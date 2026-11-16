"""解析器测试：复数、fuzzy、obsolete、空 msgstr、多行与转义。"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import po

SAMPLE = '''
msgid ""
msgstr ""
"Language: zh_HANS\\n"

#: a comment
msgid "Add Cube"
msgstr "添加立方体"

msgctxt "Operator"
msgid "Add Cube"
msgstr "添加立方体（操作符）"

msgid "Light"
msgid_plural "Lights"
msgstr[0] "灯光"
msgstr[1] "灯光（复数）"

msgid "Empty"
msgstr ""

#, fuzzy
msgid "Fuzzy one"
msgstr "模糊"

#~ msgid "Gone"
#~ msgstr "删除"

msgid "Multi"
"line"
msgstr "多行"

msgid "Quoted \\"x\\"\\n"
msgstr "引号"
'''


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.entries = po.loads(SAMPLE)
        self.by_id = {(entry.msgctxt, entry.msgid): entry for entry in self.entries}

    def get(self, msgid, msgctxt=""):
        return self.by_id[(msgctxt, msgid)]

    def test_header_skipped(self):
        self.assertFalse([key for key in self.by_id if not key[1]])

    def test_obsolete_kept(self):
        entry = self.get("Gone")
        self.assertTrue(entry.obsolete)
        self.assertFalse(entry.translated)
        self.assertEqual(entry.msgstr, "删除")

    def test_plain(self):
        self.assertEqual(self.get("Add Cube").msgstr, "添加立方体")

    def test_context(self):
        self.assertEqual(self.get("Add Cube", "Operator").msgstr, "添加立方体（操作符）")

    def test_plural(self):
        entry = self.get("Light")
        self.assertTrue(entry.plural)
        self.assertEqual(entry.value(), ("灯光", "灯光（复数）"))
        self.assertTrue(entry.translated)

    def test_single_plural_form_is_ok(self):
        entry = po.POEntry()
        entry.msgid = "x"
        entry.msgid_plural = "xs"
        entry.plurals = {0: "x"}
        self.assertTrue(entry.translated)

    def test_plural_without_messages_not_translated(self):
        entry = po.POEntry()
        entry.msgid = "x"
        entry.msgid_plural = "xs"
        self.assertFalse(entry.translated)

    def test_empty_msgstr_not_translated(self):
        self.assertFalse(self.get("Empty").translated)

    def test_fuzzy_not_translated(self):
        self.assertTrue(self.get("Fuzzy one").fuzzy)
        self.assertFalse(self.get("Fuzzy one").translated)

    def test_multiline(self):
        self.assertEqual(self.get("Multiline").msgstr, "多行")

    def test_escapes(self):
        self.assertEqual(self.get('Quoted "x"\n').msgstr, "引号")

    def test_translation_map(self):
        mapping = po.translation_map(self.entries)
        self.assertEqual(mapping[""]["Add Cube"], "添加立方体")
        self.assertEqual(mapping["Operator"]["Add Cube"], "添加立方体（操作符）")
        self.assertNotIn("Empty", mapping[""])
        self.assertNotIn("Fuzzy one", mapping[""])
        self.assertNotIn("Gone", mapping[""])

    def test_dumps_obsolete_roundtrip(self):
        text = po.dumps(self.entries)
        self.assertIn('#~ msgid "Gone"', text)
        self.assertIn('#~ msgstr "删除"', text)
        again = {(entry.msgctxt, entry.msgid): entry for entry in po.loads(text)}
        self.assertTrue(again[("", "Gone")].obsolete)
        self.assertEqual(again[("", "Gone")].msgstr, "删除")
        self.assertTrue(again[("", "Fuzzy one")].fuzzy)

    def test_completeness(self):
        done, total, ratio = po.completeness(self.entries)
        self.assertEqual(total, 7)
        self.assertEqual(done, 5)
        self.assertAlmostEqual(ratio, 5 / 7)


if __name__ == "__main__":
    unittest.main()
