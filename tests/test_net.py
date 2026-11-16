"""网络层测试：不打真实网络，替换底层抓取函数。"""

import pathlib
import sys
import unittest
import urllib.error

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import net


class NetTests(unittest.TestCase):
    def setUp(self):
        self._orig_online = net.online_enabled
        self._orig_fetch = net._fetch_once
        net.online_enabled = lambda: True
        self.calls = []
        self.seen_headers = []

    def tearDown(self):
        net.online_enabled = self._orig_online
        net._fetch_once = self._orig_fetch

    def _responder(self, mapping):
        def fake(url, timeout, max_bytes, headers=None):
            self.calls.append(url)
            self.seen_headers.append(headers)
            value = mapping[url]
            if isinstance(value, Exception):
                raise value
            return value, {"ETag": '"abc"'}

        net._fetch_once = fake

    def test_first_source_wins(self):
        self._responder({"https://a": b"abc"})
        response = net.fetch("https://a", sleep=lambda _: None)
        self.assertEqual((response.data, response.url), (b"abc", "https://a"))
        self.assertEqual(response.headers["ETag"], '"abc"')
        self.assertEqual(self.calls, ["https://a"])

    def test_headers_forwarded(self):
        self._responder({"https://a": b"abc"})
        net.fetch("https://a", headers={"If-None-Match": '"abc"'}, sleep=lambda _: None)
        self.assertEqual(self.seen_headers[0], {"If-None-Match": '"abc"'})

    def test_retry_then_success(self):
        attempts = {"n": 0}

        def flaky(url, timeout, max_bytes, headers=None):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise TimeoutError("timed out")
            return b"ok", {}

        net._fetch_once = flaky
        response = net.fetch("https://a", sleep=lambda _: None)
        self.assertEqual(response.data, b"ok")
        self.assertEqual(attempts["n"], 3)

    def test_403_switches_mirror_without_retry(self):
        self._responder(
            {
                "https://github": urllib.error.HTTPError("https://github", 403, "Forbidden", {}, None),
                "https://mirror": b"mirror",
            }
        )
        response = net.fetch(["https://github", "https://mirror"], sleep=lambda _: None)
        self.assertEqual((response.data, response.url), (b"mirror", "https://mirror"))
        self.assertEqual(self.calls, ["https://github", "https://mirror"])

    def test_304_raises_not_modified(self):
        self._responder({"https://a": urllib.error.HTTPError("https://a", 304, "Not Modified", {}, None)})
        with self.assertRaises(net.NotModified):
            net.fetch("https://a", sleep=lambda _: None)

    def test_all_sources_fail(self):
        self._responder({"https://a": OSError("boom"), "https://b": OSError("boom")})
        with self.assertRaises(net.NetworkError):
            net.fetch(["https://a", "https://b"], sleep=lambda _: None)

    def test_offline_gate(self):
        net.online_enabled = lambda: False
        with self.assertRaises(net.OfflineError):
            net.fetch("https://a")

    def test_oversize_is_fatal(self):
        def big(url, timeout, max_bytes, headers=None):
            raise net._Fatal("文件超过 %d 字节" % max_bytes)

        net._fetch_once = big
        with self.assertRaises(net.NetworkError):
            net.fetch(["https://a"], sleep=lambda _: None)


if __name__ == "__main__":
    unittest.main()
