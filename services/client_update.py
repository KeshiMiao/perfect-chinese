"""客户端自更新：下载发行包，交给 Blender 的扩展系统就地安装。

下载放在后台线程（见 core.net.run_in_background），安装必须在主线程；
装好后磁盘上的文件已经是新版本，但当前会话里跑的还是旧代码，需要重启。
"""

import os
import shutil
import sys
import tempfile
import urllib.parse

import bpy

from ..core import env, net

MAX_BYTES = 32 * 1024 * 1024
DEFAULT_REPO = "user_default"


def download_zip(url):
    """下载安装包到临时目录，返回本地路径。只在后台线程里调用。"""
    response = net.fetch(url, timeout=60, max_bytes=MAX_BYTES)
    name = urllib.parse.unquote(url.rsplit("/", 1)[-1]) or "perfect_chinese.zip"
    if not name.lower().endswith(".zip"):
        name = "perfect_chinese.zip"
    directory = tempfile.mkdtemp(prefix="perfect-chinese-update-")
    path = os.path.join(directory, name)
    with open(path, "wb") as handle:
        handle.write(response.data)
    return path


def cleanup(path):
    """删掉下载用的临时目录。"""
    if path:
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)


def addon_directory():
    """当前插件所在的目录（扩展形态下是 <extensions>/<repo>/perfect_chinese）。"""
    module = sys.modules.get(env.ADDON_ID)
    filename = getattr(module, "__file__", "") or ""
    if not filename:
        return ""
    return os.path.dirname(os.path.abspath(filename))


def repo_id():
    """当前插件装在哪个扩展仓库；认不出时退回 user_default。"""
    directory = addon_directory()
    if not directory:
        return DEFAULT_REPO
    repo_directory = os.path.dirname(directory)
    repos = getattr(getattr(bpy.context.preferences, "extensions", None), "repos", None)
    if not repos:
        return DEFAULT_REPO
    for repo in repos:
        path = getattr(repo, "directory", "") or ""
        if not path:
            continue
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(repo_directory):
            return repo.module
    return DEFAULT_REPO


def install(path):
    """把安装包覆盖到当前仓库；返回 Blender 的 operator 结果。必须在主线程调用。"""
    return bpy.ops.extensions.package_install_files(
        filepath=path,
        repo=repo_id(),
        enable_on_install=True,
        overwrite=True,
    )
