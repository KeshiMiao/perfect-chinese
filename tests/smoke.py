"""无头冒烟测试。

阶段 1：开启插件、切换语言、反复启用/禁用，最后停在"中文界面已开启"并保存偏好。
阶段 2：重启后验证中文界面自动生效（由 tests/run_smoke.sh 用同一份配置启动）。

用法：blender -b --python tests/smoke.py -- 1
"""

import os
import sys
import traceback

import bpy

ADDON = "bl_ext.user_default.perfect_chinese"


def _stage():
    for arg in reversed(sys.argv):
        if arg in ("1", "2", "3"):
            return arg
    return "1"


failures = []


def check(name, condition, detail=""):
    if condition:
        print("PASS | %s" % name)
        return
    message = "FAIL | %s%s" % (name, (" | " + detail) if detail else "")
    failures.append(message)
    print(message)


def stage_one(view):
    factory_reports = view.use_translate_reports
    check("factory 语言是 en_US", view.language == "en_US", view.language)
    check("存在 addon_show 运算符", "addon_show" in dir(bpy.ops.preferences))

    result = bpy.ops.preferences.addon_enable(module=ADDON)
    check("启用插件", result == {"FINISHED"}, str(result))

    addon = bpy.context.preferences.addons.get(ADDON)
    check("插件已登记", addon is not None)
    prefs = addon.preferences if addon else None
    check("偏好设置实例存在", prefs is not None)
    if prefs is None:
        return None
    check("面板类已注册", hasattr(bpy.types, "VIEW3D_PT_pc_extract"))
    check("首次运行自动切到中文", view.language == "zh_HANS", view.language)
    check("已记录自动启用", prefs.auto_enabled is True)

    prefs.language_enabled = True
    check("开启后为 zh_HANS", view.language == "zh_HANS", view.language)
    check("界面文案已翻译", bpy.app.translations.pgettext_iface("View") == "视图")
    check("报告翻译已打开", view.use_translate_reports is True)
    check("记住了原语言", prefs.previous_language == "en_US", prefs.previous_language)

    from bl_ext.user_default.perfect_chinese.core import registry

    registry.register("smoke", {"": {"PC Smoke Label": "冒烟"}})
    check("注册域生效", bpy.app.translations.pgettext_iface("PC Smoke Label") == "冒烟")
    registry.register("smoke", {"": {"PC Smoke Label": "冒烟"}}, bilingual=True)
    check("重复注册会替换", bpy.app.translations.pgettext_iface("PC Smoke Label") == "冒烟 | PC Smoke Label")
    registry.register("smoke2", {"Operator": {"PC Smoke Op": "冒烟操作"}})
    check("指定上下文生效", bpy.app.translations.pgettext("PC Smoke Op", "Operator") == "冒烟操作")
    check("运算符条目兜底默认上下文", bpy.app.translations.pgettext_iface("PC Smoke Op") == "冒烟操作")
    registry.register("smoke3", {"": {"PC Smoke Plain": "冒烟普通"}})
    check("默认条目不漏进 Operator", bpy.app.translations.pgettext("PC Smoke Plain", "Operator") == "PC Smoke Plain")
    registry.unregister("smoke")
    registry.unregister("smoke2")
    registry.unregister("smoke3")
    check("注销后回到原文", bpy.app.translations.pgettext_iface("PC Smoke Label") == "PC Smoke Label")
    check("注册域已清空", registry.active_ids() == ())

    from bl_ext.user_default.perfect_chinese.core import catalog, packages
    from bl_ext.user_default.perfect_chinese.services import translations

    check("偏好含三个标签页", [i.identifier for i in prefs.bl_rna.properties["tabs"].enum_items] == ["LIST", "OPTIONS", "UPDATE"])
    check("翻译列表已移出侧边栏", not hasattr(bpy.types, "VIEW3D_PT_perfect_chinese_translate"))
    check("偏好含搜索与双语", hasattr(prefs, "search") and hasattr(prefs, "bilingual"))
    check(
        "列表筛选是六选一",
        [i.identifier for i in prefs.bl_rna.properties["list_filter"].enum_items]
        == ["RECOMMEND", "ALL", "ENABLED", "DOWNLOADED", "UPDATABLE", "LOCAL"],
    )
    check("列表默认显示推荐", prefs.list_filter == "RECOMMEND", prefs.list_filter)
    check("偏好含缓存目录", hasattr(prefs, "cache_path"))
    check("存在全部更新运算符", "update_all" in dir(bpy.ops.pc))
    check("存在筛选运算符", "set_filter" in dir(bpy.ops.pc))
    check("偏好含 DeepSeek 设置", all(hasattr(prefs, name) for name in ("deepseek_key", "deepseek_model", "deepseek_ack")))
    check("DeepSeek 模型是 flash / pro", [i.identifier for i in prefs.bl_rna.properties["deepseek_model"].enum_items] == ["deepseek-flash", "deepseek-v4-pro"])
    check("不再有风格提示", not hasattr(prefs, "deepseek_style"))
    check("存在 DeepSeek 翻译与测试运算符", "deepseek" in dir(bpy.ops.pc) and "test_deepseek" in dir(bpy.ops.pc))
    check("存在更新版本运算符", "update_client" in dir(bpy.ops.pc))
    from bl_ext.user_default.perfect_chinese.services import client_update
    check("能认出当前扩展仓库", client_update.repo_id() == "user_default", client_update.repo_id())

    from bl_ext.user_default.perfect_chinese.core import official
    check("能读官方目录", official.catalog() is not None)
    check("官方目录命中 View", official.translated("View"))
    check("官方目录不命中 Add Cube", not official.translated("Add Cube"))
    from bl_ext.user_default.perfect_chinese.services import translations as tr
    check("错误状态接口可用", tr.last_error() == "" and callable(tr.set_error))

    import hashlib

    po_bytes = (
        'msgid ""\nmsgstr ""\n'
        '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        'msgid "PC Smoke Label"\nmsgstr "冒烟标签"\n'
    ).encode("utf-8")
    entry = catalog.Entry(
        id="smoke_pkg",
        name="Smoke",
        url="locale/smoke_pkg.po",
        sha256=hashlib.sha256(po_bytes).hexdigest(),
        translation_version="1",
    )
    state = translations.install(entry, po_bytes)
    check("安装后记录完整度", state["completeness"] == 1.0, str(state))
    check("安装后自动启用", translations.is_enabled("smoke_pkg"))
    check("安装的译文生效", bpy.app.translations.pgettext_iface("PC Smoke Label") == "冒烟标签")

    # 刷新拆成“后台下载 + 主线程安装”：用假的下载结果走一遍主线程安装路径
    def _po(text):
        return (
            'msgid ""\nmsgstr ""\n'
            '"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
            + text
        ).encode("utf-8")

    def _entry(package_id, name, data, version):
        return catalog.Entry(
            id=package_id,
            name=name,
            url="locale/%s.po" % package_id,
            sha256=hashlib.sha256(data).hexdigest(),
            translation_version=version,
        )

    sync_v1 = _po('msgid "PC Sync Label"\nmsgstr "同步标签"\n')
    sync_v2 = _po('msgid "PC Sync Label"\nmsgstr "同步标签2"\n')
    translations.install(_entry("smoke_sync", "Smoke Sync", sync_v1, "1"), sync_v1)
    job = translations.SyncJob(None)
    job.downloads.append((_entry("smoke_sync", "Smoke Sync", sync_v2, "2"), sync_v2))
    updated = translations.apply_sync(job)
    check("后台下载的包能在主线程装上", updated == 1 and translations.is_enabled("smoke_sync"))
    check("安装后新译文生效", bpy.app.translations.pgettext_iface("PC Sync Label") == "同步标签2")
    check("同步成功后留下状态", "已自动更新" in translations.last_status()[0])

    # 用户手动停用的包，自动更新只换文件，不能顺手重新启用
    off_v1 = _po('msgid "PC Off Label"\nmsgstr "停用标签"\n')
    off_v2 = _po('msgid "PC Off Label"\nmsgstr "停用标签2"\n')
    translations.install(_entry("smoke_off", "Smoke Off", off_v1, "1"), off_v1, auto_enable=False)
    job = translations.SyncJob(None)
    job.downloads.append((_entry("smoke_off", "Smoke Off", off_v2, "2"), off_v2))
    updated = translations.apply_sync(job)
    check("自动更新不重新启用已停用的包",
          updated == 1 and not translations.is_enabled("smoke_off") and packages.is_installed("smoke_off"))
    translations.finish_sync(None, RuntimeError("断网"))
    check("刷新失败会提示", "刷新目录失败" in translations.last_error())
    translations.uninstall("smoke_sync")
    translations.uninstall("smoke_off")

    # 更新失败不能删掉旧版本：给同一个 id 装一个没有可注册译文的坏包
    bad_bytes = (
        'msgid ""\nmsgstr ""\n\n'
        'msgid "PC Smoke Label"\nmsgstr ""\n'
    ).encode("utf-8")
    bad_entry = catalog.Entry(
        id="smoke_pkg",
        name="Smoke",
        url="locale/smoke_pkg.po",
        sha256=hashlib.sha256(bad_bytes).hexdigest(),
        translation_version="2",
    )
    try:
        translations.install(bad_entry, bad_bytes)
        check("坏包安装会失败", False, "没有抛异常")
    except Exception:
        check("坏包安装会失败", True)
    check("更新失败保留旧版本", packages.is_installed("smoke_pkg"))
    check("更新失败后旧译文仍生效", bpy.app.translations.pgettext_iface("PC Smoke Label") == "冒烟标签")
    check("更新失败不留下备份目录", not os.path.exists(packages.package_path("smoke_pkg") + ".bak"))
    prefs.bilingual = True
    check("双语注册生效", bpy.app.translations.pgettext_iface("PC Smoke Label") == "冒烟标签 | PC Smoke Label")
    prefs.bilingual = False
    check("关闭双语回到纯译文", bpy.app.translations.pgettext_iface("PC Smoke Label") == "冒烟标签")
    translations.disable("smoke_pkg")
    check("停用后回到原文", bpy.app.translations.pgettext_iface("PC Smoke Label") == "PC Smoke Label")
    translations.uninstall("smoke_pkg")
    check("卸载后已清理", not packages.is_installed("smoke_pkg"))

    from bl_ext.user_default.perfect_chinese.core import po as po_module
    from bl_ext.user_default.perfect_chinese.services import workspace

    check("能发现扩展源码", "bl_ext.user_default.perfect_chinese" in workspace.addon_entries())
    result, target = workspace.extract("bl_ext.user_default.perfect_chinese")
    check("抽取写出 .po", os.path.exists(target), target)
    check("抽取有词条", len(result.entries()) > 0, str(len(result.entries())))
    check("本地 id 保留模块大小写", workspace.local_module(workspace.local_id("EdgeFlow")) == "EdgeFlow")
    from bl_ext.user_default.perfect_chinese.ui import editor as editor_ui

    context_ids = [item[0] for item in editor_ui._context_items(None, None)]
    check("上下文“无”是有效枚举项", context_ids and context_ids[0] == "__none__", str(context_ids[:2]))
    from bl_ext.user_default.perfect_chinese.core import registry as registry_core

    check("注册域不会撞名", registry_core.domain_for("foo.bar") != registry_core.domain_for("foo-bar"))
    with open(target, encoding="utf-8") as handle:
        check("写出的 .po 可解析", len(po_module.loads(handle.read())) == len(result.entries()))
    check("侧边栏在关闭译者工具时隐藏", not bpy.types.VIEW3D_PT_pc_extract.poll(bpy.context))
    prefs.translator_tools = True
    check("侧边栏在开启译者工具时显示", bpy.types.VIEW3D_PT_pc_extract.poll(bpy.context))
    prefs.translator_tools = False
    check("偏好含语言联动开关", hasattr(prefs, "translate_tooltips") and hasattr(prefs, "header_button"))
    check("偏好含工作区搜索", hasattr(prefs, "workspace_search"))

    prefs.translate_tooltips = False
    check("关闭提示翻译立即生效", view.use_translate_tooltips is False)
    prefs.translate_tooltips = True
    check("恢复提示翻译", view.use_translate_tooltips is True)
    prefs.header_button = False
    check("顶栏按钮开关可读写", prefs.header_button is False)
    prefs.header_button = True
    check("偏好含译者字段", hasattr(prefs, "translator_tools") and hasattr(prefs, "workspace_path"))
    check("存在抽取运算符", "extract_texts" in dir(bpy.ops.pc))

    entries = po_module.loads(open(target, encoding="utf-8").read())
    entries[0].msgstr = "测试译文"
    smoke_header = (
        "# perfect-chinese: 1\n"
        "# module: bl_ext.user_default.perfect_chinese\n"
        "# name: Smoke Name\n\n"
    )
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(smoke_header + po_module.dumps(entries))
    try:
        count = workspace.preview("bl_ext.user_default.perfect_chinese")
        check("预览注册成功", count >= 1, str(count))
        check("预览文案生效", bpy.app.translations.pgettext_iface(entries[0].msgid) == "测试译文")
    finally:
        registry.unregister("preview-bl_ext.user_default.perfect_chinese")
    check("预览域已注销", not registry.registry.is_active("preview-bl_ext.user_default.perfect_chinese"))

    result_open = bpy.ops.pc.edit_texts(module="bl_ext.user_default.perfect_chinese")
    editor = bpy.context.scene.pc_editor
    check("编辑器打开", result_open == {"FINISHED"} and len(editor.items) == len(entries), str(result_open))
    from bl_ext.user_default.perfect_chinese.ui import editor as editor_ui
    check("回调用 RNA 指针认同一张表格", editor_ui.same_editor(editor, editor.module))
    check("换了文件就不算同一张表格", not editor_ui.same_editor(editor, "other.module"))
    check("旧编辑器面板已下线", not hasattr(bpy.types, "VIEW3D_PT_perfect_chinese_editor"))
    check("侧边栏三栏已注册", all(hasattr(bpy.types, name) for name in ("VIEW3D_PT_pc_extract", "VIEW3D_PT_pc_translate", "VIEW3D_PT_pc_options")))
    check("偏好含工作区标题开关", hasattr(prefs, "translate_workspaces"))
    check("词条带位置", bool(editor.items[0].locations))
    editor.items[0].msgstr = "编辑测试译文"
    result_save = bpy.ops.pc.save_editor()
    check("编辑器保存", result_save == {"FINISHED"}, str(result_save))
    with open(target, encoding="utf-8") as handle:
        saved = po_module.loads(handle.read())
    check("保存后仍可解析", len(saved) == len(entries))
    check("保存后预览生效", bpy.app.translations.pgettext_iface(editor.items[0].msgid) == "编辑测试译文")
    with open(target, encoding="utf-8") as handle:
        saved_text = handle.read()
    check("保存保留文件头", "# name: Smoke Name" in saved_text)

    # 外部追加的 obsolete 条目，保存后要原样保留
    with open(target, "a", encoding="utf-8") as handle:
        handle.write('\n#~ msgid "PC Smoke Gone"\n#~ msgstr "旧译文"\n')
    bpy.ops.pc.save_editor()
    with open(target, encoding="utf-8") as handle:
        saved_text = handle.read()
    check("保存保留 obsolete 条目", '#~ msgid "PC Smoke Gone"' in saved_text)
    check("obsolete 条目不进表格", all(item.msgid != "PC Smoke Gone" for item in editor.items))
    result_check = bpy.ops.pc.check_contexts()
    check("上下文自检可运行", result_check == {"FINISHED"}, str(result_check))
    check("自检结果正确", editor.items[0].context_ok)
    registry.unregister("edit-bl_ext.user_default.perfect_chinese")

    check("顶栏类可用", hasattr(bpy.types, "TOPBAR_HT_upper_bar"))

    prefs.language_enabled = False
    prefs.previous_language = ""
    view.language = "zh_HANS"
    bpy.ops.pc.toggle_language()
    check("不一致状态切回英文", view.language == "en_US", view.language)
    bpy.ops.pc.toggle_language()
    check("顶栏按钮再切回中文", view.language == "zh_HANS", view.language)
    check("工作区标题已翻译", any(w.name == "布局" for w in bpy.data.workspaces))

    prefs.language_enabled = False
    check("关闭后恢复原语言", view.language == "en_US", view.language)
    check("工作区标题已还原", any(w.name == "Layout" for w in bpy.data.workspaces))
    check("报告翻译已恢复", view.use_translate_reports == factory_reports, str(view.use_translate_reports))

    prefs.language_enabled = True
    bpy.ops.preferences.addon_disable(module=ADDON)
    check("卸载时恢复语言", view.language == "en_US", view.language)
    check("卸载后面板类已移除", not any(hasattr(bpy.types, name) for name in ("VIEW3D_PT_pc_extract", "VIEW3D_PT_pc_translate", "VIEW3D_PT_pc_options")))

    for attempt in range(2):
        bpy.ops.preferences.addon_enable(module=ADDON)
        check("重复启用 #%d" % (attempt + 1), bpy.context.preferences.addons.get(ADDON) is not None)

    from bl_ext.user_default.perfect_chinese.core import store

    check("缓存目录可创建", store.data_dir().endswith("perfect_chinese"), store.data_dir())
    custom = os.path.join(store.default_dir(), "custom-cache")
    store.set_root(custom)
    check("缓存目录可改", store.data_dir() == custom, store.data_dir())
    store.set_root("")

    prefs = bpy.context.preferences.addons[ADDON].preferences
    prefs.language_enabled = True
    check("退出前切换到中文", view.language == "zh_HANS", view.language)
    bpy.ops.wm.save_userpref()
    return prefs


