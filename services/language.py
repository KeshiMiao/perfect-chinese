"""界面语言切换。

只做两件事：把界面语言换成 zh_HANS 并记住原语言；关闭时还原。
状态落在偏好设置里，跨会话保留。
"""

import os

import bpy

from ..core import env, store
from . import workspace_titles

ZH_HANS = "zh_HANS"
FALLBACK_LANGUAGE = "en_US"


def _tag_redraw():
    window_manager = bpy.context.window_manager
    if window_manager is None:
        return
    for window in window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            area.tag_redraw()


def set_language(language):
    view = env.view_prefs()
    if view.language == language:
        return False
    view.language = language
    _tag_redraw()
    return True


def _remember(prefs, view):
    """记下切换前的语言与三个翻译开关，关闭时原样还原。"""
    prefs.previous_language = view.language
    prefs.previous_translate_reports = view.use_translate_reports
    prefs.previous_translate_tooltips = view.use_translate_tooltips
    prefs.previous_translate_new_dataname = view.use_translate_new_dataname


def enable(prefs):
    view = env.view_prefs()
    if not prefs.previous_language:
        # 第一次由本插件切换：原语言就是当前语言。
        # 界面本来就是中文时会记成 zh_HANS，之后关掉开关只会还原开关，不会把人踢去英文。
        _remember(prefs, view)
    elif view.language != ZH_HANS and view.language != prefs.previous_language:
        # 插件开着的时候用户手动换了界面语言：以最新的选择为准。
        _remember(prefs, view)
    set_language(ZH_HANS)
    view.use_translate_reports = bool(getattr(prefs, "translate_reports", True))
    view.use_translate_tooltips = bool(getattr(prefs, "translate_tooltips", True))
    view.use_translate_new_dataname = bool(getattr(prefs, "translate_new_dataname", True))
    if getattr(prefs, "translate_workspaces", True):
        workspace_titles.translate()
    _tag_redraw()


def disable(prefs):
    previous = prefs.previous_language
    if not previous:
        # 没有记录过原语言：本插件从未改过界面，什么都别动。
        return
    view = env.view_prefs()
    if previous != ZH_HANS and view.language == ZH_HANS:
        set_language(previous)
    view.use_translate_reports = bool(prefs.previous_translate_reports)
    view.use_translate_tooltips = bool(prefs.previous_translate_tooltips)
    view.use_translate_new_dataname = bool(prefs.previous_translate_new_dataname)
    workspace_titles.restore()
    prefs.previous_language = ""
    _tag_redraw()


def save_prefs():
    """把开关状态写进 userpref，重启后才记得住。"""
    try:
        bpy.ops.wm.save_userpref()
    except Exception:
        pass


def on_toggle(prefs):
    apply(prefs)
    save_prefs()


def apply(prefs):
    if prefs.language_enabled:
        if not getattr(prefs, "translate_workspaces", True):
            workspace_titles.restore()
        enable(prefs)
    elif prefs.previous_language:
        # 只有确实由本插件切换过（记录过原语言）才还原；
        # 不能因为"界面现在是中文"就当成插件改过的状态，否则中文用户一启用就被切回英文。
        disable(prefs)


def apply_from_prefs():
    prefs = env.addon_prefs()
    if prefs is not None:
        apply(prefs)


def _has_previous_install():
    """缓存目录已经存在，说明这台机器之前跑过本插件。"""
    candidates = [store.default_path()]
    override = store.root()
    if override:
        candidates.append(os.path.abspath(os.path.expanduser(override)))
    return any(os.path.isdir(path) for path in candidates)


def ensure_first_run_default():
    """全新安装时自动打开中文界面，省得新手找不到开关。

    老用户升级不受影响：旧版本一运行就会建缓存目录，所以目录已存在就不动语言设置。
    检测必须在任何写入之前做——default_dir() 会创建目录，这里只用不创建的 default_path()。
    标记写进偏好设置，用户之后手动关掉中文，再次启动也不会被强行打开。
    返回 True 表示这次写入了标记，调用方需要把偏好补存一次。
    """
    prefs = env.addon_prefs()
    if prefs is None or prefs.auto_enabled:
        return False
    prefs.auto_enabled = True
    if not prefs.language_enabled and not _has_previous_install():
        # 赋值会触发 update 回调（on_toggle）：立即切换语言，并尝试保存偏好。
        prefs.language_enabled = True
    return True


def restore_on_unload():
    prefs = env.addon_prefs()
    if prefs is not None and prefs.language_enabled:
        disable(prefs)
