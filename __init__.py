"""完美中文 —— Blender 中文界面与插件汉化。

插件本体只负责发现、安装、更新、启用翻译，翻译内容放在独立仓库。
"""

import bpy

from .core import env, net, registry, store
from .services import language, translations
from .ui import editor, header, ops, panel, prefs

_modules = (prefs, panel, editor, ops, header)
_timer = [None]
_save_timer = [None]


def _startup_sync():
    """后台慢慢检查一次目录，不阻塞启动。"""
    _timer[0] = None
    net.run_in_background(translations.sync, translations.finish_sync)
    return None


def _save_prefs_soon():
    """注册阶段存偏好可能没有窗口上下文，等一轮事件循环再补存一次。"""
    _save_timer[0] = None
    try:
        language.save_prefs()
    except Exception:
        pass
    return None


def register():
    for module in _modules:
        module.register()
    prefs = env.addon_prefs()
    store.set_root(getattr(prefs, "cache_path", "") if prefs is not None else "")
    if language.ensure_first_run_default():
        _save_timer[0] = bpy.app.timers.register(_save_prefs_soon, first_interval=1.5)
    language.apply_from_prefs()
    translations.apply_enabled()
    _timer[0] = bpy.app.timers.register(_startup_sync, first_interval=3.0)


def unregister():
    for slot in (_timer, _save_timer):
        if slot[0] is not None:
            try:
                bpy.app.timers.unregister(slot[0])
            except ValueError:
                pass
            slot[0] = None
    registry.clear()
    try:
        language.restore_on_unload()
    except Exception:
        # 缓存目录只读时也可能在这里失败，不能因此中断后续模块注销
        pass
    for module in reversed(_modules):
        module.unregister()
