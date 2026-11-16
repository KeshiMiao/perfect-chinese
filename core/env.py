"""运行环境探测：界面语言、插件自身标识与版本号。"""

import pathlib
import tomllib

# 扩展形态下模块名是 bl_ext.<repo>.<id>，兼容旧式 perfect_chinese。
ADDON_ID = __package__.rpartition(".")[0]


def view_prefs():
    import bpy

    return bpy.context.preferences.view


def current_language():
    return view_prefs().language


def use_translate_reports():
    return view_prefs().use_translate_reports


def addon_version():
    """从清单读取版本号，清单是唯一权威。"""
    manifest = pathlib.Path(__file__).resolve().parent.parent / "blender_manifest.toml"
    try:
        with manifest.open("rb") as handle:
            return tomllib.load(handle).get("version", "0.0.0")
    except (OSError, tomllib.TOMLDecodeError):
        return "0.0.0"


def addon_prefs():
    import bpy

    addon = bpy.context.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon else None
