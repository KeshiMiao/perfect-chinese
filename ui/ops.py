"""翻译相关 Operator：刷新目录、安装、启用/停用、卸载。"""

import os

import bpy

from ..core import env, net, packages, workspace as core_workspace
from ..services import language, translator, translations, update_check, workspace


def _background(work, label, apply=None):
    """后台只做下载；拿到结果后在主线程（done 回调）里写文件、碰 bpy。"""

    def done(result, error):
        if error is not None:
            translations.set_error("%s失败：%s" % (label, error))
        elif getattr(result, "error", ""):
            # sync() 把网络/目录错误放在返回值里，不抛异常
            translations.set_error("%s失败：%s" % (label, result.error))
        else:
            translations.set_error("")
            if apply is not None:
                try:
                    apply(result)
                except Exception as exc:
                    translations.set_error("%s失败：%s" % (label, exc))
        translations.redraw()

    net.run_in_background(work, done)


class PC_OT_refresh_catalog(bpy.types.Operator):
    bl_idname = "pc.refresh_catalog"
    bl_label = "刷新目录"
    bl_description = "从官方源获取最新的翻译列表"

    def execute(self, context):
        _background(lambda: translations.sync(force=True), "刷新目录", translations.finish_sync)
        return {"FINISHED"}


class PC_OT_install(bpy.types.Operator):
    bl_idname = "pc.install"
    bl_label = "安装翻译"
    bl_description = "下载并启用这个插件的翻译"

    package_id: bpy.props.StringProperty()

    def execute(self, context):
        entry = translations.find_entry(self.package_id)
        if entry is None:
            self.report({"ERROR"}, "目录里没有这个条目，请先刷新")
            return {"CANCELLED"}
        url = translations.download_url(entry)

        def work():
            return entry, net.fetch(url).data

        def apply(pair):
            installed, data = pair
            translations.install(installed, data)

        _background(work, "安装", apply)
        return {"FINISHED"}


class PC_OT_update_all(bpy.types.Operator):
    bl_idname = "pc.update_all"
    bl_label = "全部更新"
    bl_description = "更新所有已安装且有新版本的翻译"

    def execute(self, context):
        pending = translations.pending_updates()
        if not pending:
            self.report({"INFO"}, "没有需要更新的翻译")
            return {"CANCELLED"}

        def work():
            return translations.download_updates()

        def done(result, error):
            if error is not None:
                translations.set_status("更新失败：%s" % error, ok=False)
            else:
                downloads, problems = result
                updated = translations.apply_downloads(downloads)
                if problems:
                    translations.set_status(
                        "已更新 %d 个翻译，%d 个失败" % (updated, len(problems)), ok=False
                    )
                else:
                    translations.set_status("已更新 %d 个翻译" % updated)
            translations.redraw()

        net.run_in_background(work, done)
        return {"FINISHED"}


class PC_OT_toggle(bpy.types.Operator):
    bl_idname = "pc.toggle"
    bl_label = "启用/停用翻译"

    package_id: bpy.props.StringProperty()

    def execute(self, context):
        try:
            if translations.is_enabled(self.package_id):
                translations.disable(self.package_id)
            else:
                translations.enable(self.package_id)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        return {"FINISHED"}


class PC_OT_uninstall(bpy.types.Operator):
    bl_idname = "pc.uninstall"
    bl_label = "卸载翻译"

    package_id: bpy.props.StringProperty()

    def execute(self, context):
        translations.uninstall(self.package_id)
        return {"FINISHED"}


class PC_OT_toggle_expanded(bpy.types.Operator):
    bl_idname = "pc.toggle_expanded"
    bl_label = "展开/收起翻译详情"
    bl_description = "展开或收起这条翻译的元信息"

    package_id: bpy.props.StringProperty()

    def execute(self, context):
        prefs = env.addon_prefs()
        if prefs is None:
            return {"CANCELLED"}
        ids = [item for item in prefs.expanded_packages.split() if item]
        if self.package_id in ids:
            ids.remove(self.package_id)
        else:
            ids.append(self.package_id)
        prefs.expanded_packages = " ".join(ids)
        return {"FINISHED"}


