"""目录同步测试：临时目录 + 假的网络层。"""

import json
import pathlib
import sys
import tempfile
import unittest
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _shim  # noqa: F401

from perfect_chinese.core import net
from perfect_chinese.services import update_check


def _catalog(entries):
    return json.dumps({"schema_version": 1, "generated_at": "", "entries": entries}).encode("utf-8")


ENTRY = {
    "id": "demo",
    "name": "Demo",
    "url": "locale/demo.po",
    "sha256": "a" * 64,
    "translation_version": "1.0.0",
}


class SyncTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self._tmp.name)
        self._orig_paths = update_check.cache_paths
        self._orig_online = net.online_enabled
        self._orig_fetch = net._fetch_once
        update_check.cache_paths = lambda: (str(root / "catalog.json"), str(root / "meta.json"))
        net.online_enabled = lambda: True
        self.root = root
        self.calls = 0

    def tearDown(self):
        update_check.cache_paths = self._orig_paths
        net.online_enabled = self._orig_online
        net._fetch_once = self._orig_fetch
        self._tmp.cleanup()

    def respond(self, data, headers=None):
        def fake(url, timeout, max_bytes, request_headers=None):
            self.calls += 1
            if isinstance(data, Exception):
                raise data
            return data, headers or {}

        net._fetch_once = fake

    def test_first_fetch_writes_cache(self):
        self.respond(_catalog([ENTRY]), {"ETag": '"v1"'})
        result = update_check.refresh()
        self.assertTrue(result.updated)
        self.assertEqual(len(result.catalog.entries), 1)
        meta = json.loads((self.root / "meta.json").read_text())
        self.assertEqual(meta["etag"], '"v1"')
        self.assertEqual(self.calls, 1)

    def test_fresh_cache_skips_network(self):
        self.respond(_catalog([ENTRY]), {"ETag": '"v1"'})
        update_check.refresh(now=1000)
        self.calls = 0
        result = update_check.refresh(now=1000 + 60)
        self.assertFalse(result.updated)
        self.assertTrue(result.from_cache)
        self.assertEqual(self.calls, 0)

    def test_stale_cache_hits_network(self):
        self.respond(_catalog([ENTRY]), {"ETag": '"v1"'})
        update_check.refresh(now=1000)
        result = update_check.refresh(now=1000 + update_check.CACHE_TTL + 1)
        self.assertTrue(result.updated)
        self.assertEqual(self.calls, 2)

    def test_not_modified_keeps_cache(self):
        self.respond(_catalog([ENTRY]), {"ETag": '"v1"'})
        update_check.refresh(now=1000)
        self.respond(urllib.error.HTTPError("https://a", 304, "Not Modified", {}, None))
        result = update_check.refresh(now=2000)
        self.assertFalse(result.updated)
        self.assertIsNotNone(result.catalog)
        self.assertEqual(len(result.catalog.entries), 1)

    def test_network_error_falls_back_to_cache(self):
        self.respond(_catalog([ENTRY]), {"ETag": '"v1"'})
        update_check.refresh(now=1000)
        self.respond(OSError("offline"))
        result = update_check.refresh(now=1000 + update_check.CACHE_TTL + 1)
        self.assertFalse(result.updated)
        self.assertTrue(result.from_cache)
        self.assertEqual(len(result.catalog.entries), 1)
        self.assertTrue(result.error)

    def test_offline_without_cache(self):
        self.respond(OSError("offline"))
        result = update_check.refresh()
        self.assertIsNone(result.catalog)
        self.assertFalse(result.from_cache)
        self.assertTrue(result.error)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self._orig_online = net.online_enabled
        self._orig_fetch = net._fetch_once
        net.online_enabled = lambda: True

    def tearDown(self):
        net.online_enabled = self._orig_online
        net._fetch_once = self._orig_fetch

    def respond(self, payload):
        data = json.dumps(payload).encode("utf-8")
        net._fetch_once = lambda url, timeout, max_bytes, request_headers=None: (data, {})

    def test_finds_zip_asset(self):
        self.respond(
            {
                "tag_name": "v1.2.0",
                "html_url": "https://example.com/release",
                "assets": [
                    {"name": "notes.txt", "browser_download_url": "https://example.com/notes.txt"},
                    {"name": "perfect_chinese_1.2.0.zip", "browser_download_url": "https://example.com/a.zip"},
                ],
            }
        )
        result = update_check.check_client()
        self.assertEqual(result["latest"], "1.2.0")
        self.assertEqual(result["download"], "https://example.com/a.zip")

    def test_release_without_asset(self):
        self.respond({"tag_name": "1.2.0", "assets": []})
        result = update_check.check_client()
        self.assertEqual(result["latest"], "1.2.0")
        self.assertEqual(result["download"], "")

    def test_missing_assets_key(self):
        self.respond({"tag_name": "1.2.0"})
        self.assertEqual(update_check.check_client()["download"], "")

    def test_note_survives_result_update(self):
        update_check.set_note("正在下载…")
        update_check.remember_client({"latest": "1.2.0", "download": "u"})
        self.assertEqual(update_check.CLIENT_RESULT["note"], "")
        self.assertEqual(update_check.CLIENT_RESULT["download"], "u")


if __name__ == "__main__":
    unittest.main()
