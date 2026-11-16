"""官方中文目录查询：避免把 Blender 已经译好的词条再翻一遍。"""

import gettext
import os

_catalog = None
_loaded_path = None


def mo_path():
    import bpy

    version = "%d.%d" % tuple(bpy.app.version[:2])
    base = bpy.utils.resource_path("LOCAL")
    return os.path.join(base, "datafiles", "locale", "zh_HANS", "LC_MESSAGES", "blender.mo")


def load(path=None):
    """读取官方 .mo，返回 GNUTranslations；读不到时返回 None。"""
    path = path or mo_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as handle:
            return gettext.GNUTranslations(handle)
    except (OSError, EOFError, ValueError):
        return None


def catalog(path=None):
    """带缓存的官方目录。"""
    global _catalog, _loaded_path
    path = path or mo_path()
    if _catalog is None or _loaded_path != path:
        _catalog = load(path)
        _loaded_path = path
    return _catalog


def translated(msgid, msgctxt="", table=None):
    """官方是否已有这条译文（按精确上下文判断）。"""
    table = table if table is not None else catalog()
    if table is None or not msgid:
        return False
    # gettext 内部的键是 "msgctxt\x04msgid"，只能走 pgettext/gettext，不能直接翻 _catalog
    text = table.pgettext(msgctxt, msgid) if msgctxt else table.gettext(msgid)
    return bool(text) and text != msgid


