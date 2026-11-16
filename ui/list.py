"""翻译列表（偏好设置里的“翻译列表”标签）。"""

import bpy

from ..core import packages
from ..core.catalog import matches
from ..services import translations, workspace


def draw_translation_list(layout, prefs):
    catalog = translations.cached_catalog()
    updates = len(translations.pending_updates()) if catalog is not None else 0

    toolbar_row = layout.row(align=True)
    toolbar_row.prop(prefs, "search", text="", icon="VIEWZOOM")
    toolbar_actions = toolbar_row.row(align=True)
    toolbar_actions.alignment = "RIGHT"
    toolbar_actions.operator("pc.refresh_catalog", text="检查更新", icon="FILE_REFRESH")
    toolbar_actions.operator(
        "pc.update_all",
        text="全部更新" + (" (%d)" % updates if updates else ""),
        icon="SORT_DESC",
    )

    filter_row = layout.row(align=True)

    filters = filter_row.row(align=True)
    filters.alignment = "LEFT"
    filters.prop(prefs, "list_only_enabled", text="仅启用", toggle=True)
    filters.prop(prefs, "list_only_downloaded", text="仅下载", toggle=True)
    filters.prop(prefs, "list_only_updatable", text="待更新", toggle=True)
    filters.prop(prefs, "list_only_local", text="仅本地", toggle=True)

    catalog_summary = filter_row.row(align=True)
    catalog_summary.alignment = "RIGHT"
    catalog_summary.label(
        text="目录 %d 条 · 已启用 %d" % (len(catalog.entries), len(translations.enabled_ids()))
        if catalog is not None else "还没有目录缓存，点刷新下载")

    if translations.last_error():
        layout.label(text=translations.last_error(), icon="ERROR")
    status_text, status_ok = translations.last_status()
    if status_text:
        layout.label(text=status_text, icon="CHECKMARK" if status_ok else "ERROR")

    entries = _visible_entries(catalog, prefs)
    if not entries:
        layout.label(text="没有匹配的翻译", icon="INFO")
        return

    installed = workspace.addon_entries()
    expanded = _expanded_set(prefs)
    list_column = layout.column(align=True)
    for entry in entries:
        _draw_entry(list_column, entry, installed, entry.id in expanded)


def _filtering(prefs):
    """有搜索词或任一筛选开关：用户已经在找具体条目，补缺包不再占位。"""
    return bool(
        prefs.search.strip()
        or prefs.list_only_enabled
        or prefs.list_only_downloaded
        or prefs.list_only_updatable
        or prefs.list_only_local
    )


def _visible_entries(catalog, prefs):
    """本地译文排最前，其次是补缺包；补缺包没装时只在没有任何搜索/筛选的情况下出现。"""
    entries = [entry for entry in workspace.local_entries()
               if matches(entry, prefs.search) and _matches_filters(prefs, entry)]
    pack = translations.blender_pack_entry()
    if pack is not None and (packages.is_installed(pack.id) or not _filtering(prefs)):
        if matches(pack, prefs.search) and _matches_filters(prefs, pack):
            entries.append(pack)
    if catalog is None:
        return entries
    for entry in catalog.search(prefs.search, kind="addon"):
        if _matches_filters(prefs, entry):
            entries.append(entry)
    return entries


def _matches_filters(prefs, entry):
    if prefs.list_only_local and entry.kind != "local":
        return False
    if entry.kind == "local" and (prefs.list_only_downloaded or prefs.list_only_updatable):
        return False
    if prefs.list_only_enabled and not translations.is_enabled(entry.id):
        return False
    if prefs.list_only_downloaded and not packages.is_installed(entry.id):
        return False
    if prefs.list_only_updatable:
        return packages.is_installed(entry.id) and packages.needs_update(entry.id, entry)
    return True


def _expanded_set(prefs):
    return {package_id for package_id in prefs.expanded_packages.split() if package_id}


def _status_text(state, entry, enabled):
    """详情里的状态：本地 → 未下载 → 待更新 → 未启用 → 已启用。"""
    if entry.kind == "local":
        return "已启用" if enabled else "未启用"
    if state is None:
        return "未下载"
    if packages.needs_update(entry.id, entry):
        return "待更新"
    return "已启用" if enabled else "未启用"


def _title(entry):
    """【英文名 | 中文名】；缺一边时只显示有的那个。"""
    name = (entry.name or "").strip()
    name_zh = (entry.name_zh or "").strip()
    if name and name_zh and name_zh != name:
        return "%s | %s" % (name, name_zh)
    return name or name_zh or entry.id


def _draw_entry(layout, entry, installed, expanded):
    state = packages.installed_state(entry.id)
    enabled = translations.is_enabled(entry.id)

    entry_box = layout.box()
    # 左半：箭头 / 启用框 / 插件名 / 警告；右半：更新、安装或卸载。
    header = entry_box.row()
    header_info = header.row(align=True)
    header_info.alignment = "LEFT"

    header_info.operator(
        "pc.toggle_expanded",
        text="",
        emboss=False,
        icon="TRIA_DOWN" if expanded else "TRIA_RIGHT",
    ).package_id = entry.id

    # 启用框只在下载后出现；没下载时这一格留给折叠箭头。
    if state is not None or entry.kind == "local":
        header_info.operator(
            "pc.toggle",
            text="",
            emboss=False,
            icon="CHECKBOX_HLT" if enabled else "CHECKBOX_DEHLT",
        ).package_id = entry.id

    header_info.label(text=_title(entry))

    actions = header.row(align=True)
    actions.alignment = "RIGHT"
    _draw_warning(actions, entry, installed)
    if entry.kind == "local":
        actions.label(text="本地", icon="FILE_TEXT")
        actions.operator("pc.edit_texts", text="编辑", icon="TEXT").module = entry.module
        actions.operator("pc.remove_local", text="移除", icon="TRASH").package_id = entry.id
    elif state is None:
        actions.operator("pc.install", text="下载", icon="IMPORT").package_id = entry.id
    else:
        if packages.needs_update(entry.id, entry):
            actions.operator("pc.install", text="更新", icon="SORT_DESC").package_id = entry.id
        actions.operator("pc.uninstall", text="移除", icon="TRASH").package_id = entry.id

    if expanded:
        _draw_details(entry_box, entry, state, enabled)


def _draw_warning(row, entry, installed):
    if not entry.supports(bpy.app.version):
        row.label(text="版本不匹配", icon="ERROR")
    elif entry.kind in ("addon", "local") and entry.module and entry.module not in installed:
        row.label(text="插件未安装", icon="INFO")


def _draw_details(layout, entry, state, enabled):
    """展开后显示的翻译元信息。"""
    details = layout.column(align=True)
    grid = details.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
    if entry.kind == "blender":
        grid.label(text="模块：blender（主程序补缺）")
    else:
        grid.label(text="模块：%s" % (entry.module or "—"))
    grid.label(text="状态：%s" % _status_text(state, entry, enabled))

    grid.label(text="译者：%s" % (entry.translator or "—"))
    grid.label(text="分类：%s" % (entry.category or "—"))
    grid.label(text="支持版本：%s" % (entry.supported_versions or "*"))
    grid.label(text="更新时间：%s" % (entry.updated_at or "—"))
    if entry.kind == "local":
        grid.label(text="翻译进度：%d/%d 条已译" % (entry.translated_count, entry.entry_count))
