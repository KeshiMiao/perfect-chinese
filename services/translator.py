"""DeepSeek 批量翻译（需求 F7）。

隐私边界（D7 / F7）：只把 msgid、msgctxt 和用户自己填的风格提示发出去，
源码路径、插件名、元信息一律不上传。
"""

import json

from ..core import net

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-flash"
MODELS = ("deepseek-flash", "deepseek-v4-pro")
BATCH = 500

# 一次请求的译文再加 JSON 包装，输出 token 很容易超过模型默认的 4096；
# 按估算体积再切小，宁可多请求几次，也不让返回被截断、白花 token。
OUTPUT_BUDGET = 3500

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


def _request(sender, chunk, key, model):
    """发一批；网络错误包成 TranslatorError，返回解析后的译文。"""
    payload = build_payload(chunk, model=model)
    try:
        data = sender(API_URL, payload, headers={"Authorization": "Bearer %s" % key.strip()})
    except net.NetworkError as exc:
        raise TranslatorError(str(exc)) from None
    return parse_response(data, len(chunk))


def _splittable(exc):
    """模型输出被截断（少条目 / 不是 JSON）或超时时，可以拆小重试。"""
    text = str(exc)
    return (
        "没有译文" in text
        or "不是 JSON" in text
        or "没有 translations" in text
        or "超时" in text
        or "timed out" in text.lower()
    )


def _estimate(item):
    """粗略估算一条译文占的输出字符数（含 JSON 的 i/zh 包装）。"""
    return len(item.get("msgid") or "") + len(item.get("msgctxt") or "") + 16


def _plan_chunks(items, max_items=BATCH, max_chars=OUTPUT_BUDGET):
    """按条数上限与输出体积切批：条数多或词条长都会自动多切几批。"""
    pending = []
    start = 0
    size = 0
    for index, item in enumerate(items):
        cost = _estimate(item)
        if index > start and (index - start >= max_items or size + cost > max_chars):
            pending.append((start, index))
            start, size = index, 0
        size += cost
    if start < len(items):
        pending.append((start, len(items)))
    return pending


def translate(items, key, model=DEFAULT_MODEL, post=None, batch=BATCH, progress=None):
    """自动分批翻译，返回与 items 等长的译文字符串列表。

    每批最多 batch 条；一批的输出被截断时对半拆开重试，所以条数不设上限。
    `post` 可注入，便于测试；默认用 core.net.post_json。
    """
    if not key.strip():
        raise TranslatorError("还没有填 DeepSeek API Key")
    if model not in MODELS:
        raise TranslatorError("不支持的模型：%s" % model)
    if post is None:
        def sender(url, payload, headers=None):
            # 按体积切小后每批约 40–80 条，120 秒足够；超时会被拆得更小重试
            return net.post_json(url, payload, headers=headers, timeout=120)
    else:
        sender = post
    result = [None] * len(items)
    pending = _plan_chunks(items, max_items=batch)
    done = 0
    while pending:
        start, end = pending.pop(0)
        chunk = items[start:end]
        try:
            texts = _request(sender, chunk, key, model)
        except TranslatorError as exc:
            if end - start > 1 and _splittable(exc):
                middle = (start + end) // 2
                pending.insert(0, (middle, end))
                pending.insert(0, (start, middle))
                continue
            raise
        for index, text in zip(range(start, end), texts):
            result[index] = text
        done += end - start
        if progress is not None:
            progress(done, len(items))
    return result
