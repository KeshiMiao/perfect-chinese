"""翻译管理：启用集合、安装/卸载、启动时应用。"""

import time

import bpy

from ..core import env, net, packages, registry, store
from . import update_check
from . import workspace as workspace_service

ENABLED_FILE = "enabled.json"

# 最近一次后台操作的错误，面板上显示一行提示。
LAST_ERROR = ""

# 最近一次后台操作的结果（成功提示），与错误分开显示。
LAST_STATUS = ""
LAST_STATUS_OK = True


def set_error(message):
    global LAST_ERROR
    LAST_ERROR = message or ""


def last_error():
    return LAST_ERROR


def set_status(message, ok=True):
    global LAST_STATUS, LAST_STATUS_OK
    LAST_STATUS = message or ""
    LAST_STATUS_OK = ok


def last_status():
    return LAST_STATUS, LAST_STATUS_OK


def enabled_path():
    return store.data_path("state", ENABLED_FILE)


def enabled_ids():
    data = store.read_json(enabled_path(), [])
    return [item for item in data if isinstance(item, str)] if isinstance(data, list) else []


def _save_enabled(ids):
    store.write_json(enabled_path(), sorted(set(ids)))


def bilingual_enabled():
    prefs = env.addon_prefs()
    return bool(getattr(prefs, "bilingual", False)) if prefs else False


def separator():
    prefs = env.addon_prefs()
    return getattr(prefs, "bilingual_separator", "") if prefs else ""


def enable_local(package_id):
    """启用工作区里的本地译文：直接注册当前 .po，不复制进缓存区。"""
    module = workspace_service.local_module(package_id)
    translations_map = workspace_service.local_summary(module)
    if not translations_map:
        raise ValueError("这个 .po 里还没有译文")
    registry.register(package_id, translations_map, bilingual=bilingual_enabled(), separator=separator())
    ids = set(enabled_ids())
    ids.add(package_id)
    _save_enabled(ids)
    invalidate_caches()
    return True


def enable(package_id):
    if workspace_service.is_local(package_id):
        return enable_local(package_id)
    translations = packages.load_translations(package_id)
    if not translations:
        raise ValueError("没有可注册的译文")
    registry.register(package_id, translations, bilingual=bilingual_enabled(), separator=separator())
    ids = set(enabled_ids())
    ids.add(package_id)
    _save_enabled(ids)
    invalidate_caches()
    return True


def disable(package_id):
    registry.unregister(package_id)
    ids = set(enabled_ids())
    ids.discard(package_id)
    _save_enabled(ids)
    invalidate_caches()
    return True


def is_enabled(package_id):
    return registry.registry.is_active(package_id)


def install(entry, data, auto_enable=True):
    """写入并启用一个包；失败时恢复更新前的版本，不会把原来能用的删掉。"""
    was_enabled = is_enabled(entry.id)
    backup = packages.backup(entry.id)
    try:
        state = packages.install(entry, data)
        if auto_enable:
            enable(entry.id)
    except Exception:
        # 注册失败（例如新 .po 全是 fuzzy）时回滚：能恢复旧版就恢复，全新安装才删除。
        packages.uninstall(entry.id)
        if backup is not None:
            packages.restore(entry.id, backup)
            if was_enabled:
                try:
                    enable(entry.id)
                except Exception:
                    pass
        raise
    finally:
        invalidate_caches()
    packages.drop_backup(backup)
    return state


def uninstall(package_id):
    disable(package_id)
    removed = packages.uninstall(package_id)
    invalidate_caches()
    return removed


def apply_enabled():
    """启动时把已启用、仍安装着且兼容当前版本的包注册回去。"""
    problems = []
    for package_id in enabled_ids():
        if workspace_service.is_local(package_id):
            try:
                enable_local(package_id)
            except Exception as exc:
                problems.append("%s: %s" % (package_id, exc))
            continue
        if not packages.is_installed(package_id):
            continue
        entry = find_entry(package_id)
        if entry is not None and not entry.supports(bpy.app.version):
            continue
        try:
            translations = packages.load_translations(package_id)
            registry.register(package_id, translations, bilingual=bilingual_enabled(), separator=separator())
        except Exception as exc:
            problems.append("%s: %s" % (package_id, exc))
    return problems


def reapply():
    """双语开关等设置变化后，按 enabled 重新注册。"""
    registry.clear()
    return apply_enabled()


def cached_catalog():
    return update_check.load_cached()


def find_entry(package_id):
    catalog = cached_catalog()
    if catalog is None:
        return None
    for entry in catalog.entries:
        if entry.id == package_id:
            return entry
    return None


def download_url(entry):
    return update_check.raw_base().rstrip("/") + "/" + entry.url.lstrip("/")


