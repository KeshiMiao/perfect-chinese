"""网络：在线访问门禁、超时、重试、镜像回退。

约定：全部调用都在后台线程里执行，主线程只接收结果（见 run_in_background）。
"""

import json
import threading
import time
import urllib.error
import urllib.request
from typing import NamedTuple

from .env import addon_version

TIMEOUT = 8
RETRIES = 2
BACKOFF = 0.5
MAX_BYTES = 2 * 1024 * 1024
FATAL_STATUS = (403, 404, 410)
USER_AGENT = "perfect-chinese/%s" % addon_version()


class NetworkError(Exception):
    """所有源都失败。"""


class OfflineError(NetworkError):
    """用户没允许 Blender 联网。"""


class NotModified(Exception):
    """条件请求命中缓存（HTTP 304）。"""


class Response(NamedTuple):
    data: bytes
    url: str
    headers: dict


class _Fatal(Exception):
    """该地址没必要重试，直接换镜像。"""


def online_enabled():
    import bpy

    return bool(getattr(bpy.app, "online_access", False))


def _fetch_once(url, timeout, max_bytes, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(max_bytes + 1)
        metadata = dict(response.headers.items())
    if len(data) > max_bytes:
        raise _Fatal("文件超过 %d 字节" % max_bytes)
    return data, metadata


def fetch(urls, *, timeout=TIMEOUT, max_bytes=MAX_BYTES, headers=None, sleep=time.sleep):
    """按顺序尝试 urls，返回 Response。

    单源内最多重试 RETRIES 次；403/404/410 立即换下一个源；304 抛 NotModified。
    """
    if not online_enabled():
        raise OfflineError("未开启 Blender 的在线访问")
    if isinstance(urls, str):
        urls = [urls]

    problems = []
    for url in urls:
        for attempt in range(RETRIES + 1):
            try:
                data, metadata = _fetch_once(url, timeout, max_bytes, headers)
                return Response(data, url, metadata)
            except _Fatal as exc:
                problems.append("%s: %s" % (url, exc))
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 304:
                    raise NotModified(url) from None
                problems.append("%s: HTTP %d" % (url, exc.code))
                if exc.code in FATAL_STATUS:
                    break
            except Exception as exc:  # 超时、连接失败、证书错误等
                problems.append("%s: %s" % (url, exc))
            if attempt < RETRIES:
                sleep(BACKOFF * (2 ** attempt))
    raise NetworkError("; ".join(problems))


def post_json(url, payload, *, headers=None, timeout=60, max_bytes=MAX_BYTES, sleep=time.sleep):
    """POST JSON 并解析返回；只在后台线程里调用。"""
    if not online_enabled():
        raise OfflineError("未开启 Blender 的在线访问")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    problems = []
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise NetworkError("返回内容超过 %d 字节" % max_bytes)
            try:
                return json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise NetworkError("返回的不是 JSON：%s" % exc) from None
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(300).decode("utf-8", "replace")
            except Exception:
                pass
            if exc.code in (400, 401, 402, 403, 404, 422):
                raise NetworkError("HTTP %d：%s" % (exc.code, detail or exc.reason)) from None
            problems.append("HTTP %d" % exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            problems.append(str(getattr(exc, "reason", exc)))
        if attempt < RETRIES:
            sleep(BACKOFF * (2 ** attempt))
    raise NetworkError("请求失败：%s" % "；".join(problems))


def run_in_background(func, on_done):
    """后台线程执行 func，完成后在主线程回调 on_done(result, error)。"""
    import bpy

    def worker():
        try:
            result, error = func(), None
        except Exception as exc:
            result, error = None, exc

        def finish():
            on_done(result, error)
            return None

        bpy.app.timers.register(finish, first_interval=0.0)

    threading.Thread(target=worker, name="perfect-chinese-net", daemon=True).start()
