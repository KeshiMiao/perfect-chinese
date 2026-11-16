"""译者表格：列出工作区里的词条，就地改译文、自检上下文、保存即预览。"""

import os

import bpy

from ..core import env, extract, net, official, registry, workspace
from ..services import translator, translations, workspace as workspace_service

AUTOSAVE_DELAY = 0.6
_AUTOSAVE = {"timer": None}

# 当前注册的预览域，切换文件 / 删除工作区 .po / 卸载插件时用它注销
_PREVIEW = {"name": ""}


def _redraw_all():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _editor_of(context=None):
    scene = getattr(context or bpy.context, "scene", None)
    return getattr(scene, "pc_editor", None)


# 上下文补全的兜底候选：当前 .po 里出现过的之外，再补 Blender 常见的几类。
COMMON_CONTEXTS = (
    "Operator",
    "Panel",
    "Property",
    "Preferences",
    "Add-on Preferences",
    "Key-map",
    "Region",
    "Window",
)


def _context_items(self, context):
    values = set()
    editor = _editor_of(context)
    if editor is not None:
        for item in editor.items:
            if item.msgctxt.strip():
                values.add(item.msgctxt.strip())
    values.update(COMMON_CONTEXTS)
    # 枚举 id 不能是空串（Blender 会丢弃这一项），清空用哨兵值
    entries = [("__none__", "无", "清空这一条的上下文")]
    entries.extend((value, value, "使用这个上下文") for value in sorted(values))
    return entries


def _schedule_autosave():
    if _AUTOSAVE["timer"] is not None:
        return
    _AUTOSAVE["timer"] = bpy.app.timers.register(_autosave, first_interval=AUTOSAVE_DELAY)


def _autosave():
    _AUTOSAVE["timer"] = None
    editor = _editor_of()
    if editor is None or editor.loading or not editor.module or not editor.dirty:
        return None
    try:
        count = save_editor(editor)
        import time

        editor.status = "已保存 %s · 预览 %d 条" % (time.strftime("%H:%M:%S"), count)
    except Exception as exc:
        editor.status = "自动保存失败：%s" % exc
    _redraw_all()
    return None


def _meta_changed(editor, context):
    if editor is None or editor.loading:
        return
    editor.dirty = True
    _schedule_autosave()


def _item_changed(item, context):
    editor = _editor_of(context)
    if editor is None or editor.loading:
        return
    editor.dirty = True
    _schedule_autosave()


class PC_StringItem(bpy.types.PropertyGroup):
    msgid: bpy.props.StringProperty(update=_item_changed)
    msgctxt: bpy.props.StringProperty(update=_item_changed)
    msgstr: bpy.props.StringProperty(update=_item_changed)
    locations: bpy.props.StringProperty()
    translated: bpy.props.BoolProperty(default=False)
    context_ok: bpy.props.BoolProperty(default=True)


class PC_EditorState(bpy.types.PropertyGroup):
    module: bpy.props.StringProperty()
    filepath: bpy.props.StringProperty()
    source: bpy.props.StringProperty()
    name: bpy.props.StringProperty()
    meta_project: bpy.props.StringProperty(name="项目名", description="写入 .po 文件头的 Project-Id-Version", update=_meta_changed)
    meta_translator: bpy.props.StringProperty(name="译者", description="写入 Last-Translator 与 translator", update=_meta_changed)
    meta_revision: bpy.props.StringProperty(name="修订日期", description="写入 PO-Revision-Date", update=_meta_changed)
    only_untranslated: bpy.props.BoolProperty(name="只看未翻译", default=False)
    items: bpy.props.CollectionProperty(type=PC_StringItem)
    active_index: bpy.props.IntProperty(default=0)
    total: bpy.props.IntProperty(default=0)
    done: bpy.props.IntProperty(default=0)
    status: bpy.props.StringProperty()
    dirty: bpy.props.BoolProperty(default=False)
    loading: bpy.props.BoolProperty(default=False, options={"HIDDEN"})
    file_mtime: bpy.props.IntProperty(default=0)
    file_size: bpy.props.IntProperty(default=0)
    show_meta: bpy.props.BoolProperty(name="元信息", default=False)


