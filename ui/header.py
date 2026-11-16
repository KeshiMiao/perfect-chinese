"""顶栏的中英切换按钮（位置沿用旧版：顶栏左侧，可在偏好设置里关闭）。"""

import bpy

from ..core import env
from ..services import language


def draw_header(self, context):
    prefs = env.addon_prefs()
    if prefs is None or not prefs.header_button:
        return
    if context.region.alignment == "RIGHT":
        return
    chinese = env.view_prefs().language == language.ZH_HANS
    # 按钮写"点了会切到哪"：中文界面下显示 English，英文界面下显示中文
    self.layout.operator(
        "pc.toggle_language",
        text="English" if chinese else "中文",
    )


def register():
    bpy.types.TOPBAR_HT_upper_bar.append(draw_header)


def unregister():
    bpy.types.TOPBAR_HT_upper_bar.remove(draw_header)
