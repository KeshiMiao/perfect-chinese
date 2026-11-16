"""目录同步：24 小时缓存、ETag 条件请求、失败时退回缓存。

网络请求本身在调用方提供的线程里跑；这里只负责读缓存、写缓存和判定新鲜度。
"""

import time

from ..core import catalog, net, store

DEFAULT_SOURCE = (
    "https://raw.githubusercontent.com/KeshiMiao/perfect-chinese-translations/main/catalog.json"
)
MIRRORS = ()
CACHE_TTL = 24 * 60 * 60
CLIENT_RELEASES = "https://api.github.com/repos/KeshiMiao/perfect-chinese/releases/latest"
CLIENT_PAGE = "https://github.com/KeshiMiao/perfect-chinese/releases"


class SyncResult:
    __slots__ = ("catalog", "updated", "error", "from_cache")

    def __init__(self, catalog_value=None, updated=False, error="", from_cache=False):
        self.catalog = catalog_value
        self.updated = updated
        self.error = error
        self.from_cache = from_cache


def sources():
    return (DEFAULT_SOURCE,) + tuple(MIRRORS)


def raw_base():
    """目录所在目录，用来拼 .po 的下载地址。"""
    return DEFAULT_SOURCE.rsplit("/", 1)[0]


def cache_paths():
    return store.data_path("catalog", "catalog.json"), store.data_path("catalog", "meta.json")


def is_fresh(meta, now=None):
    try:
        fetched_at = int(meta.get("fetched_at", 0))
    except (TypeError, ValueError):
        return False
    if not fetched_at:
        return False
    return (now if now is not None else time.time()) - fetched_at < CACHE_TTL


def load_cached():
    path, _ = cache_paths()
    data = store.read_json(path)
    if not isinstance(data, dict):
        return None
    try:
        return catalog.parse(data)
    except catalog.CatalogError:
        return None


def refresh(force=False, now=None):
    """拉取最新目录；失败时返回缓存里的旧目录。"""
    catalog_path, meta_path = cache_paths()
    meta = store.read_json(meta_path, {}) or {}
    cached = load_cached()

    if not force and cached is not None and is_fresh(meta, now):
        return SyncResult(cached, updated=False, from_cache=True)

    headers = {}
    if meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if meta.get("last_modified"):
        headers["If-Modified-Since"] = meta["last_modified"]

    try:
        response = net.fetch(sources(), headers=headers)
    except net.NotModified:
        meta["fetched_at"] = int(now if now is not None else time.time())
        store.write_json(meta_path, meta)
        return SyncResult(cached, updated=False, from_cache=True)
    except net.NetworkError as exc:
        return SyncResult(cached, updated=False, error=str(exc), from_cache=cached is not None)

    try:
        fresh = catalog.parse(_decode(response.data))
    except (catalog.CatalogError, ValueError) as exc:
        return SyncResult(cached, updated=False, error="目录格式错误：%s" % exc, from_cache=cached is not None)

    store.atomic_write(catalog_path, response.data)
    store.write_json(
        meta_path,
        {
            "etag": response.headers.get("ETag", ""),
            "last_modified": response.headers.get("Last-Modified", ""),
            "fetched_at": int(now if now is not None else time.time()),
            "url": response.url,
        },
    )
    return SyncResult(fresh, updated=True, from_cache=False)


def _decode(data):
    import json

    return json.loads(data.decode("utf-8"))


def check_client():
    """查客户端最新版本；只返回信息，不下载（D9）。"""
    import json

    from ..core import net

    response = net.fetch(CLIENT_RELEASES)
    payload = json.loads(response.data.decode("utf-8"))
    tag = str(payload.get("tag_name", "")).strip()
    return {
        "latest": tag[1:] if tag[:1] in ("v", "V") else tag,
        "name": payload.get("name", ""),
        "url": payload.get("html_url", CLIENT_PAGE),
    }


CLIENT_RESULT = {"latest": "", "url": CLIENT_PAGE, "error": ""}


def remember_client(result=None, error=None):
    """记下最近一次客户端更新检查的结果，供界面显示。"""
    if result:
        CLIENT_RESULT.update(result)
        CLIENT_RESULT["error"] = ""
    if error is not None:
        CLIENT_RESULT["error"] = str(error)
