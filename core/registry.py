"""注册域：把翻译字典交给 Blender，支持增删与双语。

Blender 4.x 的注册格式是 {"zh_HANS": {(context 或 None, msgid): msgstr}}。
同名的域不能重复注册，所以增删都走 unregister -> register。
"""

import hashlib
import re

LOCALE = "zh_HANS"
DOMAIN_PREFIX = "pc_"
BILINGUAL_MAX_LENGTH = 48
DEFAULT_SEPARATOR = " | "


def domain_for(package_id):
    # 只做字符替换会把 foo.bar 与 foo-bar 撞成同一个域，补一段 id 的摘要保证唯一
    raw = str(package_id)
    safe = re.sub(r"[^a-z0-9_]", "_", raw.lower())
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return "%s%s_%s" % (DOMAIN_PREFIX, safe, digest)


def can_bilingual(msgid, text):
    """带格式占位符或太长的条目不加原文，避免撑破布局或弄坏格式化。"""
    return "%" not in msgid and "%" not in text and len(msgid) <= BILINGUAL_MAX_LENGTH


# 运算符的标题按 "Operator" 上下文查，描述却按默认上下文查；两条都登记才都生效。
OPERATOR_CONTEXT = "Operator"


def to_blender(translations, bilingual=False, separator=DEFAULT_SEPARATOR):
    """{context: {msgid: str | 复数元组}} -> {"zh_HANS": {(context, msgid): str}}。"""
    locale_map = {}
    for context, messages in translations.items():
        key_context = context or None
        for msgid, value in messages.items():
            text = value[0] if isinstance(value, (tuple, list)) else value
            if not text:
                continue
            if bilingual and can_bilingual(msgid, text):
                text = "%s%s%s" % (text, separator or " ", msgid)
            locale_map[(key_context, msgid)] = text

    # Operator 上下文的条目再补一份默认上下文，供运算符描述（tooltip）命中。
    for (context, msgid), text in list(locale_map.items()):
        if context == OPERATOR_CONTEXT:
            locale_map.setdefault((None, msgid), text)
    return {LOCALE: locale_map}


class Registry:
    def __init__(self):
        self._active = {}

    def active_ids(self):
        return tuple(sorted(self._active))

    def is_active(self, package_id):
        return package_id in self._active

    def register(self, package_id, translations, bilingual=False, separator=DEFAULT_SEPARATOR):
        data = to_blender(translations, bilingual, separator)
        if not data[LOCALE]:
            raise ValueError("没有可注册的译文")
        if package_id in self._active:
            self.unregister(package_id)
        import bpy

        bpy.app.translations.register(domain_for(package_id), data)
        self._active[package_id] = data
        return len(data[LOCALE])

    def unregister(self, package_id):
        if package_id not in self._active:
            return False
        import bpy

        bpy.app.translations.unregister(domain_for(package_id))
        del self._active[package_id]
        return True

    def clear(self):
        for package_id in list(self._active):
            self.unregister(package_id)


registry = Registry()


def register(package_id, translations, bilingual=False, separator=DEFAULT_SEPARATOR):
    return registry.register(package_id, translations, bilingual, separator)


def unregister(package_id):
    return registry.unregister(package_id)


def clear():
    registry.clear()


def active_ids():
    return registry.active_ids()
