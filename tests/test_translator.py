import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import _shim  # noqa: F401

from perfect_chinese.services import translator


def reply(pairs):
    return {"choices": [{"message": {"content": json.dumps({"translations": pairs}, ensure_ascii=False)}}]}


class PayloadTests(unittest.TestCase):
    def test_only_whitelisted_fields(self):
        payload = translator.build_payload(
            [{"msgid": "Add Cube", "msgctxt": "Operator", "path": "secret.py", "module": "x"}],
        )
        text = payload["messages"][1]["content"]
        self.assertIn("Add Cube", text)
        self.assertIn("Operator", text)
        self.assertNotIn("secret.py", text)
        self.assertNotIn("module", text)
        self.assertEqual(payload["response_format"]["type"], "json_object")
        self.assertEqual(payload["messages"][0]["role"], "system")

    def test_models_are_current(self):
        self.assertEqual(translator.DEFAULT_MODEL, "deepseek-flash")
        self.assertEqual(set(translator.MODELS), {"deepseek-flash", "deepseek-v4-pro"})

    def test_no_style_field(self):
        payload = translator.build_payload([{"msgid": "Play"}])
        self.assertNotIn("style", json.loads(payload["messages"][1]["content"]))


class ParseTests(unittest.TestCase):
    def test_parses_and_sorts(self):
        data = reply([{"i": 2, "zh": "乙"}, {"i": 1, "zh": "甲"}])
        self.assertEqual(translator.parse_response(data, 2), ["甲", "乙"])

    def test_code_fence(self):
        inner = json.dumps({"translations": [{"i": 1, "zh": "好"}]})
        data = {"choices": [{"message": {"content": "```json\n%s\n```" % inner}}]}
        self.assertEqual(translator.parse_response(data, 1), ["好"])

    def test_missing_item(self):
        with self.assertRaises(translator.TranslatorError):
            translator.parse_response(reply([{"i": 1, "zh": "甲"}]), 2)

    def test_empty_text(self):
        with self.assertRaises(translator.TranslatorError):
            translator.parse_response(reply([{"i": 1, "zh": "  "}]), 1)

    def test_not_json(self):
        data = {"choices": [{"message": {"content": "抱歉"}}]}
        with self.assertRaises(translator.TranslatorError):
            translator.parse_response(data, 1)

    def test_no_choices(self):
        with self.assertRaises(translator.TranslatorError):
            translator.parse_response({}, 1)


class TranslateTests(unittest.TestCase):
    def test_batches_and_headers(self):
        calls = []

        def post(url, payload, headers=None):
            calls.append((url, payload, headers))
            rows = json.loads(payload["messages"][1]["content"])["items"]
            return reply([{"i": row["i"], "zh": "译" + row["text"]} for row in rows])

        items = [{"msgid": "A%d" % i, "msgctxt": ""} for i in range(25)]
        result = translator.translate(items, "key", post=post, batch=10)
        self.assertEqual(len(result), 25)
        self.assertEqual(result[0], "译A0")
        self.assertEqual([len(json.loads(call[1]["messages"][1]["content"])["items"]) for call in calls], [10, 10, 5])
        self.assertEqual(calls[0][2]["Authorization"], "Bearer key")
        self.assertEqual(calls[0][0], translator.API_URL)

    def test_network_error_is_wrapped(self):
        state = {"n": 0}

        def post(url, payload, headers=None):
            state["n"] += 1
            if state["n"] == 1:
                raise translator.net.NetworkError("boom")
            return reply([{"i": 1, "zh": "好"}])

        with self.assertRaises(translator.TranslatorError):
            translator.translate([{"msgid": "X"}], "key", post=post)
        self.assertEqual(state["n"], 1)

    def test_requires_key(self):
        with self.assertRaises(translator.TranslatorError):
            translator.translate([{"msgid": "X"}], "  ")

    def test_rejects_unknown_model(self):
        with self.assertRaises(translator.TranslatorError):
            translator.translate([{"msgid": "X"}], "key", model="gpt")

    def test_too_many(self):
        items = [{"msgid": "X%d" % i} for i in range(translator.MAX_ITEMS + 1)]
        with self.assertRaises(translator.TranslatorError):
            translator.translate(items, "key")


if __name__ == "__main__":
    unittest.main()
