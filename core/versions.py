"""版本区间。

支持 `*`、裸版本号（前缀匹配）、比较符组合（空格分隔视为 AND）：
`>=4.5.0 <5.0.0`。不支持 `^`、`~`、`||`。
"""

OPERATORS = (">=", "<=", "==", ">", "<")


def parse_version(text):
    """'4.5' -> (4, 5)，'4.5.16' -> (4, 5, 16)；也接受元组。"""
    if isinstance(text, (tuple, list)):
        return tuple(int(part) for part in text)
    cleaned = str(text).strip()
    if cleaned[:1] in ("v", "V"):
        cleaned = cleaned[1:]
    if not cleaned:
        raise ValueError("空版本号")
    return tuple(int(part) for part in cleaned.split("."))


def _pad(left, right):
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)), right + (0,) * (width - len(right))


def compare(left, right):
    """返回 -1 / 0 / 1。"""
    left, right = _pad(parse_version(left), parse_version(right))
    return (left > right) - (left < right)


def _satisfies(target, operator, bound):
    result = compare(target, bound)
    return {
        ">=": result >= 0,
        "<=": result <= 0,
        "==": result == 0,
        ">": result > 0,
        "<": result < 0,
    }[operator]


def _is_prefix(target, prefix):
    target, prefix = parse_version(target), parse_version(prefix)
    return target[: len(prefix)] == prefix


def matches(spec, version):
    """判断 version 是否落在 spec 描述的区间内。spec 非法时抛 ValueError。"""
    if spec is None:
        return True
    text = str(spec).strip()
    if not text or text == "*":
        return True
    for token in text.split():
        operator = next((item for item in OPERATORS if token.startswith(item)), None)
        if operator is not None:
            if not _satisfies(version, operator, token[len(operator):]):
                return False
        elif not _is_prefix(version, token):
            return False
    return True
