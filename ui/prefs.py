"""偏好设置。"""

import bpy

from ..core import env, store, versions
from ..services import language, translator, translations, update_check, workspace
from . import tools_options
from .list import draw_translation_list


REPO_URL = "https://github.com/KeshiMiao/perfect-chinese"
DISCUSSIONS_URL = "https://github.com/KeshiMiao/perfect-chinese/discussions"


def _reapply(self, context):
    translations.reapply()


def _reset_list_page(self, context):
    # 搜索词或筛选条件一变，原来停在第几页就没有意义了
    self.list_page = 1


def _cache_get(self):
    # 只读：用不创建目录的 default_path，避免"读一下设置"就把全新安装变成老用户
    return self.cache_stored or store.default_path()


def _cache_set(self, value):
    self.cache_stored = (value or "").strip() or store.default_root()


def _cache_changed(self, context):
    store.set_root(self.cache_path)
    # 缓存目录换了，当前会话的注册表还指向旧目录：按新目录重新注册一次
    try:
        translations.reapply()
    except Exception:
        pass


def _workspace_get(self):
    return self.workspace_stored or workspace.workspace_default()


def _workspace_set(self, value):
    self.workspace_stored = (value or "").strip() or workspace.workspace_default()


class PerfectChinesePreferences(bpy.types.AddonPreferences):
    bl_idname = env.ADDON_ID

    language_enabled: bpy.props.BoolProperty(
        name="启用翻译",
        description="把界面语言切换为简体中文（zh_HANS），关闭时恢复原语言",
        default=False,
        update=lambda self, context: language.on_toggle(self),
    )
    auto_enabled: bpy.props.BoolProperty(
        name="首次已自动启用",
        description="第一次启用插件时是否已经自动打开过中文界面；用户之后手动关闭不再自动打开",
        default=False,
        options={"HIDDEN"},
    )
    previous_language: bpy.props.StringProperty(
        name="原语言",
        description="开启中文界面前的语言，关闭时用于恢复",
        default="",
        options={"HIDDEN"},
    )
    previous_translate_reports: bpy.props.BoolProperty(
        name="原报告翻译设置",
        default=False,
        options={"HIDDEN"},
    )
    previous_translate_tooltips: bpy.props.BoolProperty(
        name="原工具提示翻译设置",
        default=False,
        options={"HIDDEN"},
    )
    previous_translate_new_dataname: bpy.props.BoolProperty(
        name="原数据名翻译设置",
        default=False,
        options={"HIDDEN"},
    )
    translate_tooltips: bpy.props.BoolProperty(
        name="工具提示",
        default=True,
        update=lambda self, context: language.on_toggle(self),
    )
    translate_new_dataname: bpy.props.BoolProperty(
        name="新建数据",
        default=True,
        update=lambda self, context: language.on_toggle(self),
    )
    translate_reports: bpy.props.BoolProperty(
        name="报告",
        default=True,
        update=lambda self, context: language.on_toggle(self),
    )
    translate_workspaces: bpy.props.BoolProperty(
        name="工作区标题",
        description="把顶部的工作区标签（布局、建模、雕刻……）也换成中文，关闭时还原",
        default=True,
        update=lambda self, context: language.on_toggle(self),
    )
    header_button: bpy.props.BoolProperty(
        name="顶栏按钮",
        description="在 3D 视图顶栏显示中英切换按钮",
        default=True,
    )
    search: bpy.props.StringProperty(
        name="搜索翻译",
        description="按原名、中文名、模块名、译者或分类过滤翻译列表",
        default="",
        update=_reset_list_page,
    )
    list_page: bpy.props.IntProperty(
        name="页码",
        description="翻译列表当前显示第几页；搜索或筛选变化时回到第一页",
        default=1,
        min=1,
        options={"HIDDEN"},
    )
    expanded_packages: bpy.props.StringProperty(
        description="已展开的条目 id，空格分隔；只用来记住折叠状态",
        default="",
        options={"HIDDEN"},
    )
    list_filter: bpy.props.EnumProperty(
        name="筛选",
        description="选择翻译列表显示哪一类条目",
        items=[
            ("RECOMMEND", "推荐", "已下载或已启用的译文、已安装插件的译文、本地自译"),
            ("ALL", "全部", "目录里的全部译文"),
            ("ENABLED", "仅启用", "当前已启用的译文"),
            ("DOWNLOADED", "仅下载", "已经下载到本机的译文"),
            ("UPDATABLE", "待更新", "已下载且目录里有新版本的译文"),
            ("LOCAL", "仅本地", "译者工具产出的本地译文"),
        ],
        default="RECOMMEND",
        update=_reset_list_page,
    )
    cache_stored: bpy.props.StringProperty(
        description="缓存区目录的实际存储值；空值时界面回填默认目录",
        default="",
        options={"HIDDEN"},
    )
    cache_path: bpy.props.StringProperty(
        name="缓存区目录",
        description="翻译缓存与工作区的存放位置；清空会回到默认目录",
        subtype="DIR_PATH",
        get=_cache_get,
        set=_cache_set,
        update=_cache_changed,
    )
    bilingual_separator: bpy.props.StringProperty(
        name="双语分隔符",
        description="译文与原文之间的分隔符，默认竖线加空格",
        default=" | ",
        update=_reapply,
    )
    translator_tools: bpy.props.BoolProperty(
        name="译者工具",
        description="在 3D 视图侧边栏显示【译者工具】标签，里面是抽取、翻译、选项三个面板；只对译者有意义",
        default=False,
    )
    workspace_stored: bpy.props.StringProperty(
        description="工作区目录的实际存储值；空值时界面回填默认目录",
        default="",
        options={"HIDDEN"},
    )
    workspace_path: bpy.props.StringProperty(
        name="工作区目录",
        description="每个插件一份 .po 的存放目录；清空会回到缓存目录下的 workspace",
        get=_workspace_get,
        set=_workspace_set,
        subtype="DIR_PATH",
    )
    workspace_search: bpy.props.StringProperty(
        name="搜索插件",
        description="按模块名过滤可抽取的插件",
        default="",
    )
    translator_name: bpy.props.StringProperty(
        name="译者昵称",
        description="抽取译文时自动填进 .po 文件头的 Last-Translator 与 translator",
        default="",
    )
    deepseek_key: bpy.props.StringProperty(
        name="API KEY",
        description="DeepSeek API KEY，保存在 Blender 偏好设置里；不上传到别处",
        subtype="PASSWORD",
        default="",
    )
    deepseek_model: bpy.props.EnumProperty(
        name="选择模型",
        description="Flash 快、便宜；Pro 更强、更贵",
        items=[
            ("deepseek-flash", "deepseek-flash", "速度快、价格低，适合批量翻译"),
            ("deepseek-v4-pro", "deepseek-v4-pro", "理解更好、价格更高，适合难句和术语"),
        ],
        default="deepseek-flash",
    )
    deepseek_ack: bpy.props.BoolProperty(
        name="同意调用 DeepSeek 翻译插件",
        description="翻译时会把原文与上下文发给 DeepSeek，会产生 API 费用",
        default=False,
    )
    bilingual: bpy.props.BoolProperty(
        name="双语模式",
        description="译文后面附带英文原文，便于核对；只影响插件翻译，不影响界面语言",
        default=False,
        update=_reapply,
    )

    tabs: bpy.props.EnumProperty(
        items=[
            ("LIST", "翻译列表", "已收录的插件翻译"),
            ("OPTIONS", "选项和配置", "界面语言与译者工具设置"),
            ("UPDATE", "更新和关于", "版本、更新检查与缓存位置"),
        ],
        name="选项卡",
        default="LIST",
    )

    def draw(self, context):
        layout = self.layout
        tabs_row = layout.row(align=True)
        tabs_row.prop(self, "tabs", expand=True)
        layout.separator(factor=0.5)

        if self.tabs == "LIST":
            draw_translation_list(layout, self)
        elif self.tabs == "OPTIONS":
            self._draw_options(layout)
        else:
            self._draw_update(layout)

    def _draw_options(self, layout):
        language_box = layout.box()
        language_box.label(text="界面语言", icon="WORLD")

        common_caption = language_box.column(align=True)
        common_caption.label(text="常规选项：")
        common_grid = language_box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        common_grid.prop(self, "language_enabled")
        common_grid.prop(self, "header_button")

        bilingual_row = common_grid.row(align=True)
        bilingual_row.alignment = "LEFT"
        bilingual_row.prop(self, "bilingual")
        if self.bilingual:
            bilingual_row.prop(self, "bilingual_separator", text="分隔符")

        range_caption = language_box.column(align=True)
        range_caption.label(text="翻译范围：")
        range_grid = language_box.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        range_grid.prop(self, "translate_tooltips")
        range_grid.prop(self, "translate_reports")
        range_grid.prop(self, "translate_new_dataname")
        range_grid.prop(self, "translate_workspaces")

        tools_box = layout.box()
        tools_box.label(text="译者工具", icon="TOOL_SETTINGS")

        tools_toggle_row = tools_box.row(align=True)
        tools_toggle_row.alignment = "LEFT"
        tools_toggle_row.prop(self, "translator_tools")
        if self.translator_tools:
            tools_options.draw_identity(tools_box, self)
            tools_options.draw_deepseek(tools_box, self)
            tools_options.draw_workspace(tools_box, self)

        tools_options.draw_cache(layout, self)

    def _draw_update(self, layout):
        update_box = layout.box()
        update_box.label(text="插件更新", icon="SORT_DESC")
        version_row = update_box.row()
        version_row.label(text="当前版本： %s" % env.addon_version())
        result = update_check.CLIENT_RESULT
        if result.get("error"):
            update_box.label(text="检查失败：%s" % result["error"], icon="ERROR")
        elif result.get("latest"):
            if versions.compare(result["latest"], env.addon_version()) > 0:
                update_box.label(text="有新版本 %s" % result["latest"], icon="SORT_DESC")
            else:
                update_box.label(text="已是最新版本", icon="CHECKMARK")
        update_actions = update_box.row(align=True)
        update_actions.operator("pc.check_client_update", text="检查更新", icon="URL")
        update_actions.operator("pc.open_release_page", text="打开发布页", icon="BLENDER")

        about_box = layout.box()
        about_box.label(text="关于", icon="INFO")
        about_row = about_box.row(align=True)
        about_row.label(text="完美中文")
        about_row.label(text="作者：KeshiMiao")
        about_links = about_box.row(align=True)
        about_links.operator("wm.url_open", text="GitHub 仓库", icon="URL").url = REPO_URL
        about_links.operator("wm.url_open", text="GitHub 讨论", icon="URL").url = DISCUSSIONS_URL


def register():
    bpy.utils.register_class(PerfectChinesePreferences)


def unregister():
    bpy.utils.unregister_class(PerfectChinesePreferences)