def stage_two(view):
    prefs = bpy.context.preferences.addons.get(ADDON)
    check("重启后插件自动启用", prefs is not None)
    check("重启后自动应用中文", view.language == "zh_HANS", view.language)
    if prefs is None:
        return
    prefs = prefs.preferences
    check("重启后记住了原语言", prefs.previous_language == "en_US", prefs.previous_language)
    from bl_ext.user_default.perfect_chinese.core import registry

    registry.register("smoke", {"": {"PC Smoke Label": "冒烟"}})
    check("注册域生效", bpy.app.translations.pgettext_iface("PC Smoke Label") == "冒烟")
    registry.register("smoke", {"": {"PC Smoke Label": "冒烟"}}, bilingual=True)
    check("重复注册会替换", bpy.app.translations.pgettext_iface("PC Smoke Label") == "冒烟 | PC Smoke Label")
    registry.register("smoke2", {"Operator": {"PC Smoke Op": "冒烟操作"}})
    check("指定上下文生效", bpy.app.translations.pgettext("PC Smoke Op", "Operator") == "冒烟操作")
    check("运算符条目兜底默认上下文", bpy.app.translations.pgettext_iface("PC Smoke Op") == "冒烟操作")
    registry.register("smoke3", {"": {"PC Smoke Plain": "冒烟普通"}})
    check("默认条目不漏进 Operator", bpy.app.translations.pgettext("PC Smoke Plain", "Operator") == "PC Smoke Plain")
    registry.unregister("smoke")
    registry.unregister("smoke2")
    registry.unregister("smoke3")
    check("注销后回到原文", bpy.app.translations.pgettext_iface("PC Smoke Label") == "PC Smoke Label")
    check("注册域已清空", registry.active_ids() == ())

    prefs.language_enabled = False
    check("关闭后恢复原语言", view.language == "en_US", view.language)
    bpy.ops.wm.save_userpref()


