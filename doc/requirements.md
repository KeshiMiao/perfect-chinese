# 完美中文 · 重构需求（v1.0）

- 状态：v1.0 定稿（2026-11-14）。只定义"要什么"，不展开"怎么做"；实现期的取舍以本文为准，变更在此登记。
- 支持：Blender 4.5 LTS 与 5.x（最低 4.5.0），locale 固定 `zh_HANS`。
- 验证：4.5.15 LTS、5.2.4 LTS 实跑；官方词条差异由两版自带 `.mo` 比对得出。

## 1. 目标与边界

- 一句话：插件本体与翻译内容解耦。客户端只负责发现、安装、更新、启用翻译，并提供译者工具。
- 本仓库：客户端插件（内置译者工具，默认关闭）。
- 独立仓库：翻译内容 + 单一目录 JSON + CI。翻译可单独发版，不必等插件。
- `.po` 仍是唯一载体（兼容 Poedit / Weblate）。
- 重写方式：在当前仓库覆盖重写，保留仓库地址、issue 与 star。
- 不为 4.4 及更早版本保留兼容代码。

## 2. 平台事实（实测，违反即 bug）

| 项目 | 4.5.15 LTS | 5.2.4 LTS |
| --- | --- | --- |
| 语言标识 / locale | `zh_HANS` | `zh_HANS` |
| 覆盖官方已有译文 | 不能 | 不能 |
| `bpy.app.online_access` | 有（默认关） | 有（默认关） |
| `use_translate_reports` | 有 | 有 |
| 扩展 API（manifest / `extension_path_user`） | 有 | 有 |
| 官方中文词条数 | 36,560 | 39,343 |

1. **locale 必须是 `zh_HANS`**：`view.language` 与 `bpy.app.translations.locale` 都是它；`zh_Hans`、`zh_CN` 一律不生效。
2. **注册只是兜底**：`bpy.app.translations.register(domain, {locale: {(msgctxt, msgid): 译文}})`；官方已有译文的词条永远优先（两版都无法用 `blender` 域覆盖 `Add Cube`）。
3. **上下文是封闭集合**：`bpy.app.translations.contexts` 共 60 个，含 `Operator`、ID 类型名等，**没有 `Property`**；上下文不匹配时没有回退（实测默认上下文与 `Operator` 互不命中）。所以只能"猜对"，且必须自检命中。
4. **同名域不能重复注册**：第二次 `register` 直接抛 `ValueError`（`translations message cache already contains some data for addon ...`）。
5. **空译文 = 空白**：注册值为空串时界面显示空白（实测），空 `msgstr` 必须跳过。
6. **官方词条随版本变化**：4.5 独有 1,714 条、5.2 独有 4,497 条，共用 34,846 条。补缺包不能一份通用。
7. **网络开关**：联网前必须检查 `bpy.app.online_access`（默认关闭）；扩展形态需声明 `[permissions] network`。
8. **打包**：4.5 / 5.x 都支持 legacy 与 extension；对外只发 extension（`blender_version_min = "4.5.0"`）。

## 3. 已定决策

- D1 内容与客户端分离：单一目录 JSON 放在独立翻译项目，翻译独立更新。
- D2 补缺包也走下载，不内置。
- D3 译者工具内置于客户端，默认关闭。
- D4 一键切换 = 切换 `language`（记住并恢复原语言），覆盖 `use_translate_reports`。
- D5 支持 4.5 LTS 与 5.x。
- D6 msgctxt 自动推断（只能用既有上下文），漏掉的可人工补。
- D7 DeepSeek Key 存 Blender 偏好设置（明文、不在插件目录），界面掩码显示。
- D8 双语只做插件词条，补缺包不双语。
- D9 "更新检查"而非"自更新"：客户端只提示 + 打开下载页，不做下载替换。
- D10 上架 extensions.blender.org，商店渠道的更新交给 Blender。
- D11 抽取：静态 AST + RNA，目标 ≥95%，动态字符串标记待补。
- D12 启动后静默检查、每天最多一次；翻译自动更新，客户端只提示。
- D13 译者工具支持实时预览（防抖重建注册域）。
- D14 默认自动启用匹配翻译；完整度 < 80% 标黄，不拦截。
- D15 补缺包按 Blender 版本拆包（`blender-4.5`、`blender-5.x`），首次联网自动下载并启用。
- D16 结构重写，不沿用旧结构。
- D17 在当前仓库覆盖重写。
- D18 旧版共存检测 + 一次性迁移脚本。
- D19 信任锚：GitHub 为权威目录源，Gitee 只镜像文件；`sha256` 只防传输损坏，两源冲突以 GitHub 为准。
- D20 内容发布：只发布译文及其对应的原文，不随包分发插件本体；视为对作者的宣传，默认发布；收到作者异议（邮件或 issue）即刻下架对应条目并记录。

