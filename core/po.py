"""宽容版 .po 解析与写回。

只做注册与统计需要的事：单数/复数、msgctxt、fuzzy、obsolete、空 msgstr。
故意不实现 PO 的全部语法（例如格式化参数校验）。
"""

import re

_FIELD = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+"(.*)"$')
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


class POEntry:
    __slots__ = ("msgctxt", "msgid", "msgid_plural", "msgstr", "plurals", "fuzzy", "obsolete", "line", "locations")

    def __init__(self, line=0):
        self.msgctxt = ""
        self.msgid = ""
        self.msgid_plural = ""
        self.msgstr = ""
        self.plurals = {}
        self.fuzzy = False
        self.obsolete = False
        self.line = line
        self.locations = []

    @property
    def translated(self):
        if self.fuzzy or self.obsolete or not self.msgid:
            return False
        if self.msgid_plural:
            # 中文通常只有一个复数形式，msgstr[0] 是必需的，其余序号有就必须非空。
            return 0 in self.plurals and all(self.plurals.values())
        return bool(self.msgstr)

    @property
    def plural(self):
        return bool(self.msgid_plural)

    def value(self):
        """注册用的值：单数返回字符串，复数返回按序号的元组。"""
        if self.msgid_plural:
            return tuple(self.plurals[index] for index in sorted(self.plurals))
        return self.msgstr


def _unescape(text):
    out = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            out.append(_ESCAPES.get(following, "\\" + following))
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def loads(text):
    """解析 .po 文本，返回条目列表（不含文件头；obsolete 条目会保留并标记）。"""
    if text.startswith("\ufeff"):
        text = text[1:]
    entries = []
    entry = POEntry()
    last = None
    skipping = False

    def flush():
        nonlocal entry
        if entry.msgid or entry.msgctxt:
            entries.append(entry)
        entry = POEntry()

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("#~"):
            # 旧版 gettext 的注释条目：#~ msgid "..." 仍然要解析，写回时再还原成 #~
            entry.obsolete = True
            line = line[2:].strip()
            if not line:
                continue
        if not line:
            flush()
            skipping = False
            last = None
            continue
        if line.startswith("#:"):
            entry.locations.extend(line[2:].split())
            continue
        if line.startswith("#"):
            if "fuzzy" in line:
                entry.fuzzy = True
            continue
        if skipping:
            continue
        if line.startswith('"'):
            if last is None:
                continue
            field, index = last
            chunk = _unescape(line[1:-1])
            if field == "msgctxt":
                entry.msgctxt += chunk
            elif field == "msgid":
                entry.msgid += chunk
            elif field == "msgid_plural":
                entry.msgid_plural += chunk
            elif field == "msgstr":
                entry.msgstr += chunk
            else:
                entry.plurals[index] = entry.plurals.get(index, "") + chunk
            continue

        match = _FIELD.match(line)
        if match is None:
            skipping = True
            last = None
            continue
        name, index, chunk = match.groups()
        if name == "msgctxt":
            if entry.msgid:
                flush()
            entry.msgctxt = _unescape(chunk)
            last = ("msgctxt", None)
        elif name == "msgid":
            if entry.msgid:
                flush()
            entry.msgid = _unescape(chunk)
            entry.line = number
            last = ("msgid", None)
        elif name == "msgid_plural":
            entry.msgid_plural = _unescape(chunk)
            last = ("msgid_plural", None)
        else:
            if index is None:
                entry.msgstr = _unescape(chunk)
                last = ("msgstr", None)
            else:
                entry.plurals[int(index)] = _unescape(chunk)
                last = ("plural", int(index))
    flush()
    return [item for item in entries if item.msgid]


_ESCAPE_OUT = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t", "\r": "\\r"}


def _escape(text):
    return "".join(_ESCAPE_OUT.get(char, char) for char in text)


def _quote(text):
    return '"%s"' % _escape(text)


HEADER_FIELDS = ("Project-Id-Version", "Last-Translator", "PO-Revision-Date", "Language", "Content-Type")


def read_meta(text):
    """读取 .po 文件头（msgid "" 那条）的键值，返回字典；没有文件头时返回空字典。"""
    meta = {}
    started = False
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not started:
            if line == 'msgid ""':
                started = True
            continue
        if line == 'msgstr ""':
            continue
        if not line:
            if meta:
                break
            continue
        if not line.startswith('"') or not line.endswith('"') or len(line) < 2:
            break
        for part in _unescape(line[1:-1]).split("\n"):
            if ": " in part:
                key, value = part.split(": ", 1)
            elif part.endswith(":"):
                key, value = part[:-1], ""
            else:
                continue
            key = key.strip()
            if key:
                meta[key] = value.strip()
    return meta


def dumps(entries, header=(), meta=None):
    """写回 .po：保留 msgctxt、复数、位置注释与 fuzzy；header 是文件头注释行。"""
    lines = []
    for line in header:
        lines.append("# %s" % line if line else "#")
    lines.append('msgid ""')
    lines.append('msgstr ""')
    lines.append('"Language: zh_HANS\\n"')
    lines.append('"Content-Type: text/plain; charset=UTF-8\\n"')
    values = {key: value for key, value in (meta or {}).items() if value and key not in ("Language", "Content-Type")}
    ordered = [key for key in HEADER_FIELDS if key in values]
    ordered += [key for key in values if key not in ordered]
    for key in ordered:
        lines.append(_quote("%s: %s\n" % (key, values[key])))
    for entry in entries:
        lines.append("")
        for location in entry.locations:
            lines.append("#: %s" % location)
        if entry.fuzzy:
            lines.append("#, fuzzy")
        fields = []
        if entry.msgctxt:
            fields.append("msgctxt %s" % _quote(entry.msgctxt))
        fields.append("msgid %s" % _quote(entry.msgid))
        if entry.msgid_plural:
            fields.append("msgid_plural %s" % _quote(entry.msgid_plural))
            for index in sorted(entry.plurals):
                fields.append("msgstr[%d] %s" % (index, _quote(entry.plurals[index])))
        else:
            fields.append("msgstr %s" % _quote(entry.msgstr))
        if entry.obsolete:
            fields = ["#~ %s" % field for field in fields]
        lines.extend(fields)
    return "\n".join(lines) + "\n"


def translation_map(entries):
    """按注册格式汇总：{context: {msgid: msgstr 或复数元组}}，跳过空译文、fuzzy 与 obsolete。"""
    contexts = {}
    for entry in entries:
        if not entry.translated:
            continue
        contexts.setdefault(entry.msgctxt, {})[entry.msgid] = entry.value()
    return contexts


def completeness(entries):
    """(已翻译条目数, 总条目数, 比例)；fuzzy 计入总数但不计入已翻译。"""
    total = [entry for entry in entries if not entry.obsolete]
    done = [entry for entry in total if entry.translated]
    ratio = (len(done) / len(total)) if total else 0.0
    return len(done), len(total), ratio
