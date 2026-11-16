"""本地缓存与文件写入。

约定：所有缓存写在 Blender 的 DATAFILES 目录，不写插件目录。
"""

import hashlib
import json
import os
import tempfile

ADDON_DIRNAME = "perfect_chinese"

# 用户在偏好设置里指定的缓存目录；空字符串表示用 Blender 默认位置。
_override = ""


def set_root(path):
    global _override
    _override = (path or "").strip()


def root():
    return _override


def default_path():
    """默认缓存目录的路径（不创建，可用于判断是不是全新安装）。"""
    import bpy

    return bpy.utils.user_resource("DATAFILES", path=ADDON_DIRNAME, create=False) or ""


def default_dir():
    import bpy

    return bpy.utils.user_resource("DATAFILES", path=ADDON_DIRNAME, create=True)


def default_root():
    """默认缓存根目录（不受用户覆盖影响）。"""
    return default_dir()


def data_dir(*parts):
    """返回缓存目录（或它的子目录），必要时创建。"""
    if _override:
        base = os.path.abspath(os.path.expanduser(_override))
        os.makedirs(base, exist_ok=True)
    else:
        base = default_dir()
    if not parts:
        return base
    path = os.path.join(base, *parts)
    os.makedirs(path, exist_ok=True)
    return path


def data_path(*parts):
    """返回缓存目录下的文件路径（父目录会创建）。"""
    return os.path.join(data_dir(*parts[:-1]), parts[-1])


def atomic_write(path, data):
    """先写同目录临时文件再替换，避免中断留下半个文件。"""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def read_json(path, default=None):
    try:
        with open(path, "rb") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()
