# 完美中文（Perfect Chinese）

给 Blender 用的中文界面与插件汉化扩展。插件本体与翻译内容解耦：本仓库只放客户端，译文与目录在独立仓库
[perfect-chinese-translations](https://github.com/KeshiMiao/perfect-chinese-translations)。

## 功能

- **一键中英切换**：顶栏的【中文 / English】按钮，在 `zh_HANS` 与你的原语言之间切换，立即生效；工具提示、
  新建数据名、报告、工作区标题可一并联动，关掉插件时还原。
- **翻译列表**：搜索、下载、启用、更新、卸载；支持「仅启用 / 仅下载 / 待更新 / 仅本地」筛选，单项与全部更新。
- **主程序补缺包**：补齐 Blender 官方缺译的中文词条，按 4.5 与 5.x 分开；首次联网自动下载并启用。
- **本地译文**：工作区里的 `.po` 以【本地】条目并入列表，勾选即启用。
- **双语模式**：插件词条显示「译文 | 原文」，分隔符可配，默认关闭。
- **译者工具**（默认关闭）：3D 视图侧边栏的【译者工具】标签（【抽取】【翻译】【选项】三个面板），
  抽取插件文本、编辑译文、实时预览，可用 DeepSeek 自动翻译未译条目。

## 安装

支持 Blender **4.5 LTS 与 5.x**（最低 4.5.0）。

- 下载发布页的 zip，在 偏好设置 → 获取扩展 → 从磁盘安装。
- 或从源码安装：把 `perfect_chinese/` 放进 `extensions/user_default/`，也可以用
  `blender --command extension build` 打包后再安装。

装好后在 偏好设置 → 扩展 → 完美中文 里有三页：【翻译列表】【选项和配置】【更新和关于】。

## 使用

1. 打开 Blender 偏好设置的「联网访问」开关（默认关闭），再到【翻译列表】点【检查更新】拉取目录。
2. 勾选条目即启用，无需重启；顶栏【中文 / English】按钮切换中英。
3. 翻译缓存默认放在 Blender 用户数据目录，可在【选项和配置】里改到别处，清空即回默认。

翻译内容不在这个仓库；想补译或报错，请到
[perfect-chinese-translations](https://github.com/KeshiMiao/perfect-chinese-translations) 提 issue 或 PR。

## 许可

GPL-3.0-or-later，见 [LICENSE](LICENSE)。