## 4. 功能需求

### F1 一键切换中英
- 顶栏入口，可关闭。
- 在 `zh_HANS` 与用户原语言之间切换，切换后立即重绘，不重启。
- 写 `view.language` 会持久化：需在首次切换前记录原语言；用户手动改过语言后，以当前值为准重新记忆。
- `DEFAULT` / `zh_HANT` 不做特殊处理：原语言是它们时，仍按"记录 → 恢复"处理。
- 联动开关可配置：工具提示 / 新建数据名 / 报告。

### F2 补缺官方翻译
- 只补官方缺译词条，不覆盖已有译文；与插件翻译包分开开关。
- 按 Blender 版本拆包：`blender-4.5`、`blender-5.x`，用 `supported_versions` 命中当前 `bpy.app.version`。
- 首次联网自动下载并启用；离线或未开网络时标"待下载"，不报错。

### F3 翻译源与目录
- 单一目录 JSON，由独立仓库 CI 生成；客户端拉取 → 缓存 → 离线可浏览搜索。
- GitHub 权威、Gitee 镜像同一批文件（D19）；目录本身不在两处各自生成。
- 目录缓存 24h + ETag；命中缓存时不发请求。
- 新条目入库署名即可，不设前置授权（D20）。

### F4 搜索 / 安装 / 更新 / 卸载
- 搜索维度：原名、译名、模块名、作者、分类。
- 安装 = 下载 `.po` → 校验 → 落盘 → 注册；失败回滚，不影响已装版本。
- 更新 = 比较 `translation_version`，支持单条与全部；不自动降级。
- 卸载 = 删文件 + 注销，不影响其他条目。
- 启用 = 已下载 + 已注册；目录刷新时，已安装插件对应的翻译自动下载并注册（可单条禁用）。
- 完整度 = 非空 `msgstr` 条目数 ÷ 全部非 obsolete 条目数（fuzzy 计为未翻）。
- 状态必须区分：已启用 / 未下载 / 版本不匹配 / 不完整 / 插件未安装。

### F5 双语模式
- 译文后拼接原文，默认分隔符 `" | "`，可配置；默认关闭；只作用于插件翻译包。
- 只覆盖我们提供的词条：官方已译的（如 `Cancel`）仍是单语，同一面板可能出现中英混排，首次开启时提示一次。
- 已知代价：文案变长、窄面板溢出。

### F6 本地翻译工作区
- 用户可配置目录，每个插件一个子目录。
- 从"源码可读"的插件抽取文本，生成 `.po`（含 msgctxt、源码位置）；只有 `.pyc` 的插件标记"不可抽取"。
- 工作区可纳入 git，便于协作与提 PR。
- 编辑时实时预览：保存即反映到界面（防抖重建注册域）。

### F7 DeepSeek 自动翻译
- 自带 Key + `online_access` 开启时可用；只翻未翻译条目，支持整包与单条。
- 上传白名单：仅 `msgid`、`msgctxt`、用户填写的风格提示；不上传源码、路径、插件元信息。
- Key 存偏好设置（会随配置备份），输入掩码，提供"清除/更换"；首次使用提示费用与隐私。
- 可选术语表 / 风格提示。

### F8 Blender 内手动翻译
- 表格视图：原文、译文、上下文、状态；搜索、只看未翻译、就地编辑保存。
- 实时预览（同 F6），并显示当前完整度。
- 保存时自检：逐条用对应上下文查一次，未命中的标"上下文可能不对"。
- 不做完整 CAT（记忆库、批量预翻）——后续。

### F9 匹配与兼容
- 以**模块名**为主键（legacy `EdgeFlow`；extension `bl_ext.<repo>.<pkg>`）；显示名只用于展示与搜索。
- `module: "blender"` 特例：主程序补缺包，始终视为匹配。
- 同一插件存在多份时（legacy + extension，或多条命中）：extension 优先；同分取 `translation_version` 高者。
- 版本用简化区间（§6）；插件升级后失配 → 保留已装翻译、标"可能不兼容"，允许强制启用。

