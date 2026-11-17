"""翻译列表（偏好设置里的“翻译列表”标签）。"""

import bpy

from ..core import packages
from ..core.catalog import matches
from ..services import translations, workspace


# 一页画太多条目会让偏好设置面板明显卡顿，只画当前页。
PAGE_SIZE = 50

MODE_ORDER = ("RECOMMEND", "ALL", "ENABLED", "DOWNLOADED", "UPDATABLE", "LOCAL")

MODE_LABELS = {
    "RECOMMEND": "推荐",
    "ALL": "全部",
    "ENABLED": "已启用",
    "DOWNLOADED": "已下载",
    "UPDATABLE": "待更新",
    "LOCAL": "仅本地",
}


def draw_translation_list(layout, prefs):
    catalog = translations.cached_catalog()
    pending = translations.pending_updates() if catalog is not None else []
    updatable = {entry.id for entry in pending}

    # 第一行：搜索占满剩余宽度，右侧是列表级动作
    toolbar = layout.row(align=True)
    toolbar.prop(prefs, "search", text="", icon="VIEWZOOM")
    actions = toolbar.row(align=True)
    actions.alignment = "RIGHT"
    actions.operator("pc.refresh_catalog", text="检查更新", icon="FILE_REFRESH")
    actions.operator(
        "pc.update_all",
        text="全部更新" + (" (%d)" % len(pending) if pending else ""),
        icon="SORT_DESC",
    )

    installed = packages.installed_ids()
    enabled = set(translations.enabled_ids())
    addons = workspace.addon_entries()
    entries = _visible_entries(catalog, prefs, installed, enabled, addons)

    total = len(entries)
    pages = page_count(total)
    page = clamp_page(prefs.list_page, pages)
    page_entries = entries[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]

    # 第二行：筛选靠左，右侧是“第几页”与翻页
    filter_row = layout.row(align=True)
    filters = filter_row.row(align=True)
    filters.alignment = "LEFT"
    for mode in MODE_ORDER:
        filters.operator(
            "pc.set_filter",
            text=MODE_LABELS[mode],
            depress=prefs.list_filter == mode,
        ).mode = mode
    pager = filter_row.row(align=True)
    pager.alignment = "RIGHT"
    pager.label(text=_summary_text(total, page, pages))
    if pages > 1:
        prev_row = pager.row(align=True)
        prev_row.enabled = page > 1
        prev_row.operator("pc.list_page", text="", icon="TRIA_LEFT").delta = -1
        next_row = pager.row(align=True)
        next_row.enabled = page < pages
        next_row.operator("pc.list_page", text="", icon="TRIA_RIGHT").delta = 1

    if translations.last_error():
        layout.label(text=translations.last_error(), icon="ERROR")
    status_text, status_ok = translations.last_status()
    if status_text:
        layout.label(text=status_text, icon="CHECKMARK" if status_ok else "ERROR")

    if not entries:
        layout.label(text=_empty_text(prefs), icon="INFO")
        return

    expanded = _expanded_set(prefs)
    list_column = layout.column(align=True)
    for entry in page_entries:
        _draw_entry(
            list_column,
            entry,
            addons,
            installed,
            enabled,
            updatable,
            entry.id in expanded,
        )


