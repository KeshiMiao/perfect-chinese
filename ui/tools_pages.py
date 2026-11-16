"""译者工具窗口的三页；为 280 px 宽的侧栏优化：纵向排布，每行只放一件事。"""

import os

import bpy

from ..core import env, workspace as core_workspace
from ..services import translations, workspace


def _prefs():
    return env.addon_prefs()


def draw_extract_page(layout, context):
    prefs = _prefs()
    if prefs is None:
        return
    layout.prop(prefs, "workspace_search", text="", icon="VIEWZOOM")
    query = prefs.workspace_search.strip().lower()
    entries = workspace.addon_entries()
    items = sorted((module, path) for module, path in entries.items() if query in module.lower())
    if not items:
        box = layout.box()
        box.label(text="没有匹配的插件", icon="INFO")
        box.label(text="可能是仓库未启用，或只剩 .pyc")
    for module, _path in items[:80]:
        target = core_workspace.po_path(workspace.workspace_dir(), module)
        extracted = os.path.exists(target)
        package_id = workspace.local_id(module)
        box = layout.box()
        row = box.row(align=True)
        # 版式与翻译列表一致：左侧启用框（抽取后才有），中间模块名，右侧编辑/移除或抽取。
        if extracted:
            row.operator(
                "pc.toggle",
                text="",
                emboss=False,
                icon="CHECKBOX_HLT" if translations.is_enabled(package_id) else "CHECKBOX_DEHLT",
            ).package_id = package_id
        row.label(text=module, translate=False)
        if extracted:
            actions = row.row(align=True)
            actions.alignment = "RIGHT"
            actions.operator("pc.edit_texts", text="编辑", icon="TEXT").module = module
            actions.operator("pc.remove_workspace", text="移除", icon="TRASH").module = module
        else:
            actions = row.row(align=True)
            actions.alignment = "RIGHT"
            actions.operator("pc.extract_texts", text="抽取", icon="FILE_REFRESH").module = module
    if len(items) > 80:
        layout.label(text="只显示前 80 个，用搜索缩小范围", icon="INFO")
    layout.separator(factor=0.5)
    layout.operator("pc.open_workspace", text="打开工作区目录", icon="FILE_FOLDER")


def draw_translate_page(layout, context):
    prefs = _prefs()
    editor = context.scene.pc_editor
    if not editor.module:
        box = layout.box()
        box.label(text="还没有打开译文", icon="INFO")
        box.label(text="到【抽取】页选一个插件，点【编辑】")
        return

    head = layout.row(align=True)
    head.label(text=editor.module, translate=False, icon="FILE_TEXT")
    stats = layout.row(align=True)
    stats.scale_y = 0.9
    stats.label(text="%d/%d 条已译" % (editor.done, editor.total))
    if editor.dirty:
        stats.label(text="未保存", icon="ERROR")
    elif editor.status:
        stats.label(text=editor.status, icon="INFO")

    from .editor import file_changed

    if editor.file_mtime and file_changed(editor) and not editor.dirty:
        warn = layout.box()
        warn.label(text="文件已被外部修改", icon="ERROR")
        warn.operator("pc.reload_editor", text="重新载入", icon="FILE_REFRESH")

    meta_box = layout.box()
    meta_box.prop(
        editor,
        "show_meta",
        text="元信息",
        icon="TRIA_DOWN" if editor.show_meta else "TRIA_RIGHT",
        emboss=False,
    )
    if editor.show_meta:
        meta_box.prop(editor, "meta_project", text="项目")
        meta_box.prop(editor, "meta_translator", text="译者")
        meta_box.prop(editor, "meta_revision", text="修订日期")
        meta_box.operator("pc.refresh_meta_time", text="更新修订时间", icon="FILE_REFRESH")
    tools = layout.row(align=True)
    tools.prop(editor, "only_untranslated", text="", icon="RADIOBUT_OFF")
    tools.operator("pc.save_editor", text="保存", icon="FILE_TICK")
    tools.operator("pc.check_contexts", text="自检", icon="CHECKMARK")
    if prefs is not None and prefs.deepseek_ack and prefs.deepseek_key.strip():
        tools.operator("pc.deepseek", text="", icon="SHADERFX").scope = "UNTRANSLATED"

    layout.template_list("PC_UL_strings", "", editor, "items", editor, "active_index", rows=6)
    if not editor.items:
        return
    index = min(max(editor.active_index, 0), len(editor.items) - 1)
    item = editor.items[index]

    box = layout.box()
    box.label(text="原文", icon="TEXT")
    box.prop(item, "msgid", text="")

    box.label(text="译文", icon="FONT_DATA")
    translated = box.row(align=True)
    translated.prop(item, "msgstr", text="")
    if prefs is not None and prefs.deepseek_ack and prefs.deepseek_key.strip():
        translated.operator("pc.deepseek", text="", icon="SHADERFX").scope = "CURRENT"

    box.label(text="上下文", icon="INFO")
    context_row = box.row(align=True)
    context_row.prop(item, "msgctxt", text="")
    context_row.operator("pc.pick_context", text="", icon="VIEWZOOM", translate=False)

    if item.msgstr and not item.context_ok:
        box.label(text="上下文可能不对", icon="ERROR")

    from ..core import official

    if item.msgid and official.translated(item.msgid, item.msgctxt):
        official_hint = box.column(align=True)
        official_hint.scale_y = 0.85
        official_hint.label(text="官方目录已收录这条，可参考官方译法", icon="CHECKMARK")
    
    actions = box.row(align=True)
    actions.operator("pc.add_string", text="新增行", icon="ADD")
    actions.operator("pc.remove_string", text="删除行", icon="REMOVE")
    files = box.row(align=True)
    files.scale_y = 0.9
    files.operator("pc.open_po_location", text="定位文件", icon="FILE_FOLDER")
    files.operator("pc.open_po_external", text="外部编辑", icon="WINDOW")
    if item.locations:
        hint = box.column(align=True)
        hint.scale_y = 0.8
        hint.label(text=item.locations.splitlines()[0], translate=False)


def draw_options_page(layout, context):
    prefs = _prefs()
    if prefs is None:
        return
    from . import tools_options

    tools_options.draw_identity(layout, prefs)
    tools_options.draw_deepseek(layout, prefs)
    tools_options.draw_workspace(layout, prefs)
    tools_options.draw_cache(layout, prefs)
