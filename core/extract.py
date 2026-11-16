"""从插件源码抽取可翻译字符串（静态 AST，不导入插件）。

只做静态能看见的部分：类属性、函数调用里的字面量、枚举项、`bl_info`。
拼接/f-string 这类动态文本记入 problems，交给译者手工补（见需求 D11）。
"""

import ast
import os
import re

from . import po

IGNORED_DIRS = {"__pycache__", ".git", ".hg", ".svn", "node_modules"}
LABEL_ATTRS = ("bl_label", "bl_description", "bl_category")
PROP_KINDS = (
    "StringProperty", "BoolProperty", "IntProperty", "FloatProperty", "EnumProperty",
    "PointerProperty", "CollectionProperty", "FloatVectorProperty", "IntVectorProperty",
    "StringVectorProperty", "BoolVectorProperty",
)
PGETEXT = {
    "pgettext": "",
    "pgettext_iface": "",
    "pgettext_tip": "Tooltip",
    "pgettext_data": "",
}
ID_LIKE = re.compile(r"^[a-z0-9][a-z0-9_.:-]*$")
MAX_LENGTH = 500


class Candidate:
    __slots__ = ("msgid", "msgctxt", "locations")

    def __init__(self, msgid, msgctxt):
        self.msgid = msgid
        self.msgctxt = msgctxt
        self.locations = []


class Extraction:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.candidates = {}
        self.problems = []
        self.files = []
        self.meta = {}

    def add(self, msgid, msgctxt, path, line):
        msgid = (msgid or "").strip()
        if not msgid or len(msgid) > MAX_LENGTH or ID_LIKE.match(msgid):
            return
        key = (msgctxt, msgid)
        candidate = self.candidates.get(key)
        if candidate is None:
            candidate = Candidate(msgid, msgctxt)
            self.candidates[key] = candidate
        location = "%s:%d" % (os.path.relpath(path, self.root), line)
        if location not in candidate.locations:
            candidate.locations.append(location)

    def problem(self, path, line, text):
        self.problems.append("%s:%d %s" % (os.path.relpath(path, self.root), line, text))

    def scan(self):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(name for name in dirnames if name not in IGNORED_DIRS and not name.startswith("."))
            for name in sorted(filenames):
                if name.endswith(".py"):
                    self.files.append(os.path.join(dirpath, name))
        if not self.files:
            self.problem(self.root, 0, "没有可读的 .py 源码，可能只有 .pyc（不可抽取）")
            return self
        for path in self.files:
            self._scan_file(path)
        return self

    def _scan_file(self, path):
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as handle:
                source = handle.read()
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            self.problem(path, exc.lineno or 0, "语法错误：%s" % exc.msg)
            return
        _Visitor(self, path).visit(tree)

    def entries(self):
        result = []
        for key in sorted(self.candidates):
            candidate = self.candidates[key]
            entry = po.POEntry()
            entry.msgctxt, entry.msgid = candidate.msgctxt, candidate.msgid
            entry.locations = list(candidate.locations)
            result.append(entry)
        return result


def _constants(node):
    """收集表达式里的字符串常量，跳过 f-string（拼出来的文本无法整体翻译）。"""
    if isinstance(node, ast.JoinedStr):
        return
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
        return
    for child in ast.iter_child_nodes(node):
        for item in _constants(child):
            yield item


def _constant(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _enum_item(node):
    """把 ("id", "Label", "Description") 识别成枚举项；不像就返回 None。"""
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) < 2:
        return None
    key = _constant(node.elts[0])
    label = _constant(node.elts[1])
    description = _constant(node.elts[2]) if len(node.elts) > 2 else None
    if key is None or label is None:
        return None
    key = key.strip()
    if not (1 <= len(key) <= 64) or any(ch.isspace() for ch in key) or "/" in key:
        return None
    label = label.strip()
    if not (1 <= len(label) <= 200):
        return None
    description = (description or "").strip() or None
    return label, description