def page_count(total):
    return max(1, (int(total) + PAGE_SIZE - 1) // PAGE_SIZE)


def clamp_page(page, pages):
    return min(max(int(page or 1), 1), max(1, int(pages)))


def turn_page(prefs, delta):
    """翻页；页码始终夹在有效范围内。"""
    catalog = translations.cached_catalog()
    total = len(_visible_entries(catalog, prefs))
    pages = page_count(total)
    current = clamp_page(prefs.list_page, pages)
    prefs.list_page = clamp_page(current + int(delta), pages)
    return prefs.list_page


def _summary_text(total, page, pages):
    if pages <= 1:
        return "共 %d 条" % total
    return "共 %d 条 · 第 %d/%d 页" % (total, page, pages)


def _empty_text(prefs):
    mode = prefs.list_filter
    label = MODE_LABELS.get(mode, mode)
    search = prefs.search.strip()
    if search:
        if mode == "ALL":
            return "没有匹配「%s」的翻译" % search
        return "「%s」里没有匹配「%s」的翻译，切到「全部」再搜" % (label, search)
    return {
        "RECOMMEND": "推荐里暂时没有可用的译文：检查更新后下载一条，或切到「全部」",
        "ALL": "目录还是空的，点【检查更新】拉取列表",
        "ENABLED": "还没有启用任何译文",
        "DOWNLOADED": "还没有下载任何译文，点【检查更新】后再挑一条下载",
        "UPDATABLE": "所有译文都是最新的",
        "LOCAL": "还没有本地译文：在【译者工具】里抽取一个插件后会出现在这里",
    }.get(mode, "没有匹配的翻译")


def _visible_entries(catalog, prefs, installed=None, enabled=None, addons=None):
    """按当前筛选模式挑出条目：本地译文在前，补缺包其次，目录条目最后。"""
    mode = prefs.list_filter
    if installed is None:
        installed = packages.installed_ids()
    if enabled is None:
        enabled = set(translations.enabled_ids())
    if addons is None:
        addons = workspace.addon_entries()

    entries = [
        entry
        for entry in workspace.local_entries()
        if matches(entry, prefs.search) and _in_mode(entry, mode, installed, enabled, addons)
    ]
    pack = translations.blender_pack_entry()
    if (
        pack is not None
        and matches(pack, prefs.search)
        and _in_mode(pack, mode, installed, enabled, addons)
    ):
        entries.append(pack)
    if catalog is None:
        return entries
    for entry in catalog.search(prefs.search, kind="addon"):
        if _in_mode(entry, mode, installed, enabled, addons):
            entries.append(entry)
    return entries


def _in_mode(entry, mode, installed, enabled, addons):
    """一个条目是否属于当前筛选；installed/enabled 是 id 集合，addons 是插件模块表。"""
    if mode == "ALL":
        return True
    if mode == "RECOMMEND":
        # 主程序补缺包是插件的招牌功能，始终出现在推荐里
        if entry.kind in ("local", "blender"):
            return True
        if entry.id in installed or entry.id in enabled:
            return True
        return bool(entry.module) and entry.module in addons
    if mode == "ENABLED":
        return entry.id in enabled
    if mode == "DOWNLOADED":
        return entry.id in installed
    if mode == "UPDATABLE":
        return entry.id in installed and packages.needs_update(entry.id, entry)
    if mode == "LOCAL":
        return entry.kind == "local"
    return True


def _expanded_set(prefs):
    return {package_id for package_id in prefs.expanded_packages.split() if package_id}


def _title(entry):
    """【英文名 | 中文名】；缺一边时只显示有的那个。"""
    name = (entry.name or "").strip()
    name_zh = (entry.name_zh or "").strip()
    if name and name_zh and name_zh != name:
        return "%s | %s" % (name, name_zh)
    return name or name_zh or entry.id


def _draw_entry(layout, entry, addons, installed, enabled, updatable, expanded):
    downloaded = entry.kind == "local" or entry.id in installed
    is_enabled = entry.id in enabled

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
    if downloaded:
        header_info.operator(
            "pc.toggle",
            text="",
            emboss=False,
            icon="CHECKBOX_HLT" if is_enabled else "CHECKBOX_DEHLT",
        ).package_id = entry.id

    header_info.label(text=_title(entry))

    actions = header.row(align=True)
    actions.alignment = "RIGHT"
    _draw_warning(actions, entry, addons)
    if entry.kind == "local":
        actions.label(text="本地", icon="FILE_TEXT")
        actions.operator("pc.edit_texts", text="编辑", icon="TEXT").module = entry.module
        actions.operator("pc.remove_local", text="移除", icon="TRASH").package_id = entry.id
    elif not downloaded:
        actions.operator("pc.install", text="下载", icon="IMPORT").package_id = entry.id
    else:
        if entry.id in updatable:
            actions.operator("pc.install", text="更新", icon="SORT_DESC").package_id = entry.id
        actions.operator("pc.uninstall", text="移除", icon="TRASH").package_id = entry.id

    if expanded:
        _draw_details(entry_box, entry, downloaded, is_enabled, entry.id in updatable)


def _draw_warning(row, entry, addons):
    if not entry.supports(bpy.app.version):
        row.label(text="版本不匹配", icon="ERROR")
    elif entry.kind in ("addon", "local") and entry.module and entry.module not in addons:
        row.label(text="插件未安装", icon="INFO")


def _draw_details(layout, entry, downloaded, enabled, updatable):
    """展开后显示的翻译元信息。"""
    details = layout.column(align=True)
    grid = details.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
    if entry.kind == "blender":
        grid.label(text="模块：blender（主程序补缺）")
    else:
        grid.label(text="模块：%s" % (entry.module or "—"))
    grid.label(text="状态：%s" % _status_text(entry, downloaded, enabled, updatable))

    grid.label(text="译者：%s" % (entry.translator or "—"))
    grid.label(text="分类：%s" % (entry.category or "—"))
    grid.label(text="支持版本：%s" % (entry.supported_versions or "*"))
    grid.label(text="更新时间：%s" % (entry.updated_at or "—"))
    if entry.kind == "local":
        grid.label(text="翻译进度：%d/%d 条已译" % (entry.translated_count, entry.entry_count))


def _status_text(entry, downloaded, enabled, updatable):
    """详情里的状态：仅本地 → 未下载 → 待更新 → 未启用 → 已启用。"""
    if entry.kind == "local":
        return "已启用" if enabled else "未启用"
    if not downloaded:
        return "未下载"
    if updatable:
        return "待更新"
    return "已启用" if enabled else "未启用"
