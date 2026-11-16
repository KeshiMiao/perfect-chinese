"""DeepSeek 批量翻译（需求 F7）。

隐私边界（D7 / F7）：只把 msgid、msgctxt 和用户自己填的风格提示发出去，
源码路径、插件名、元信息一律不上传。
"""

import json

from ..core import net

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-flash"
MODELS = ("deepseek-flash", "deepseek-v4-pro")
BATCH = 20
MAX_ITEMS = 400

SYSTEM = (
    "你是 Blender 界面的简体中文译者。把用户给的英文界面词条译成中文。"
    "要求：术语与 Blender 官方中文界面保持一致；保留占位符（%s、%d、{name}、%r 等）、"
    "快捷键、文件扩展名和程序标识符；产品名（Cycles、EEVEE、Principled BSDF 等）用官方译法或保留原文；"
    "译文简短，适合按钮、菜单和提示；不要添加解释或标点之外的任何内容。"
    "结合上下文判断词义：面板标题、按钮、属性名通常是动作或功能名，不要臆测成图案、材质名。"
    "同一批里术语保持一致（如 texel density → 纹素密度、UV island → UV 孤岛、heatmap → 热力图）。"
    "孤立的短词优先按界面动作或状态理解（Check 更像「检查」而不是「棋盘格」）。"
    "常用术语：viewport → 视图，outliner → 大纲视图，workspace → 工作区，modifier → 修改器，"
    "mesh → 网格，object → 物体，UV island → UV 孤岛，heatmap → 热力图。"
    "数学/节点运算名按功能翻译，不要译成实物：Ceiling → 向上取整，Floor → 向下取整，"
    "Round → 四舍五入，Truncate → 截断，Modulo → 取模。"
    '只输出 JSON：{"translations": [{"i": 1, "zh": "..."}]}，i 与输入编号对应。'
)


LAST_TEST = ""
LAST_TEST_OK = True


class TranslatorError(Exception):
    """翻译失败（网络、Key 或返回格式）。"""


def build_payload(items, model=DEFAULT_MODEL):
    """构造请求体；items 是 [{"msgid": ..., "msgctxt": ...}]。"""
    rows = [
        {"i": index + 1, "context": item.get("msgctxt") or "", "text": item["msgid"]}
        for index, item in enumerate(items)
    ]
    user = {"task": "translate", "items": rows}
    return {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
    }


def parse_response(data, count):
    """从返回体里取出 count 条译文，顺序与输入一致。"""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise TranslatorError("返回里没有 message.content") from None
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        payload = json.loads(text)
    except ValueError:
        raise TranslatorError("返回的不是 JSON") from None
    rows = payload.get("translations") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise TranslatorError("返回里没有 translations 数组")
    result = [None] * count
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("i")) - 1
        except (TypeError, ValueError):
            continue
        zh = row.get("zh")
        if 0 <= index < count and isinstance(zh, str) and zh.strip():
            result[index] = zh.strip()
    missing = [index + 1 for index, value in enumerate(result) if value is None]
    if missing:
        raise TranslatorError("有 %d 条没有译文（编号 %s）" % (len(missing), missing[:5]))
    return result


def translate(items, key, model=DEFAULT_MODEL, post=None, batch=BATCH, progress=None):
    """逐批翻译，返回与 items 等长的译文字符串列表。

    `post` 可注入，便于测试；默认用 core.net.post_json。
    """
    if not key.strip():
        raise TranslatorError("还没有填 DeepSeek API Key")
    if model not in MODELS:
        raise TranslatorError("不支持的模型：%s" % model)
    if len(items) > MAX_ITEMS:
        raise TranslatorError("一次最多 %d 条" % MAX_ITEMS)
    sender = post or net.post_json
    result = []
    for start in range(0, len(items), batch):
        chunk = items[start:start + batch]
        payload = build_payload(chunk, model=model)
        try:
            data = sender(API_URL, payload, headers={"Authorization": "Bearer %s" % key.strip()})
        except net.NetworkError as exc:
            raise TranslatorError(str(exc)) from None
        result.extend(parse_response(data, len(chunk)))
        if progress is not None:
            progress(len(result), len(items))
    return result
