import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import extract, po

ADDON = '''\
import bpy

bl_info = {
    "name": "Demo Addon",
    "description": "Does demo things",
    "version": (1, 2),
    "category": "Object",
}


class DEMO_OT_thing(bpy.types.Operator):
    bl_idname = "demo.thing"
    bl_label = "Do Thing"
    bl_description = "Runs the demo"

    def execute(self, context):
        self.report({'INFO'}, "Finished")
        self.report({'INFO'}, "Done with %d items" % 2)
        return {'FINISHED'}


class DEMO_PT_panel(bpy.types.Panel):
    bl_label = "Demo Panel"
    bl_category = "Demo"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Hello world")
        layout.operator("demo.thing", text="Do it now")
        layout.prop(context.scene, "demo_prop", text="Demo Value")
        layout.label(text="Dynamic " + context.scene.name)
        layout.label(text=bpy.app.translations.pgettext("Special Text", "Operator"))
        layout.label(text=bpy.app.translations.pgettext_iface("Iface Text"))
        layout.label(text=bpy.app.translations.pgettext_tip("Tip Text"))


class DemoProps(bpy.types.PropertyGroup):
    demo_prop: bpy.props.StringProperty(name="Demo Value", description="Value used by demo")
    mode: bpy.props.EnumProperty(
        name="Mode",
        items=[('A', "Alpha", "First letter"), ('B', "Beta", "Second letter")],
    )
'''


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addon = os.path.join(self.root, "demo_addon")
        os.makedirs(self.addon)
        self.write("__init__.py", ADDON)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        path = os.path.join(self.addon, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def entries(self):
        return {(item.msgctxt, item.msgid): item for item in extract.extract(self.addon).entries()}

    def test_contexts(self):
        entries = self.entries()
        self.assertIn(("Operator", "Do Thing"), entries)
        self.assertIn(("Operator", "Runs the demo"), entries)
        self.assertIn(("", "Finished"), entries)
        self.assertIn(("", "Demo Panel"), entries)
        self.assertIn(("", "Hello world"), entries)
        # operator 按钮的 text= 按 Operator 上下文登记，属性和 label 仍是默认上下文。
        self.assertIn(("Operator", "Do it now"), entries)
        self.assertNotIn(("", "Do it now"), entries)
        self.assertIn(("", "Demo Value"), entries)

    def test_pgettext(self):
        entries = self.entries()
        self.assertIn(("Operator", "Special Text"), entries)
        self.assertIn(("", "Iface Text"), entries)
        self.assertIn(("Tooltip", "Tip Text"), entries)

    def test_properties_and_items(self):
        entries = self.entries()
        self.assertIn(("", "Value used by demo"), entries)
        self.assertIn(("", "Alpha"), entries)
        self.assertIn(("", "Second letter"), entries)

    def test_bl_info(self):
        result = extract.extract(self.addon)
        self.assertEqual(result.meta["name"], "Demo Addon")
        self.assertEqual(result.meta["version"], "1.2")
        keys = {(item.msgctxt, item.msgid) for item in result.entries()}
        self.assertIn(("", "Does demo things"), keys)
        self.assertIn(("", "Object"), keys)

    def test_skips_ids(self):
        keys = {(item.msgctxt, item.msgid) for item in extract.extract(self.addon).entries()}
        self.assertNotIn(("", "demo.thing"), keys)
        self.assertNotIn(("", "demo_prop"), keys)

    def test_dynamic_problems(self):
        result = extract.extract(self.addon)
        joined = "\n".join(result.problems)
        self.assertIn("动态文本", joined)
        self.assertIn("self.report", joined)

    def test_no_python(self):
        empty = os.path.join(self.root, "empty")
        os.makedirs(empty)
        with open(os.path.join(empty, "only.pyc"), "wb") as handle:
            handle.write(b"\x00")
        result = extract.extract(empty)
        self.assertEqual(result.entries(), [])
        self.assertTrue(any(".pyc" in text for text in result.problems))

    def test_syntax_error(self):
        bad = os.path.join(self.root, "bad")
        os.makedirs(bad)
        with open(os.path.join(bad, "broken.py"), "w", encoding="utf-8") as handle:
            handle.write("def broken(:\n")
        result = extract.extract(bad)
        self.assertTrue(any("语法错误" in text for text in result.problems))

    def test_merge_keeps_translations(self):
        entries = extract.extract(self.addon).entries()
        for entry in entries:
            if entry.msgid == "Hello world":
                entry.msgstr = "你好世界"
            if entry.msgid == "Alpha":
                entry.msgstr = "阿尔法"
        self.write("__init__.py", ADDON.replace('"Hello world"', '"Hello there"'))
        fresh = extract.extract(self.addon).entries()
        merged = extract.merge(entries, fresh)
        mapping = {(item.msgctxt, item.msgid): item for item in merged}
        self.assertEqual(mapping[("", "Alpha")].msgstr, "阿尔法")
        self.assertTrue(mapping[("", "Hello world")].obsolete)
        self.assertIn(("", "Hello there"), mapping)
        text = extract.render(merged, module="demo_addon")
        self.assertIn('#~ msgid "Hello world"', text)
        again = {(item.msgctxt, item.msgid): item for item in po.loads(text)}
        self.assertTrue(again[("", "Hello world")].obsolete)
        self.assertEqual(again[("", "Hello world")].msgstr, "你好世界")

    def test_render_roundtrip(self):
        entries = extract.extract(self.addon).entries()
        text = extract.render(entries, module="demo_addon", source="/tmp/demo")
        self.assertIn("# module: demo_addon", text)
        loaded = po.loads(text)
        self.assertEqual(len(loaded), len(entries))
        first = loaded[0]
        self.assertTrue(first.locations)
        self.assertEqual(first.msgstr, "")


if __name__ == "__main__":
    unittest.main()
