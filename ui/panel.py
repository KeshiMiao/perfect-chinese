"""3D 视图侧边栏：标签【译者工具】，下面三个独立面板（抽取 / 翻译 / 选项）。"""

import bpy

from ..core import env
from . import tools_pages

CATEGORY = "译者工具"


def _prefs():
    return env.addon_prefs()


def _visible(context):
    prefs = _prefs()
    return prefs is not None and prefs.translator_tools


class VIEW3D_PT_pc_extract(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY
    bl_label = "抽取"

    @classmethod
    def poll(cls, context):
        return _visible(context)

    def draw(self, context):
        tools_pages.draw_extract_page(self.layout, context)


class VIEW3D_PT_pc_translate(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY
    bl_label = "翻译"

    @classmethod
    def poll(cls, context):
        return _visible(context)

    def draw(self, context):
        tools_pages.draw_translate_page(self.layout, context)


class VIEW3D_PT_pc_options(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY
    bl_label = "选项"

    @classmethod
    def poll(cls, context):
        return _visible(context)

    def draw(self, context):
        tools_pages.draw_options_page(self.layout, context)


_classes = (
    VIEW3D_PT_pc_extract,
    VIEW3D_PT_pc_translate,
    VIEW3D_PT_pc_options,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
