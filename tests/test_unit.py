"""不依赖 Blender 的单元测试：python3 -m unittest discover -s tests"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import catalog, official, po, registry, versions


class VersionTests(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(versions.matches("*", (4, 5, 0)))
        self.assertTrue(versions.matches(">=4.5.0 <5.0.0", (4, 5, 16)))
        self.assertFalse(versions.matches(">=4.5.0 <5.0.0", (5, 2, 4)))
        self.assertTrue(versions.matches("4.5", (4, 5, 16)))
        self.assertFalse(versions.matches("4.5", (5, 2, 4)))
        self.assertTrue(versions.matches("==5.2.4", (5, 2, 4)))
        self.assertFalse(versions.matches("==5.2.4", (5, 2, 3)))
        self.assertTrue(versions.matches(">=0.5.0", (0, 5, 0)))

    def test_bad_spec(self):
        with self.assertRaises(ValueError):
            versions.matches(">=x", (4, 5, 0))


def _entry(**overrides):
    raw = {
        "id": "edgeflow",
        "name": "Edge Flow",
        "url": "locale/edgeflow.po",
        "sha256": "a" * 64,
        "translation_version": "1.0.0",
        "locale": "zh_HANS",
    }
    raw.update(overrides)
    return raw


class CatalogTests(unittest.TestCase):
    def test_parse_ok(self):
        data = {"schema_version": 1, "generated_at": "2026-11-01T00:00:00Z", "entries": [_entry()]}
        result = catalog.parse(data)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.problems, [])
        self.assertEqual(result.entries[0].id, "edgeflow")

    def test_bad_entries_are_skipped(self):
        data = {
            "entries": [
                _entry(id="Bad ID"),
                _entry(sha256="xyz"),
                _entry(locale="zh_CN"),
                _entry(url="https://example.com/a.po"),
                _entry(bytes=catalog.MAX_FILE_BYTES + 1),
                _entry(id="ok.po"),
            ]
        }
        result = catalog.parse(data)
        self.assertEqual([entry.id for entry in result.entries], ["ok.po"])
        self.assertEqual(len(result.problems), 5)

    def test_missing_required(self):
        raw = _entry()
        del raw["sha256"]
        with self.assertRaises(catalog.CatalogError):
            catalog.parse_entry(raw)

    def test_version_is_optional(self):
        # 变更识别靠 sha256，版本号只是展示字段，可以缺省。
        raw = _entry()
        del raw["translation_version"]
        self.assertEqual(catalog.parse_entry(raw).translation_version, "")

    def test_search(self):
        data = {"entries": [_entry(name_zh="边流动", module="EdgeFlow", translator="可是", category="建模")]}
        result = catalog.parse(data)
        self.assertEqual(len(result.search("边流")), 1)
        self.assertEqual(len(result.search("edgeflow")), 1)
        self.assertEqual(len(result.search("建模 可是")), 1)
        self.assertEqual(len(result.search("不存在")), 0)

    def test_search_accepts_raw_or_chinese_name(self):
        # 列表标题是“英文名 | 中文名”，两种写法都要能搜到。
        data = {
            "entries": [
                _entry(
                    name="Texel Kit",
                    name_zh="纹素工具",
                    module="bl_ext.blender_org.texel_kit",
                    translator="KeshiMiao",
                    category="UV",
                )
            ]
        }
        result = catalog.parse(data)
        self.assertEqual(len(result.search("Texel Kit")), 1)
        self.assertEqual(len(result.search("纹素工具")), 1)
        self.assertEqual(len(result.search("texel 纹素")), 1)
        self.assertEqual(len(result.search("边流动")), 0)
        self.assertEqual(len(result.search("")), 1)

    def test_supports(self):
        entry = catalog.parse_entry(_entry(supported_versions=">=0.5.0 <1.0.0"))
        self.assertTrue(entry.supports((0, 9, 0)))
        self.assertFalse(entry.supports((1, 0, 0)))


class CatalogSchemaTests(unittest.TestCase):
    def test_reject_future_schema(self):
        with self.assertRaises(catalog.CatalogError):
            catalog.parse({"schema_version": catalog.SCHEMA_VERSION + 1, "entries": []})
        current = catalog.parse({"schema_version": catalog.SCHEMA_VERSION, "entries": []})
        self.assertEqual(current.entries, [])


class OfficialTests(unittest.TestCase):
    class _Table:
        def __init__(self):
            self._catalog = {"ctx\x04Msg": "译文", "Plain": "普通"}

        def pgettext(self, context, message):
            return self._catalog.get("%s\x04%s" % (context, message), message)

        def gettext(self, message):
            return self._catalog.get(message, message)

    def test_translated_uses_context_key(self):
        table = self._Table()
        # gettext 的实际键是 "msgctxt\x04msgid"，按 (msgctxt, msgid) 元组查会永远落空
        self.assertTrue(official.translated("Msg", "ctx", table))
        self.assertFalse(official.translated("Msg", "", table))
        self.assertTrue(official.translated("Plain", "", table))
        self.assertFalse(official.translated("Missing", "ctx", table))
        self.assertFalse(official.translated("", "ctx", table))


class PoMetaTests(unittest.TestCase):
    def test_dumps_writes_metadata(self):
        entry = po.POEntry()
        entry.msgid = "View"
        entry.msgstr = "视图"
        text = po.dumps(
            [entry],
            header=["perfect-chinese: 1", "module: demo"],
            meta={
                "Project-Id-Version": "demo",
                "Last-Translator": "KeshiMiao",
                "PO-Revision-Date": "2026-11-15 21:00+0800",
                "translator": "KeshiMiao",
            },
        )
        self.assertIn('"Last-Translator: KeshiMiao\\n"', text)
        meta = po.read_meta(text)
        self.assertEqual(meta["Project-Id-Version"], "demo")
        self.assertEqual(meta["translator"], "KeshiMiao")

    def test_read_meta_without_header(self):
        text = 'msgid "View"' + chr(10) + 'msgstr "视图"' + chr(10)
        self.assertEqual(po.read_meta(text), {})


class RegistryTests(unittest.TestCase):
    def test_domain_is_unique(self):
        # 只做字符替换会把 foo.bar 与 foo-bar 撞成同一个注册域
        self.assertNotEqual(registry.domain_for("foo.bar"), registry.domain_for("foo-bar"))
        self.assertEqual(registry.domain_for("Demo"), registry.domain_for("Demo"))
        self.assertTrue(registry.domain_for("Foo.Bar").startswith("pc_"))

    def test_operator_entries_fall_back_to_default(self):
        data = registry.to_blender(
            {"Operator": {"Set Density": "设置密度"}, "": {"Target": "目标"}}
        )["zh_HANS"]
        self.assertEqual(data[("Operator", "Set Density")], "设置密度")
        self.assertEqual(data[(None, "Set Density")], "设置密度")
        self.assertEqual(data[(None, "Target")], "目标")

    def test_default_is_not_overwritten(self):
        data = registry.to_blender(
            {"Operator": {"Apply": "应用（运算符）"}, "": {"Apply": "应用"}}
        )["zh_HANS"]
        self.assertEqual(data[(None, "Apply")], "应用")


if __name__ == "__main__":
    unittest.main()