def stage_three(view):
    """回归：界面本来就是中文的老用户，启用插件不应改语言，也不该重置翻译开关。"""
    view.language = "zh_HANS"
    view.use_translate_tooltips = True
    tooltips = view.use_translate_tooltips
    result = bpy.ops.preferences.addon_enable(module=ADDON)
    check("中文环境启用插件", result == {"FINISHED"}, str(result))
    check("启用后仍是中文", view.language == "zh_HANS", view.language)
    addon = bpy.context.preferences.addons.get(ADDON)
    prefs = addon.preferences if addon else None
    check("语言开关保持关闭", prefs is not None and prefs.language_enabled is False)
    check("未记录原语言", prefs is not None and prefs.previous_language == "", getattr(prefs, "previous_language", ""))
    check("工具提示开关未被重置", view.use_translate_tooltips is tooltips)
    bpy.ops.pc.toggle_language()
    check("中文界面下按钮能切到英文", view.language == "en_US", view.language)


def main():
    view = bpy.context.preferences.view
    try:
        stage = _stage()
        if stage == "1":
            stage_one(view)
        elif stage == "2":
            stage_two(view)
        else:
            stage_three(view)
    except Exception:
        traceback.print_exc()
        failures.append("异常中断")
    if failures:
        print("\n".join(failures))
        print("SMOKE RESULT: FAIL (%d)" % len(failures))
        sys.exit(1)
    print("SMOKE RESULT: PASS")


main()
