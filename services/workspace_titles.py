"""工作区标题（顶部的布局/建模/雕刻……标签）翻译。

Blender 官方只翻译了部分工作区名，其余的没有对应条目。这里直接改工作区名，
把原名记到本地状态文件里，关闭中文界面时还原。
"""

import bpy

from ..core import env, store

TITLES = {
    "Layout": "布局",
    "Modeling": "建模",
    "Sculpting": "雕刻",
    "UV Editing": "UV编辑",
    "Texture Paint": "纹理绘制",
    "Shading": "着色",
    "Animation": "动画",
    "Rendering": "渲染",
    "Compositing": "合成",
    "Geometry Nodes": "几何节点",
    "Scripting": "脚本",
    "Video Editing": "视频编辑",
    "Motion Tracking": "运动追踪",
    "Masking": "遮罩",
}
REVERSE = {value: key for key, value in TITLES.items()}


def _path():
    return store.data_path("state", "workspace_titles.json")


def _load():
    data = store.read_json(_path(), {}) or {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def _save(mapping):
    store.write_json(_path(), mapping)


def _workspaces():
    """注册阶段 bpy.data 是受限的（_RestrictData），返回 None 让调用方稍后再试。"""
    try:
        return list(bpy.data.workspaces)
    except (AttributeError, RuntimeError):
        return None


def _defer():
    """注册时改不了工作区名，延后到一次事件循环之后再试。"""
    if _defer.pending:
        return
    _defer.pending = True

    def retry():
        _defer.pending = False
        prefs = env.addon_prefs()
        if prefs is not None and prefs.language_enabled:
            translate()
        return None

    bpy.app.timers.register(retry, first_interval=0.5)


_defer.pending = False


def translate():
    """把已知的英文工作区名改成中文，并记下原名。"""
    if env.view_prefs().language != "zh_HANS":
        return
    workspaces = _workspaces()
    if workspaces is None:
        _defer()
        return
    mapping = _load()
    names = {workspace.name for workspace in workspaces}
    for workspace in workspaces:
        name = workspace.name
        if name in REVERSE:
            # 旧版插件留下的中文名：补一条映射，方便还原。
            mapping.setdefault(name, REVERSE[name])
            continue
        title = TITLES.get(name)
        if title is None or title == name:
            continue
        if title in names:
            continue
        mapping[title] = name
        workspace.name = title
        names.discard(name)
        names.add(title)
    _save(mapping)


def restore():
    """把工作区名还原成英文。"""
    workspaces = _workspaces()
    if workspaces is None:
        return
    mapping = _load()
    for workspace in workspaces:
        name = workspace.name
        original = mapping.get(name) or REVERSE.get(name)
        if original and original != name:
            workspace.name = original
    _save({})