### F10 更新检查
- 一个入口同时显示：客户端版本、目录版本、翻译版本。
- 客户端：上架后由 Blender 更新；非商店渠道只"检查 + 打开下载页"（D9）。
- 翻译/目录：自动检查与更新，无需重启（D12）。

### F11 旧版共存与迁移
- 启动时检测"legacy 目录 + 扩展目录"两份安装，提示卸载旧版并给出路径，避免重复注册。
- 迁移脚本只做一次性转换：旧文件名的第 2 段是**显示名**（如 `3D Navigation`），不是模块 id（`space_view3d_3d_navigation`），需要产出"插件 → 模块 id"的人工确认表。
- 补缺包不转换：丢弃 2.83 时代的 `blender.po`，按当前 Blender 的官方 `.mo` 重新生成。
- 旧配置与本地 `.po` 不自动继承；卸载时注销全部注册域、可选保留本地翻译。

### F12 网络与失败策略
- 所有请求：`online_access` 门禁 → 连接/读取超时 → 最多重试 2 次（指数退避）→ 总预算约 15s。
- 镜像回退：GitHub 失败（403 / 429 / 5xx / 超时）切 Gitee，反之亦然；单条失败不阻塞其他条目。
- 首启无缓存：界面正常可用，显示"未连接"与"待下载"，不阻塞启动。
- 网络在后台线程执行，主线程只收结果，避免卡界面。
- 离线：只读缓存；所有本地操作（启用已下载包、译者工具）照常可用。

## 5. 非目标

- 覆盖 / 强制替换官方译文（代码级 patch）。
- 除中文外的多语言界面（双语除外）。
- 自定义第三方源、云端协作、Weblate 托管、翻译记忆库。
- Blender < 4.5。

## 6. 数据契约

### 目录 JSON（单文件，CI 生成）
```json
{
  "schema_version": 1,
  "generated_at": "2026-11-01T00:00:00Z",
  "entries": [{
    "id": "edgeflow",
    "module": "EdgeFlow",
    "name": "Edge Flow",
    "name_zh": "边流动",
    "translator": "可是",
    "category": "建模",
    "locale": "zh_HANS",
    "translation_version": "1.2.0",
    "supported_versions": ">=0.5.0 <1.0.0",
    "url": "locale/edgeflow.po",
    "sha256": "…",
    "bytes": 12345,
    "updated_at": "2026-10-30"
  }]
}
```

### 翻译文件头（替代文件名里的元信息）
```
# perfect-chinese: 1
# id: edgeflow
# module: EdgeFlow
# name: Edge Flow
# name_zh: 边流动
# translator: 可是
# translation_version: 1.2.0
# supported_versions: >=0.5.0 <1.0.0
# updated_at: 2026-10-30

msgid ""
msgstr ""
"Language: zh_HANS\n"
"Content-Type: text/plain; charset=UTF-8\n"
```

### 校验与信任
- 缺必填字段、`sha256` 不符、超过 512 KB、locale 不是 `zh_HANS` → 拒绝该条。
- `id` 形如 `[a-z0-9][a-z0-9._-]*`，即文件名（`blender-4.5.po` 这类含点也允许），不含路径。
- 空 `msgstr` 跳过；obsolete 条目忽略；fuzzy 计为未翻。
- `sha256` 校验的是"文件是否完整"，不是"内容是否可信"：v1 信任 GitHub 目录，不做签名；签名列为后续。

### 版本语义
- `translation_version` 由译者/CI 维护，内容有任何改动必须递增；只改 `sha256` 而版本不变 = 热修，允许覆盖但要在 UI 提示。
- 区间支持 `*`、`X.Y.Z`、比较符组合（`>=` `>` `<=` `<` `==`，空格分隔为 AND）；不实现 `^`、`~`、`||`。

## 7. 现状问题（重构动机）

- `modules/utils.py:15` 路径拼写错误 `setttings`；配置写在插件目录内。
- `modules/localization/__init__.py:44` 用 `file[:-3].split("#")` 从文件名拆元信息：名字含 `#` 即崩，且第 2 段是显示名而非模块名。
- `modules/localization/localization.py:20` 硬编码 `zh_CN`；解析器用正则，把 `msgid_plural` 当成新的 `msgid`（单数词条丢失），忽略 fuzzy / obsolete，未跳过空 `msgstr`。
- `modules/operators/translation.py:15` 语言判断用 `zh_CN`；语义上是切开关而非切语言。
- `__init__.py:2` 名称拼写 `Prefect Chinese`；`__init__.py:6` 仍声明 `2.83.0`。
- `modules/ui/panel.py:45` 侧边栏面板 `draw` 为空实现，运行时反复注册/注销面板。
- `addon_updater.py` / `addon_updater_ops.py` 共 3,183 行 vendored 代码，与主线功能耦合。
- `modules/preferences.py` 单文件 360 行，更新器 UI、列表渲染、过滤逻辑混在一起。