class PC_OT_list_page(bpy.types.Operator):
    bl_idname = "pc.list_page"
    bl_label = "翻译列表翻页"
    bl_description = "切换到翻译列表的上一页或下一页"

    delta: bpy.props.IntProperty(default=1)

    def execute(self, context):
        prefs = env.addon_prefs()
        if prefs is None:
            return {"CANCELLED"}
        from .list import turn_page

        turn_page(prefs, self.delta)
        return {"FINISHED"}


class PC_OT_set_filter(bpy.types.Operator):
    bl_idname = "pc.set_filter"
    bl_label = "筛选翻译列表"
    bl_description = "只显示某一类译文"

    mode: bpy.props.StringProperty()

    def execute(self, context):
        prefs = env.addon_prefs()
        if prefs is None:
            return {"CANCELLED"}
        prefs.list_filter = self.mode
        return {"FINISHED"}


class PC_OT_extract_texts(bpy.types.Operator):
    bl_idname = "pc.extract_texts"
    bl_label = "抽取插件文本"
    bl_description = "扫描插件源码，生成或更新工作区里的 .po，已有译文会保留"

    module: bpy.props.StringProperty()

    def execute(self, context):
        try:
            result, target = workspace.extract(self.module)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "抽取 %d 条 → %s；动态文本 %d 处"
            % (len(result.entries()), target, len(result.problems)),
        )
        return {"FINISHED"}


class PC_OT_preview_texts(bpy.types.Operator):
    bl_idname = "pc.preview_texts"
    bl_label = "预览工作区译文"
    bl_description = "把工作区里的译文临时注册到界面，保存后点一次即可看到效果"

    module: bpy.props.StringProperty()

    def execute(self, context):
        try:
            count = workspace.preview(self.module)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, "已预览 %d 条译文" % count)
        translations.redraw()
        return {"FINISHED"}


class PC_OT_toggle_language(bpy.types.Operator):
    bl_idname = "pc.toggle_language"
    bl_label = "切换中文界面"
    bl_description = "在中英界面之间切换"

    def execute(self, context):
        prefs = env.addon_prefs()
        if prefs is None:
            self.report({"ERROR"}, "找不到插件偏好设置")
            return {"CANCELLED"}
        chinese = env.view_prefs().language == language.ZH_HANS
        if chinese:
            if prefs.previous_language in ("", language.ZH_HANS):
                # 原语言就是中文（或状态对不上）：按钮要能切到英文，别原地不动。
                prefs.previous_language = language.FALLBACK_LANGUAGE
            prefs.language_enabled = False
        else:
            prefs.language_enabled = True
        language.apply(prefs)
        return {"FINISHED"}


class PC_OT_test_deepseek(bpy.types.Operator):
    bl_idname = "pc.test_deepseek"
    bl_label = "测试 DeepSeek 连接"
    bl_description = "翻译一条示例文本，确认 Key 与网络可用"

    def execute(self, context):
        prefs = context.preferences.addons[env.ADDON_ID].preferences
        if not prefs.deepseek_ack:
            self.report({"ERROR"}, "先勾选“允许把词条发往 DeepSeek”")
            return {"CANCELLED"}
        if not prefs.deepseek_key.strip():
            self.report({"ERROR"}, "先填 API Key")
            return {"CANCELLED"}
        key, model = prefs.deepseek_key, prefs.deepseek_model
        translator.LAST_TEST = "正在测试…"
        translator.LAST_TEST_OK = True

        def work():
            return translator.translate([{"msgid": "Add Cube", "msgctxt": "Operator"}], key, model=model)

        def done(result, error):
            # 后台完成时这个 operator 实例可能已经释放，不能再 self.report；
            # 结果放在偏好设置页的状态行里显示。
            if error is not None:
                translator.LAST_TEST = "连接失败：%s" % error
                translator.LAST_TEST_OK = False
                translations.set_status(translator.LAST_TEST, ok=False)
            else:
                translator.LAST_TEST = "连接正常：Add Cube → %s" % result[0]
                translator.LAST_TEST_OK = True
                translations.set_status(translator.LAST_TEST)
            translations.redraw()

        net.run_in_background(work, done)
        return {"FINISHED"}