def _matches_needle(needle, item):
    """内置过滤框：支持 * 与 ? 通配，匹配原文、译文与上下文。"""
    texts = (item.msgid, item.msgstr, item.msgctxt)
    if "*" in needle or "?" in needle:
        import fnmatch

        return any(fnmatch.fnmatchcase(text.lower(), needle) for text in texts)
    return any(needle in text.lower() for text in texts)


class PC_UL_strings(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # 行里只放原文（字面显示，不能交给翻译）；译文放详情卡片。
        string_row = layout.row(align=True)
        string_row.label(text="", icon="CHECKBOX_HLT" if item.translated else "CHECKBOX_DEHLT")
        text = item.msgid or "（空原文）"
        string_row.label(text=text[:32] + ("…" if len(text) > 32 else ""), translate=False)
        if item.msgctxt:
            string_row.label(text="[%s]" % item.msgctxt[:10], translate=False)
        if not item.context_ok:
            string_row.label(text="", icon="QUESTION")

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        editor = data
        needle = getattr(self, "filter_name", "").strip().lower()
        flags = []
        for item in items:
            if editor.only_untranslated and item.translated:
                flags.append(0)
                continue
            if needle and not _matches_needle(needle, item):
                flags.append(0)
                continue
            flags.append(self.bitflag_filter_item)
        return flags, []


def _completeness(editor):
    editor.total = len(editor.items)
    editor.done = sum(1 for item in editor.items if item.msgstr.strip())


def _entries(editor, old=()):
    """编辑器行 → POEntry；沿用旧条目里的 fuzzy、复数与位置，保存一次不会把它们丢掉。"""
    previous = {(entry.msgctxt, entry.msgid): entry for entry in old if not entry.obsolete}
    entries = []
    for item in editor.items:
        # 空 msgid 的行不写回：.po 里它会变成一条无意义的空条目。
        if not item.msgid.strip():
            continue
        entry = extract.po.POEntry()
        entry.msgctxt = item.msgctxt
        entry.msgid = item.msgid
        entry.msgstr = item.msgstr
        entry.locations = [part for part in item.locations.splitlines() if part]
        old_entry = previous.get((item.msgctxt, item.msgid))
        if old_entry is not None:
            entry.msgid_plural = old_entry.msgid_plural
            entry.plurals = dict(old_entry.plurals)
            # 译文没改就保留原 fuzzy 标记；改过则视为人工确认
            entry.fuzzy = old_entry.fuzzy and old_entry.msgstr == item.msgstr
        entries.append(entry)
    return entries


def _obsolete_entries(old, editor):
    """编辑器里不显示的旧条目原样留着，写回时带 #~ 前缀。"""
    edited = {(item.msgctxt, item.msgid) for item in editor.items if item.msgid.strip()}
    return [entry for entry in old if entry.obsolete and (entry.msgctxt, entry.msgid) not in edited]


def _unregister_preview():
    name = _PREVIEW["name"]
    _PREVIEW["name"] = ""
    if not name:
        return
    try:
        registry.unregister(name)
    except Exception:
        pass


def forget_preview(module):
    """某个模块的预览域不再需要（删除工作区 .po 时调用）。"""
    if _PREVIEW["name"] == "edit-" + str(module):
        _unregister_preview()


def _register_preview(editor):
    translations_map = {}
    for item in editor.items:
        if item.msgstr.strip():
            translations_map.setdefault(item.msgctxt, {})[item.msgid] = item.msgstr
    name = "edit-" + editor.module if editor.module else ""
    if not translations_map or not name:
        _unregister_preview()
        return 0
    if _PREVIEW["name"] and _PREVIEW["name"] != name:
        _unregister_preview()
    _PREVIEW["name"] = name
    return registry.register(name, translations_map)


class PC_OT_add_string(bpy.types.Operator):
    bl_idname = "pc.add_string"
    bl_label = "新增词条"
    bl_description = "新增一条空词条：填原文、可选上下文与译文"

    def execute(self, context):
        editor = context.scene.pc_editor
        if not editor.module:
            self.report({"ERROR"}, "先打开一个工作区文件")
            return {"CANCELLED"}
        item = editor.items.add()
        item.msgid = ""
        item.msgctxt = ""
        item.msgstr = ""
        editor.active_index = len(editor.items) - 1
        editor.dirty = True
        _schedule_autosave()
        return {"FINISHED"}


class PC_OT_remove_string(bpy.types.Operator):
    bl_idname = "pc.remove_string"
    bl_label = "删除词条"
    bl_description = "删除当前选中的词条；保存后从 .po 里移除"

    def execute(self, context):
        editor = context.scene.pc_editor
        if not editor.items:
            return {"CANCELLED"}
        index = min(max(editor.active_index, 0), len(editor.items) - 1)
        editor.items.remove(index)
        editor.active_index = max(0, min(index, len(editor.items) - 1))
        editor.dirty = True
        _schedule_autosave()
        return {"FINISHED"}


def load_editor(editor, path, module):
    """把 .po 读进编辑器；记录 mtime/size 供外部改动检测。obsolete 条目不进表格。"""
    if editor.module and editor.module != module:
        # 换了文件：旧文件的预览域不能继续留在注册表里
        _unregister_preview()
    entries = [entry for entry in extract.load_existing(path) if not entry.obsolete]
    editor.loading = True
    editor.items.clear()
    for entry in entries:
        item = editor.items.add()
        item.msgid = entry.msgid
        item.msgctxt = entry.msgctxt
        item.msgstr = entry.msgstr
        item.locations = "\n".join(entry.locations)
        item.translated = bool(entry.msgstr.strip())
    editor.module = module
    editor.filepath = path
    editor.source = workspace_service.source_path(module) or ""
    editor.name = ""
    editor.active_index = 0
    meta = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as handle:
            meta = extract.po.read_meta(handle.read())
    editor.meta_project = meta.get("Project-Id-Version", module)
    editor.meta_translator = meta.get("Last-Translator") or meta.get("translator", "")
    editor.meta_revision = meta.get("PO-Revision-Date", "")
    editor.dirty = False
    try:
        editor.file_mtime = int(os.path.getmtime(path))
        editor.file_size = os.path.getsize(path)
    except OSError:
        editor.file_mtime = 0
        editor.file_size = 0
    editor.loading = False
    _completeness(editor)


def file_changed(editor):
    """外部编辑器改过 .po 吗？"""
    if not editor.filepath or not os.path.exists(editor.filepath):
        return False
    try:
        return (os.path.getsize(editor.filepath) != editor.file_size
                or int(os.path.getmtime(editor.filepath)) != editor.file_mtime)
    except OSError:
        return False


class PC_OT_edit_texts(bpy.types.Operator):
    bl_idname = "pc.edit_texts"
    bl_label = "编辑译文"
    bl_description = "打开工作区里的 .po，逐条编辑译文"

    module: bpy.props.StringProperty()

    def execute(self, context):
        path = workspace.po_path(workspace_service.workspace_dir(), self.module)
        if not os.path.exists(path):
            self.report({"ERROR"}, "还没有抽取过 %s" % self.module)
            return {"CANCELLED"}
        editor = context.scene.pc_editor
        if editor.dirty and editor.filepath and editor.filepath != path:
            # 自动保存在 0.6s 后；这之前切文件会静默丢掉最后几笔改动
            self.report({"ERROR"}, "当前文件还没保存，先保存再切换")
            return {"CANCELLED"}
        load_editor(editor, path, self.module)
        return {"FINISHED"}


class PC_OT_reload_editor(bpy.types.Operator):
    bl_idname = "pc.reload_editor"
    bl_label = "重新载入"
    bl_description = "丢弃内存里的改动，重新读取磁盘上的 .po"

    def execute(self, context):
        editor = context.scene.pc_editor
        if not editor.filepath or not os.path.exists(editor.filepath):
            self.report({"ERROR"}, "文件不存在")
            return {"CANCELLED"}
        load_editor(editor, editor.filepath, editor.module)
        return {"FINISHED"}


class PC_OT_open_po_location(bpy.types.Operator):
    bl_idname = "pc.open_po_location"
    bl_label = "打开所在位置"
    bl_description = "在文件管理器里定位当前 .po"

    def execute(self, context):
        path = context.scene.pc_editor.filepath
        if not path or not os.path.exists(path):
            self.report({"ERROR"}, "文件不存在")
            return {"CANCELLED"}
        if os.name == "nt":
            import subprocess

            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
        else:
            bpy.ops.wm.path_open(filepath=os.path.dirname(path))
        return {"FINISHED"}


class PC_OT_open_po_external(bpy.types.Operator):
    bl_idname = "pc.open_po_external"
    bl_label = "用外部编辑器打开"
    bl_description = "用系统关联的程序打开当前 .po，可与其他编辑器协同"

    def execute(self, context):
        path = context.scene.pc_editor.filepath
        if not path or not os.path.exists(path):
            self.report({"ERROR"}, "文件不存在")
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=path)
        return {"FINISHED"}


