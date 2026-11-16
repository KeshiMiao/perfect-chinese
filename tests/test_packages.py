"""翻译包安装测试：临时目录 + 合成的 .po。"""

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _shim  # noqa: F401

from perfect_chinese.core import catalog, packages, store

PO_TEXT = '''# perfect-chinese: 1
# id: demo
# name: Demo
# translation_version: 1.0.0

msgid ""
msgstr ""
"Language: zh_HANS\\n"

msgid "Hello"
msgstr "你好"

msgid "Bye"
msgstr ""
'''


def make_entry(data, version="1.0.0"):
    return catalog.parse_entry(
        {
            "id": "demo",
            "name": "Demo",
            "url": "locale/demo.po",
            "sha256": store.sha256_bytes(data),
            "translation_version": version,
        }
    )


class PackageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self._orig = store.data_dir
        root = self.root

        def fake_data_dir(*parts):
            path = root.joinpath(*parts)
            path.mkdir(parents=True, exist_ok=True)
            return str(path)

        store.data_dir = fake_data_dir
        self.data = PO_TEXT.encode("utf-8")

    def tearDown(self):
        store.data_dir = self._orig
        self._tmp.cleanup()

    def test_install_and_read(self):
        entry = make_entry(self.data)
        state = packages.install(entry, self.data)
        self.assertEqual(state["translated_count"], 1)
        self.assertTrue(packages.is_installed("demo"))
        translations = packages.load_translations("demo")
        self.assertEqual(translations[""]["Hello"], "你好")
        self.assertNotIn("Bye", translations[""])

    def test_installed_ids(self):
        self.assertEqual(packages.installed_ids(), set())
        entry = make_entry(self.data)
        packages.install(entry, self.data)
        self.assertEqual(packages.installed_ids(), {"demo"})

    def test_sha_mismatch(self):
        entry = make_entry(self.data)
        with self.assertRaises(packages.PackageError):
            packages.install(entry, self.data + b"x")
        self.assertFalse(packages.is_installed("demo"))

    def test_not_utf8(self):
        entry = make_entry(b"\xff\xfe")
        with self.assertRaises(packages.PackageError):
            packages.install(entry, b"\xff\xfe")

    def test_empty_po(self):
        data = b'msgid ""\nmsgstr ""\n'
        entry = make_entry(data)
        with self.assertRaises(packages.PackageError):
            packages.install(entry, data)

    def test_bad_id(self):
        with self.assertRaises(packages.PackageError):
            packages.package_dir("../etc")

    def test_needs_update(self):
        entry = make_entry(self.data, "1.0.0")
        packages.install(entry, self.data)
        same = make_entry(self.data, "1.0.0")
        newer = make_entry(self.data + b"", "1.1.0")
        changed = catalog.parse_entry(
            {
                "id": "demo",
                "name": "Demo",
                "url": "locale/demo.po",
                "sha256": "b" * 64,
                "translation_version": "1.1.0",
            }
        )
        self.assertFalse(packages.needs_update("demo", same))
        self.assertFalse(packages.needs_update("demo", newer))
        self.assertTrue(packages.needs_update("demo", changed))

    def test_backup_and_restore(self):
        entry = make_entry(self.data)
        packages.install(entry, self.data)
        backup = packages.backup("demo")
        self.assertIsNotNone(backup)
        newer = b'msgid ""\nmsgstr ""\n\nmsgid "Hello"\nmsgstr "\xe6\x82\xa8\xe5\xa5\xbd"\n'
        packages.install(make_entry(newer), newer)
        self.assertEqual(packages.load_translations("demo")[""]["Hello"], "您好")
        packages.restore("demo", backup)
        self.assertEqual(packages.load_translations("demo")[""]["Hello"], "你好")
        packages.drop_backup(backup)

    def test_obsolete_only_rejected(self):
        data = '# perfect-chinese: 1\n\n#~ msgid "Old"\n#~ msgstr "\xe6\x97\xa7"\n'.encode("utf-8")
        entry = make_entry(data)
        with self.assertRaises(packages.PackageError):
            packages.install(entry, data)

    def test_uninstall(self):
        entry = make_entry(self.data)
        packages.install(entry, self.data)
        self.assertTrue(packages.uninstall("demo"))
        self.assertFalse(packages.is_installed("demo"))
        self.assertFalse(packages.uninstall("demo"))


if __name__ == "__main__":
    unittest.main()