class SyncJob:
    """后台刷新结果：目录状态，以及等主线程安装的下载内容。

    后台线程只做网络与磁盘读取；install/enable/redraw 都在主线程回调里执行，
    避免在 worker 线程里碰 bpy 数据。
    """

    __slots__ = ("result", "downloads", "errors")

    def __init__(self, result):
        self.result = result
        self.downloads = []  # [(entry, bytes)]
        self.errors = []  # 展示给用户的中文提示


def sync(force=False):
    """后台线程：刷新目录并下载需要的包，返回待安装任务（不碰 bpy 数据）。"""
    set_status("")
    result = update_check.refresh(force=force)
    job = SyncJob(result)
    if result.error or result.catalog is None:
        return job
    downloads, problems = download_updates()
    job.downloads.extend(downloads)
    job.errors.extend(problems)
    try:
        pack = download_blender_pack()
    except Exception as exc:  # 补缺包失败不影响已经下载好的更新
        job.errors.append("补缺包下载失败：%s" % exc)
    else:
        if pack is not None:
            job.downloads.append(pack)
    return job


def download_updates():
    """后台线程：下载所有待更新的包，返回 ([(entry, bytes)], [错误])。"""
    downloads, problems = [], []
    for entry in pending_updates():
        try:
            downloads.append((entry, net.fetch(download_url(entry)).data))
        except Exception as exc:
            problems.append("自动更新下载失败：%s" % exc)
    return downloads, problems


def download_blender_pack():
    """后台线程：下载主程序补缺包（首次联网，D15）；不需要时返回 None。"""
    if not bpy.app.online_access:
        return None
    entry = blender_pack_entry()
    if entry is None or packages.is_installed(entry.id):
        return None
    return entry, net.fetch(download_url(entry)).data


def apply_downloads(downloads):
    """主线程：安装并启用已下载的包，返回成功数量。"""
    updated = 0
    for entry, data in downloads:
        try:
            # 用户手动停用过的包只更新文件，不因为"自动更新"被重新启用
            install(entry, data, auto_enable=is_enabled(entry.id))
            updated += 1
        except Exception as exc:
            set_error("安装 %s 失败：%s" % (entry.name, exc))
    return updated


def apply_sync(job):
    """主线程：把后台刷新下载好的内容装好，返回更新数量。"""
    updated = apply_downloads(job.downloads)
    if updated:
        set_status("已自动更新 %d 个翻译" % updated)
    if job.errors:
        set_error(job.errors[0])
    return updated


def finish_sync(job, error=None):
    """主线程回调：报告刷新错误，并安装后台下载好的包。"""
    if error is not None:
        set_error("刷新目录失败：%s" % error)
        redraw()
        return 0
    if job is None:
        return 0
    if job.result.error:
        set_error("刷新目录失败：%s" % job.result.error)
    updated = apply_sync(job)
    redraw()
    return updated


def redraw():
    window_manager = bpy.context.window_manager
    if window_manager is None:
        return
    for window in window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            area.tag_redraw()


# 列表重绘会反复问 pending_updates（每条都要 stat），同样用短缓存 + 启停/安装时失效。
_UPDATES_CACHE = {"stamp": 0.0, "catalog": None, "value": []}
UPDATES_CACHE_TTL = 0.5


def invalidate_caches():
    """包状态变化后让列表缓存立刻失效。"""
    _UPDATES_CACHE.update(stamp=0.0, catalog=None, value=[])
    workspace_service.invalidate_local_cache()


def pending_updates():
    """已安装、版本可匹配、且目录里有更新版本的条目。"""
    catalog = cached_catalog()
    if catalog is None:
        return []
    now = time.monotonic()
    cache = _UPDATES_CACHE
    if (cache["stamp"] and cache["catalog"] is catalog
            and now - cache["stamp"] < UPDATES_CACHE_TTL):
        return list(cache["value"])
    result = []
    for entry in catalog.entries:
        if entry.kind not in ("addon", "blender"):
            continue
        if not packages.is_installed(entry.id):
            continue
        if not entry.supports(bpy.app.version):
            continue
        if packages.needs_update(entry.id, entry):
            result.append(entry)
    cache.update(stamp=now, catalog=catalog, value=result)
    return list(result)


def blender_pack_entry():
    """当前 Blender 版本可用的补缺包（有多个时取版本区间的最高者）。"""
    catalog = cached_catalog()
    if catalog is None:
        return None
    found = None
    for entry in catalog.entries:
        if entry.kind != "blender" or not entry.supports(bpy.app.version):
            continue
        if found is None or entry.updated_at > found.updated_at:
            found = entry
    return found