class _Visitor(ast.NodeVisitor):
    def __init__(self, extraction, path):
        self.x = extraction
        self.path = path

    def visit_ClassDef(self, node):
        bases = [_dotted(base) for base in node.bases]
        is_operator = any(base == "Operator" or base.endswith(".Operator") for base in bases)
        context = "Operator" if is_operator else ""
        for item in node.body:
            if isinstance(item, ast.Assign) and len(item.targets) == 1:
                target = item.targets[0]
                if isinstance(target, ast.Name) and target.id in LABEL_ATTRS:
                    value = _constant(item.value)
                    if value is not None:
                        self.x.add(value, context, self.path, item.lineno)
        self.generic_visit(node)

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "bl_info" and isinstance(node.value, ast.Dict):
                self._bl_info(node.value, node.lineno)
        # 枚举项经常先存成模块级常量再传给 items=，这里也收一遍。
        if isinstance(node.value, (ast.List, ast.Tuple)):
            self._items(node.value, quiet=True)
        elif isinstance(node.value, ast.Dict):
            self._item_dict(node.value)
        self.generic_visit(node)

    def _bl_info(self, node, line):
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            meta_key = key.value
            text = _constant(value)
            if meta_key in ("name", "description", "category") and text is not None:
                self.x.add(text, "", self.path, line)
                if meta_key == "name":
                    self.x.meta["name"] = text
            elif meta_key == "version" and isinstance(value, ast.Tuple):
                parts = [
                    item.value if isinstance(item, ast.Constant) and isinstance(item.value, int) else None
                    for item in value.elts
                ]
                if parts and all(part is not None for part in parts):
                    self.x.meta["version"] = ".".join(str(part) for part in parts)

    def visit_Call(self, node):
        name = _dotted(node.func)
        short = name.rsplit(".", 1)[-1]
        # 按钮文字：Blender 画 operator 按钮时按 "Operator" 上下文查，所以 text= 也要登记到该上下文。
        text_context = "Operator" if name.endswith(".operator") else ""

        if short in PGETEXT:
            self._pgettext(node, short)
        elif short == "report":
            self._report(node)
        elif name.startswith("bpy.props.") or short in PROP_KINDS:
            self._props(node)
        else:
            for keyword in node.keywords:
                if keyword.arg == "text":
                    self._text(node, keyword, text_context)
                elif keyword.arg == "items":
                    self._items(keyword.value)
        self.generic_visit(node)

    def _pgettext(self, node, short):
        # bpy.app.translations.pgettext(msgid, msgctxt=None)：文本在前，上下文在后。
        if not node.args:
            return
        text = _constant(node.args[0])
        if text is None:
            self.x.problem(self.path, node.lineno, "pgettext 的文本不是字面量")
            return
        context = PGETEXT[short]
        if len(node.args) > 1:
            extra = _constant(node.args[1])
            if extra is None:
                self.x.problem(self.path, node.lineno, "pgettext 的上下文不是字面量")
            else:
                context = extra
        self.x.add(text, context, self.path, node.lineno)

    def _report(self, node):
        if len(node.args) < 2:
            return
        text = _constant(node.args[1])
        if text is None:
            self.x.problem(self.path, node.lineno, "self.report 的文本不是字面量")
            return
        self.x.add(text, "", self.path, node.lineno)

    def _props(self, node):
        for keyword in node.keywords:
            if keyword.arg not in ("name", "description"):
                continue
            text = _constant(keyword.value)
            if text is None:
                self.x.problem(self.path, node.lineno, "属性 %s 不是字面量" % keyword.arg)
                continue
            self.x.add(text, "", self.path, node.lineno)
        for keyword in node.keywords:
            if keyword.arg == "items":
                self._items(keyword.value, quiet=True)

    def _text(self, node, keyword, context=""):
        text = _constant(keyword.value)
        if text is not None:
            self.x.add(text, context, self.path, node.lineno)
            return
        # 三元表达式之类仍可能含可翻译字面量，例如 text="Remove" if on else "Add"。
        found = list(_constants(keyword.value))
        for literal in found:
            self.x.add(literal, context, self.path, node.lineno)
        if found:
            self.x.problem(self.path, node.lineno, "text= 含动态文本，只抽取了其中的字面量")
        else:
            self.x.problem(self.path, node.lineno, "text= 不是字面量（动态文本）")

    def _items(self, node, quiet=False):
        if not isinstance(node, (ast.List, ast.Tuple)):
            if not quiet:
                self.x.problem(self.path, node.lineno, "items= 不是字面量（动态枚举项）")
            return
        for item in node.elts:
            if isinstance(item, ast.Dict):
                self._item_dict(item)
                continue
            pair = _enum_item(item)
            if pair is None:
                continue
            label, description = pair
            if label is not None:
                self.x.add(label, "", self.path, item.lineno)
            if description is not None:
                self.x.add(description, "", self.path, item.lineno)

    def _item_dict(self, node):
        """{"ID": ("Label", "Description")} 或 {"ID": {"label": ..., "description": ...}} 形式。"""
        if not isinstance(node, ast.Dict):
            return
        for key, value in zip(node.keys, node.values):
            text = _constant(key)
            if text is None or not ID_LIKE.match(text.strip()):
                continue
            if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) >= 2:
                label = _constant(value.elts[0])
                description = _constant(value.elts[1]) if len(value.elts) > 1 else None
            elif isinstance(value, ast.Dict):
                fields = {}
                for sub_key, sub_value in zip(value.keys, value.values):
                    name = _constant(sub_key)
                    if name in ("label", "description"):
                        fields[name] = _constant(sub_value)
                label = fields.get("label")
                description = fields.get("description")
            else:
                continue
            if label is not None:
                self.x.add(label, "", self.path, node.lineno)
            if description is not None:
                self.x.add(description, "", self.path, node.lineno)


def extract(root):
    return Extraction(root).scan()


def merge(existing, entries):
    """把已有译文合并进抽取结果：译文保留，找不到的旧条目标为 obsolete。"""
    mapping = {(item.msgctxt, item.msgid): item for item in existing}
    result = []
    for entry in entries:
        old = mapping.pop((entry.msgctxt, entry.msgid), None)
        if old is not None:
            entry.msgstr = old.msgstr
            entry.msgid_plural = old.msgid_plural
            entry.plurals = dict(old.plurals)
            entry.fuzzy = old.fuzzy
        result.append(entry)
    for old in mapping.values():
        old.obsolete = True
        result.append(old)
    return result


HEADER_FIRST = "perfect-chinese: 1"


def render(entries, module="", source="", name="", header=None, meta=None):
    """写回 .po；已有文件头（id、category 等）优先保留，不写入本地源码路径。"""
    lines = [__import__("re").sub(r"^#\s?", "", line) for line in (header or [])]
    keys = {}
    for line in lines:
        match = __import__("re").match(r"([a-z_]+)\s*:\s*(.+)$", line)
        if match:
            keys[match.group(1)] = match.group(2).strip()
    if keys:
        lines = [line for line in lines if not __import__("re").match(r"([a-z_]+)\s*:", line)]
        if module:
            keys["module"] = module
        if name:
            keys["name"] = name
        lines = [HEADER_FIRST] + ["%s: %s" % (key, value) for key, value in keys.items() if key != "source"]
        header_lines = lines
    else:
        header_lines = [HEADER_FIRST]
        if module:
            header_lines.append("module: %s" % module)
        if name:
            header_lines.append("name: %s" % name)
    return po.dumps(entries, header=header_lines, meta=meta)


def load_existing(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        return po.loads(handle.read())