## 8. 技术方向（不展开）

- 纯标准库；`urllib` + 超时/重试；无第三方依赖。
- 合并成少数自有注册域（补缺包、插件包各一个），词条优先级由我们 merge 决定，不依赖域注册顺序这种内部行为。
- 注册域增删走"先 unregister 再 register"，失败回滚到旧字典。
- 自写宽容版 `.po` 解析器（复数、obsolete、fuzzy、空 `msgstr`）。
- 缓存写 `bpy.utils.user_resource('DATAFILES', ...)`，不写插件目录；原子写 + `sha256`。
- 抽取：静态 AST + RNA 反射 + 上下文推断；f-string / 运行时拼接无法静态覆盖。
- 测试：`blender -b --python` 无头跑；CI 覆盖 4.5 与 5.x。

## 9. 项目结构（提案）

原则：core 不依赖 UI，UI 只调用服务；不用类属性充当全局状态；**类只在启动时注册一次**，运行时只增删"注册域"。

```text
perfect_chinese/
├── blender_manifest.toml     # 扩展清单（blender_version_min = "4.5.0"）
├── __init__.py               # 只有 register / unregister
├── core/                     # 无 UI 逻辑
│   ├── env.py                # 版本、语言、已装插件探测
│   ├── net.py                # 超时/重试/镜像回退/online_access 门禁
│   ├── catalog.py            # 目录加载、校验、搜索
│   ├── versions.py           # 版本区间
│   ├── po.py                 # .po 读写（宽容解析、跳过空 msgstr）
│   ├── registry.py           # 注册域增删、双语拼接、优先级
│   ├── store.py              # 本地路径、原子写、sha256
│   ├── packages.py           # 已安装包与完整度
│   └── extract.py            # AST + RNA 抽取
├── services/
│   ├── update_check.py       # 客户端版本检查 + 目录刷新
│   ├── translator.py         # DeepSeek（分批、重试、用量提示）
│   └── workspace.py          # 译者工作区
├── ui/
│   ├── prefs.py              # 偏好设置分页
│   ├── translate.py          # 汉化列表（搜索 / 安装 / 更新）
│   ├── translator/           # 译者工具（常驻注册，按开关显隐）
│   └── ops/                  # Operator 按域拆分
├── data/sources.json         # 内置源端点（GitHub / Gitee）
├── tests/                    # 无头测试入口与用例
└── doc/
```

- 删除：`addon_updater*.py`、`datafiles/`、`auto_load.py`；旧 `.po` 一次性转换后迁走。
- 状态集中到少量运行时对象；偏好设置用 `PropertyGroup`，Key 单独存放。

## 10. 验收口径

- 抽取：固定抽样清单（≥10 个源码可读插件），覆盖率 = 命中 msgid 数 ÷ 静态可识别 msgid 数，≥95%；`.pyc` 插件标"不可抽取"不算失败。
- 完整度：按 F4 公式；同一文件两次计算结果一致。
- 注册域：反复开关不抛 `ValueError`；关闭后界面立即回到原文；双语切换无需重启。
- 网络：断网启动不弹错、不阻塞；单条下载失败不影响其他条目；镜像 403/429 时 5s 内切换。
- 迁移：除补缺包外，21 个旧插件翻译迁移后条目数不减少。

## 11. 尚未展开

- 目录签名方案（v1 不做，但要留字段扩展位）。
- DeepSeek 默认模型、分批大小、限速与成本估算方式。
- 术语表格式（JSON / CSV / 纯文本）。
- 分类体系：沿用现有中文分类，还是对齐 Blender 官方 tag。
- 下架流程：异议渠道的响应时限、下架后目录与已安装副本的处理（D20）。

## 12. 里程碑（粗）

1. M0 结构重建：按 §9 搭骨架、4.5/5.x 适配、`zh_HANS`、移除旧更新器。
2. M1 客户端核心：源与目录、网络策略、安装/更新/卸载、双语。
3. M2 内容迁移：旧 `.po` → 新仓 + 文件头 + 目录 CI + 补缺包按版本生成。
4. M3 译者工作区 + 抽取。
5. M4 DeepSeek 接入。
6. M5 发布：扩展打包、文档、迁移说明。