def save_editor(editor):
    """把编辑器内容写回 .po 并刷新预览，返回注册的条数。"""
    old = extract.load_existing(editor.filepath) if os.path.exists(editor.filepath) else []
    entries = _entries(editor, old) + _obsolete_entries(old, editor)
    meta = {}
    if os.path.exists(editor.filepath):
        with open(editor.filepath, encoding="utf-8", errors="replace") as handle:
            meta = extract.po.read_meta(handle.read())
    for key, value in (
        ("Project-Id-Version", editor.meta_project),
        ("Last-Translator", editor.meta_translator),
        ("PO-Revision-Date", editor.meta_revision),
        ("translator", editor.meta_translator),
    ):
        if value:
            meta[key] = value
    text = extract.render(
        entries,
        module=editor.module,
        source=editor.source,
        name=editor.name,
        header=workspace.read_header(editor.filepath),
        meta=meta,
    )
    from ..core import store

    store.atomic_write(editor.filepath, text.encode("utf-8"))
    try:
        import os as _os

        editor.file_mtime = int(_os.path.getmtime(editor.filepath))
        editor.file_size = _os.path.getsize(editor.filepath)
    except OSError:
        pass
    editor.loading = True
    for item in editor.items:
        item.translated = bool(item.msgstr.strip())
    editor.loading = False
    editor.dirty = False
    _completeness(editor)
    workspace_service.invalidate_local_cache()
    return _register_preview(editor)


