"""译者工作区的本地文件：一个插件一份 .po，抽取时保留已有译文。"""

import os
import re

from . import extract, po, store

BAD_CHARS = re.compile(r"[^a-z0-9._-]+")


def slug(module):
    """模块 id → 文件名：bl_ext.user_default.foo → bl_ext.user_default.foo。"""
    text = str(module).strip().lower()
    text = BAD_CHARS.sub("-", text).strip("-.")
    if not text or not text[0].isalnum():
        text = "addon-" + text if text else "addon"
    return text[:80]


def po_path(directory, module):
    return os.path.join(directory, slug(module) + ".po")


def has_source(path):
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [name for name in dirnames if not name.startswith(".") and name != "__pycache__"]
        if any(name.endswith(".py") for name in filenames):
            return True
    return False


def read_header(path):
    """读取 .po 顶部注释行（去掉开头的 #），用于原样保留文件头字段。"""
    lines = []
    if not os.path.exists(path):
        return lines
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line.startswith("#"):
                break
            lines.append(line)
    return lines


def write(addon_dir, out_path, module="", name="", meta=None):
    """抽取 addon_dir 并合并进 out_path，返回抽取结果。"""
    result = extract.extract(addon_dir)
    if not result.files:
        return result
    existing = extract.load_existing(out_path)
    merged = extract.merge(existing, result.entries())
    merged_meta = {}
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8", errors="replace") as handle:
            merged_meta = po.read_meta(handle.read())
    for key, value in (meta or {}).items():
        if value:
            merged_meta[key] = value
    text = extract.render(
        merged,
        module=module,
        source=addon_dir,
        name=name or result.meta.get("name", ""),
        header=read_header(out_path),
        meta=merged_meta,
    )
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    store.atomic_write(out_path, text.encode("utf-8"))
    return result


def summary(path):
    """{(msgctxt, msgid): msgstr} 形式的译文表，用于预览。"""
    return po.translation_map(extract.load_existing(path))
