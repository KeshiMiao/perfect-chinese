"""目录：解析、校验、搜索。

目录是单个 JSON 文件，由翻译仓库的 CI 生成；这里只读取和校验，生成逻辑不在这边。
"""

import re
from dataclasses import dataclass, field

from . import versions

SCHEMA_VERSION = 1
MAX_FILE_BYTES = 512 * 1024
LOCALE = "zh_HANS"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MISSING = object()


class CatalogError(ValueError):
    """单条目录数据不合法。"""


@dataclass(frozen=True)
class Entry:
    id: str
    name: str
    url: str
    sha256: str
    translation_version: str = ""
    module: str = ""
    name_zh: str = ""
    translator: str = ""
    category: str = ""
    locale: str = LOCALE
    supported_versions: str = "*"
    size: int = 0
    updated_at: str = ""
    kind: str = "addon"
    entry_count: int = 0
    translated_count: int = 0

    def supports(self, version):
        try:
            return versions.matches(self.supported_versions, version)
        except (TypeError, ValueError):
            return False


def matches(entry, query=""):
    """一条条目是否命中搜索词：按空格分词，每个词都要在原文/译名/模块/译者/分类/id 里出现。"""
    keywords = [word for word in str(query).strip().lower().split() if word]
    if not keywords:
        return True
    haystack = " ".join(
        (entry.name, entry.name_zh, entry.module, entry.translator, entry.category, entry.id)
    ).lower()
    return all(word in haystack for word in keywords)


@dataclass
class Catalog:
    entries: list = field(default_factory=list)
    generated_at: str = ""
    schema_version: int = SCHEMA_VERSION
    problems: list = field(default_factory=list)

    def search(self, query="", kind=None):
        return [
            entry
            for entry in self.entries
            if (kind is None or entry.kind == kind) and matches(entry, query)
        ]


def _text(raw, key, *, required=False):
    value = raw.get(key, MISSING)
    if value is MISSING:
        if required:
            raise CatalogError("缺少字段 %s" % key)
        return ""
    if not isinstance(value, str):
        raise CatalogError("字段 %s 不是字符串" % key)
    if required and not value.strip():
        raise CatalogError("字段 %s 为空" % key)
    return value


def _size(raw):
    value = raw.get("bytes", raw.get("size", 0))
    if not isinstance(value, int) or value < 0:
        raise CatalogError("bytes 不是非负整数")
    if value > MAX_FILE_BYTES:
        raise CatalogError("文件超过 %d 字节" % MAX_FILE_BYTES)
    return value


def _url(raw):
    url = _text(raw, "url", required=True)
    if url.startswith("/") or "://" in url or ".." in url.split("/"):
        raise CatalogError("url 必须是仓库内相对路径")
    return url


def parse_entry(raw):
    if not isinstance(raw, dict):
        raise CatalogError("条目不是对象")
    entry_id = _text(raw, "id", required=True)
    if not ID_PATTERN.match(entry_id):
        raise CatalogError("id 不合法")
    locale = _text(raw, "locale") or LOCALE
    if locale != LOCALE:
        raise CatalogError("locale 必须是 %s" % LOCALE)
    sha256 = _text(raw, "sha256", required=True).lower()
    if not SHA256_PATTERN.match(sha256):
        raise CatalogError("sha256 不合法")
    supported = _text(raw, "supported_versions") or "*"
    try:
        versions.matches(supported, (4, 5, 0))
    except (TypeError, ValueError):
        raise CatalogError("supported_versions 不合法") from None
    return Entry(
        id=entry_id,
        name=_text(raw, "name", required=True),
        url=_url(raw),
        sha256=sha256,
        translation_version=_text(raw, "translation_version"),
        module=_text(raw, "module"),
        name_zh=_text(raw, "name_zh"),
        translator=_text(raw, "translator"),
        category=_text(raw, "category"),
        locale=locale,
        supported_versions=supported,
        size=_size(raw),
        updated_at=_text(raw, "updated_at"),
        kind=_text(raw, "kind") or "addon",
    )


def parse(data):
    """解析目录；坏条目记入 problems 并跳过，不影响其余条目。"""
    if not isinstance(data, dict):
        raise CatalogError("目录不是 JSON 对象")
    schema = data.get("schema_version", SCHEMA_VERSION)
    if not isinstance(schema, int) or schema < 1:
        raise CatalogError("schema_version 不合法")
    if schema > SCHEMA_VERSION:
        raise CatalogError(
            "目录 schema_version 为 %d，高于插件支持的 %d，请先升级插件" % (schema, SCHEMA_VERSION)
        )
    raw_entries = data.get("entries", [])
    if not isinstance(raw_entries, list):
        raise CatalogError("entries 不是数组")

    catalog = Catalog(
        generated_at=str(data.get("generated_at", "")),
        schema_version=schema,
    )
    for index, raw in enumerate(raw_entries):
        try:
            catalog.entries.append(parse_entry(raw))
        except CatalogError as exc:
            catalog.problems.append("第 %d 条：%s" % (index + 1, exc))
    return catalog