class PC_OT_save_editor(bpy.types.Operator):
    bl_idname = "pc.save_editor"
    bl_label = "保存译文"
    bl_description = "写回 .po 并把译文注册到界面，立即能看到效果"

    def execute(self, context):
        editor = context.scene.pc_editor
        if not editor.module:
            self.report({"ERROR"}, "没有打开的工作区文件")
            return {"CANCELLED"}
        try:
            count = save_editor(editor)
        except Exception as exc:
            self.report({"ERROR"}, "保存失败：%s" % exc)
            return {"CANCELLED"}
        self.report({"INFO"}, "已保存并预览 %d 条译文" % count)
        translations.redraw()
        return {"FINISHED"}


class PC_OT_pick_context(bpy.types.Operator):
    bl_idname = "pc.pick_context"
    bl_label = "选择上下文"
    bl_description = "从当前文件已有的上下文里选一个；可输入过滤，也能手填"
    bl_property = "value"

    value: bpy.props.EnumProperty(name="上下文", items=_context_items)

    def invoke(self, context, event):
        context.window_manager.invoke_search_popup(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        editor = context.scene.pc_editor
        if not editor.items:
            return {"CANCELLED"}
        index = min(max(editor.active_index, 0), len(editor.items) - 1)
        editor.items[index].msgctxt = "" if self.value == "__none__" else self.value
        return {"FINISHED"}


class PC_OT_deepseek(bpy.types.Operator):
    bl_idname = "pc.deepseek"
    bl_label = "DeepSeek 翻译"
    bl_description = "用 DeepSeek 翻译：顶部按钮翻译全部未译条目，译文旁的按钮只翻当前一条；只上传原文与上下文"

    scope: bpy.props.EnumProperty(
        items=[
            ("UNTRANSLATED", "翻译未译条目", "把所有未翻译的词条分批翻译"),
            ("CURRENT", "翻译当前条目", "只翻译选中的这一条（会覆盖已有译文）"),
        ],
        default="UNTRANSLATED",
    )

    def execute(self, context):
        editor = context.scene.pc_editor
        if not editor.module or not editor.items:
            self.report({"ERROR"}, "没有打开的工作区文件")
            return {"CANCELLED"}
        prefs = context.preferences.addons[env.ADDON_ID].preferences
        if not prefs.deepseek_ack:
            self.report({"ERROR"}, "先在偏好设置的 DeepSeek 里勾选同意上传词条")
            return {"CANCELLED"}
        if not prefs.deepseek_key.strip():
            self.report({"ERROR"}, "先在偏好设置里填 DeepSeek API Key")
            return {"CANCELLED"}

        targets, official_count = [], 0
        for index, item in enumerate(editor.items):
            if self.scope == "CURRENT":
                if index != editor.active_index:
                    continue
            elif item.msgstr.strip():
                continue
            if official.translated(item.msgid, item.msgctxt):
                official_count += 1
            targets.append((index, item))
        if not targets:
            self.report({"INFO"}, "没有需要翻译的词条")
            return {"CANCELLED"}
        if len(targets) > translator.MAX_ITEMS:
            self.report({"ERROR"}, "一次最多 %d 条，请先筛选" % translator.MAX_ITEMS)
            return {"CANCELLED"}

        payload = [{"msgid": item.msgid, "msgctxt": item.msgctxt} for _, item in targets]
        editor.status = "正在翻译 %d 条…" % len(payload)
        key, model = prefs.deepseek_key, prefs.deepseek_model
        module = editor.module

        def work():
            return translator.translate(payload, key, model=model)

        def done(result, error):
            if _editor_of() is not editor or editor.module != module:
                # 用户已经切到别的文件：结果不能写进新文件的表格
                return
            if error is not None:
                # operator 可能已经结束，不能再用 self.report，结果写在编辑器状态行
                editor.status = "翻译失败：%s" % error
                translations.redraw()
                return
            for (_, item), text in zip(targets, result):
                item.msgstr = text
            try:
                count = save_editor(editor)
            except Exception as exc:
                editor.status = "翻译完成，但保存失败：%s" % exc
                return
            note = "（%d 条官方已收录）" % official_count if official_count else ""
            editor.status = "已翻译 %d 条%s，预览 %d 条" % (len(result), note, count)
            translations.redraw()

        net.run_in_background(work, done)
        return {"FINISHED"}


class PC_OT_check_contexts(bpy.types.Operator):
    bl_idname = "pc.check_contexts"
    bl_label = "自检上下文"
    bl_description = "逐条用自己的上下文查一次，查得到才算上下文正确"

    def execute(self, context):
        editor = context.scene.pc_editor
        if not editor.module:
            self.report({"ERROR"}, "没有打开的工作区文件")
            return {"CANCELLED"}
        try:
            _register_preview(editor)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        bad = 0
        for item in editor.items:
            if not item.msgstr.strip():
                item.context_ok = True
                continue
            if item.msgctxt:
                actual = bpy.app.translations.pgettext(item.msgid, item.msgctxt)
            else:
                actual = bpy.app.translations.pgettext_iface(item.msgid)
            item.context_ok = actual == item.msgstr
            if not item.context_ok:
                bad += 1
        self.report({"INFO"}, ("%d 条上下文可能不对" % bad) if bad else "上下文检查通过")
        return {"FINISHED"}


class PC_OT_refresh_meta_time(bpy.types.Operator):
    bl_idname = "pc.refresh_meta_time"
    bl_label = "刷新修订日期"
    bl_description = "把修订日期填成当前时间（写入 .po 文件头的 PO-Revision-Date）"

    def execute(self, context):
        editor = _editor_of(context)
        if editor is None or not editor.module:
            self.report({"ERROR"}, "没有打开的工作区文件")
            return {"CANCELLED"}
        import time

        editor.meta_revision = time.strftime("%Y-%m-%d %H:%M%z")
        editor.dirty = True
        _schedule_autosave()
        return {"FINISHED"}


_classes = (PC_StringItem, PC_EditorState, PC_UL_strings, PC_OT_add_string, PC_OT_remove_string, PC_OT_edit_texts, PC_OT_reload_editor, PC_OT_open_po_location, PC_OT_open_po_external, PC_OT_save_editor, PC_OT_pick_context, PC_OT_refresh_meta_time, PC_OT_deepseek, PC_OT_check_contexts)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pc_editor = bpy.props.PointerProperty(type=PC_EditorState)


def unregister():
    if _AUTOSAVE["timer"] is not None:
        try:
            bpy.app.timers.unregister(_AUTOSAVE["timer"])
        except ValueError:
            pass
        _AUTOSAVE["timer"] = None
    _unregister_preview()
    del bpy.types.Scene.pc_editor
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
