"""偏好设置与译者工具窗口共用的选项块。"""

import bpy

from ..core import store
from ..services import translator, workspace


def draw_identity(layout, prefs):
    box = layout.box()
    box.label(text="译者身份", icon="USER")
    box.prop(prefs, "translator_name")


def draw_workspace(layout, prefs):
    box = layout.box()
    box.label(text="工作区目录", icon="FILE_FOLDER")
    box.prop(prefs, "workspace_path", text="")
    box.operator("pc.open_workspace", text="打开工作区目录", icon="FILE_FOLDER")


def draw_deepseek(layout, prefs):
    box = layout.box()
    box.label(text="DeepSeek", icon="SHADERFX")
    box.prop(prefs, "deepseek_key")
    box.prop(prefs, "deepseek_model")

    consent = box.row(align=True)
    consent.prop(prefs, "deepseek_ack")
    test = box.row(align=True)
    test.enabled = prefs.deepseek_ack
    test.operator("pc.test_deepseek", text="测试连接")

    hint = box.column(align=True)
    hint.scale_y = 0.8
    hint.label(text="API KEY 仅保存在偏好设置里，翻译时只上传原文和上下文。")
    if translator.LAST_TEST:
        box.label(text=translator.LAST_TEST, icon="CHECKMARK" if translator.LAST_TEST_OK else "ERROR")


def draw_cache(layout, prefs):
    box = layout.box()
    box.label(text="缓存区目录", icon="FILE_FOLDER")
    row = box.row(align=True)
    row.prop(prefs, "cache_path", text="")
    action = box.row(align=True)
    action.operator("wm.path_open", text="打开缓存区目录").filepath = store.data_dir()