class PC_OT_check_client_update(bpy.types.Operator):
    bl_idname = "pc.check_client_update"
    bl_label = "检查更新"
    bl_description = "查客户端最新版本（只检查，不自动下载）"

    def execute(self, context):
        def work():
            return update_check.check_client()

        def done(result, error):
            update_check.remember_client(result, error)
            translations.redraw()

        net.run_in_background(work, done)
        return {"FINISHED"}


class PC_OT_open_release_page(bpy.types.Operator):
    bl_idname = "pc.open_release_page"
    bl_label = "打开发布页"

    def execute(self, context):
        url = update_check.CLIENT_RESULT.get("url") or update_check.CLIENT_PAGE
        bpy.ops.wm.url_open(url=url)
        return {"FINISHED"}


class PC_OT_open_workspace(bpy.types.Operator):
    bl_idname = "pc.open_workspace"
    bl_label = "打开工作区目录"
    bl_description = "在文件管理器里打开译者工作区"

    def execute(self, context):
        directory = workspace.workspace_dir()
        os.makedirs(directory, exist_ok=True)
        bpy.ops.wm.path_open(filepath=directory)
        return {"FINISHED"}


class PC_OT_remove_local(bpy.types.Operator):
    bl_idname = "pc.remove_local"
    bl_label = "移除本地译文"
    bl_description = "从工作区删除这条本地 .po，并停用它的译文"

    package_id: bpy.props.StringProperty()
    message: bpy.props.StringProperty()

    def invoke(self, context, event):
        entry = workspace.find_local(self.package_id)
        if entry is None:
            self.report({"ERROR"}, "工作区里找不到这个 .po")
            return {"CANCELLED"}
        self.message = "删除工作区里的 %s？" % entry.module
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        column = self.layout.column(align=True)
        column.label(text=self.message, translate=False)
        column.label(text="文件会从工作区删除，无法撤销", icon="ERROR")
        column.label(text="已启用的译文会先停用", icon="INFO")

    def execute(self, context):
        entry = workspace.find_local(self.package_id)
        if entry is None:
            self.report({"ERROR"}, "工作区里找不到这个 .po")
            return {"CANCELLED"}
        path = workspace.local_files().get(entry.module)
        try:
            translations.disable(self.package_id)
        except Exception:
            pass
        if path and os.path.exists(path):
            os.remove(path)
        translations.set_status("已移除本地译文 %s" % entry.module)
        translations.redraw()
        return {"FINISHED"}


class PC_OT_remove_workspace(bpy.types.Operator):
    bl_idname = "pc.remove_workspace"
    bl_label = "移除工作区译文"
    bl_description = "删除这个插件在工作区里的 .po"

    module: bpy.props.StringProperty()
    message: bpy.props.StringProperty()

    def invoke(self, context, event):
        path = core_workspace.po_path(workspace.workspace_dir(), self.module)
        if not os.path.exists(path):
            self.report({"ERROR"}, "还没有抽取过这个插件")
            return {"CANCELLED"}
        self.message = "删除工作区里的 %s？" % os.path.basename(path)
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        column = self.layout.column(align=True)
        column.label(text=self.message, translate=False)
        column.label(text="文件会从工作区删除，无法撤销", icon="ERROR")
        column.label(text="已启用的译文会先停用", icon="INFO")

    def execute(self, context):
        path = core_workspace.po_path(workspace.workspace_dir(), self.module)
        if not os.path.exists(path):
            self.report({"ERROR"}, "还没有抽取过这个插件")
            return {"CANCELLED"}
        try:
            translations.disable(workspace.local_id(self.module))
        except Exception:
            pass
        from . import editor as editor_ui

        editor_ui.forget_preview(self.module)
        os.remove(path)
        translations.set_status("已移除 %s 的工作区译文" % self.module)
        translations.redraw()
        return {"FINISHED"}


_classes = (
    PC_OT_refresh_catalog,
    PC_OT_install,
    PC_OT_update_all,
    PC_OT_toggle,
    PC_OT_uninstall,
    PC_OT_toggle_expanded,
    PC_OT_list_page,
    PC_OT_set_filter,
    PC_OT_extract_texts,
    PC_OT_preview_texts,
    PC_OT_toggle_language,
    PC_OT_test_deepseek,
    PC_OT_check_client_update,
    PC_OT_open_release_page,
    PC_OT_open_workspace,
    PC_OT_remove_local,
    PC_OT_remove_workspace,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
