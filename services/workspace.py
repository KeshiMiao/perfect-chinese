"""译者工作区：找得到源码的插件、抽取、预览。"""

import os
import time

import bpy

from ..core import env, registry, store, workspace


class WorkspaceError(Exception):
    """找不到源码或无法抽取。"""


def workspace_default():
    """默认工作区目录（缓存目录下的 workspace）。"""
    return store.data_dir("workspace")


def workspace_dir():
    prefs = env.addon_prefs()
    configured = getattr(prefs, "workspace_path", "") if prefs else ""
    if configured:
        return bpy.path.abspath(configured)
    return workspace_default()


def addon_entries():
    """当前能找到源码的插件：{module: path}。"""
    found = {}
    for repo in bpy.context.preferences.extensions.repos:
        directory = getattr(repo, "directory", "")
        if not directory or not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            path = os.path.join(directory, name)
            if name.startswith(".") or not os.path.isdir(path):
                continue
            found.setdefault("bl_ext.%s.%s" % (repo.module, name), path)
    for base in bpy.utils.script_paths(subdir="addons") or []:
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            if name.startswith((".", "_")) or not os.path.isdir(path):
                continue
            found.setdefault(name, path)
    return found


def source_path(module):
    return addon_entries().get(module)


def extract(module, translator=""):
    """抽取一个插件，写到工作区；返回 (抽取结果, 目标路径)。"""
    path = source_path(module)
    if path is None:
        raise WorkspaceError("找不到 %s 的源码目录" % module)
    if not workspace.has_source(path):
        raise WorkspaceError("%s 只有 .pyc，无法静态抽取" % module)
    target = workspace.po_path(workspace_dir(), module)
    if not translator:
        prefs = env.addon_prefs()
        translator = getattr(prefs, "translator_name", "") if prefs else ""
    meta = {
        "Project-Id-Version": module,
        "Last-Translator": translator,
        "PO-Revision-Date": time.strftime("%Y-%m-%d %H:%M%z"),
        "translator": translator,
    }
    result = workspace.write(path, target, module=module, meta=meta)
    invalidate_local_cache()
    return result, target


def preview(module):
    """把工作区里的译文注册成预览域，界面立即生效。"""
    target = workspace.po_path(workspace_dir(), module)
    if not os.path.exists(target):
        raise WorkspaceError("还没有抽取过 %s" % module)
    translations = workspace.summary(target)
    if not translations:
        raise WorkspaceError("%s 的工作区里还没有译文" % module)
    registry.register("preview-" + module, translations)
    return sum(len(items) for items in translations.values())


LOCAL_PREFIX = "local:"


def local_id(module):
    """工作区 .po 在列表里的 id：local:<模块名>，保留原始大小写。"""
    return LOCAL_PREFIX + str(module)


def is_local(package_id):
    return str(package_id).startswith(LOCAL_PREFIX)


def local_module(package_id):
    """id 里的模块名；兼容旧版本写的 local:<小写 slug> 形式。"""
    module = str(package_id)[len(LOCAL_PREFIX):]
    known = local_files()
    if module in known:
        return module
    for name in known:
        if workspace.slug(name) == module:
            return name
    return module


def _header_module(path):
    for line in workspace.read_header(path):
        text = line.lstrip("#").strip()
        if text.startswith("module:"):
            return text.split(":", 1)[1].strip()
    return ""


def local_files():
    """工作区里的 .po：{module: path}；模块名取自文件头，缺省用文件名。"""
    directory = workspace_dir()
    found = {}
    if not os.path.isdir(directory):
        return found
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".po"):
            continue
        path = os.path.join(directory, name)
        found[_header_module(path) or name[:-3]] = path
    return found


# 列表每帧重绘都会问一次本地条目；.po 解析 + sha256 太贵，用 0.5s 的短缓存，
# 抽取/保存/删除/启停时显式失效。
_LOCAL_CACHE = {"stamp": 0.0, "entries": []}
LOCAL_CACHE_TTL = 0.5


def invalidate_local_cache():
    _LOCAL_CACHE.update(stamp=0.0, entries=[])


def local_entries():
    now = time.monotonic()
    stamp = _LOCAL_CACHE["stamp"]
    if stamp and now - stamp < LOCAL_CACHE_TTL:
        return list(_LOCAL_CACHE["entries"])
    entries = _scan_local_entries()
    _LOCAL_CACHE.update(stamp=now, entries=entries)
    return list(entries)


def _scan_local_entries():
    """工作区里的 .po 转成列表条目（kind=local），带进度与译者。"""
    from ..core import catalog, po, store

    result = []
    for module, path in sorted(local_files().items()):
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            stat = os.stat(path)
        except OSError:
            continue
        entries = po.loads(text)
        done, total, _ratio = po.completeness(entries)
        meta = po.read_meta(text)
        result.append(catalog.Entry(
            id=local_id(module),
            name=module,
            url=os.path.basename(path),
            sha256=store.sha256_bytes(text.encode("utf-8")),
            translation_version=str(int(stat.st_mtime)),
            module=module,
            translator=meta.get("Last-Translator") or meta.get("translator", ""),
            category="本地",
            size=stat.st_size,
            updated_at=time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
            kind="local",
            entry_count=total,
            translated_count=done,
        ))
    return result


def find_local(package_id):
    for entry in local_entries():
        if entry.id == package_id:
            return entry
    return None


def local_summary(module):
    path = local_files().get(module)
    if path is None:
        raise WorkspaceError("工作区里找不到 %s 的 .po" % module)
    return workspace.summary(path)
