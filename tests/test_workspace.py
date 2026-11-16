import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import extract, po, workspace

SOURCE = '''
import bpy

class DEMO_OT_run(bpy.types.Operator):
    bl_idname = "demo.run"
    bl_label = "Run Demo"
'''

SOURCE2 = '''
import bpy

class DEMO_OT_run(bpy.types.Operator):
    bl_idname = "demo.run"
    bl_label = "Run Demo"
    bl_description = "Runs the demo"
'''


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addon = os.path.join(self.root, "addon")
        os.makedirs(self.addon)
        self.out = os.path.join(self.root, "out")
        self.write("__init__.py", SOURCE)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        with open(os.path.join(self.addon, name), "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_slug(self):
        self.assertEqual(workspace.slug("bl_ext.user_default.EdgeFlow"), "bl_ext.user_default.edgeflow")
        self.assertEqual(workspace.slug("../evil path"), "evil-path")
        self.assertEqual(workspace.slug("1bad"), "1bad")

    def test_has_source(self):
        self.assertTrue(workspace.has_source(self.addon))
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        with open(os.path.join(empty, "x.pyc"), "wb") as handle:
            handle.write(b"\x00")
        self.assertFalse(workspace.has_source(empty))

    def test_write_and_merge(self):
        target = workspace.po_path(self.out, "demo")
        workspace.write(self.addon, target, module="demo")
        entries = extract.load_existing(target)
        self.assertEqual([item.msgid for item in entries], ["Run Demo"])

        entries[0].msgstr = "运行演示"
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(po.dumps(entries, header=["module: demo"]))

        self.write("__init__.py", SOURCE2)
        workspace.write(self.addon, target, module="demo")
        entries = extract.load_existing(target)
        mapping = {item.msgid: item for item in entries}
        self.assertEqual(mapping["Run Demo"].msgstr, "运行演示")
        self.assertIn("Runs the demo", mapping)

    def test_summary(self):
        target = workspace.po_path(self.out, "demo")
        workspace.write(self.addon, target, module="demo")
        entries = extract.load_existing(target)
        entries[0].msgstr = "运行演示"
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(po.dumps(entries))
        self.assertEqual(workspace.summary(target), {"Operator": {"Run Demo": "运行演示"}})


if __name__ == "__main__":
    unittest.main()
