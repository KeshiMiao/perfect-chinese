"""已安装的翻译包：校验、落盘、状态与完整度。"""

import os
import shutil
import time

from . import catalog, po, store

STATE_FILE = "state.json"
DATA_FILE = "translation.po"


class PackageError(Exception):
    """下载内容不可用。"""


def package_path(package_id):
    """包目录路径（不创建）。"""
    if not catalog.ID_PATTERN.match(str(package_id)):
        raise PackageError("包 id 不合法：%r" % (package_id,))
    return os.path.join(store.data_dir("packages"), str(package_id))


def package_dir(package_id):
    path = package_path(package_id)
    os.makedirs(path, exist_ok=True)
    return path


def install(entry, data):
    """校验并写入一个包；失败时不留下半成品。"""
    if len(data) > catalog.MAX_FILE_BYTES:
        raise PackageError("文件超过 %d 字节" % catalog.MAX_FILE_BYTES)
    digest = store.sha256_bytes(data)
    if digest != str(entry.sha256).lower():
        raise PackageError("sha256 不匹配")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackageError("不是 UTF-8 文本：%s" % exc) from None
    entries = [entry for entry in po.loads(text) if not entry.obsolete]
    if not entries:
        raise PackageError("没有可用的词条")

    directory = package_dir(entry.id)
    store.atomic_write(os.path.join(directory, DATA_FILE), data)
    done, total, ratio = po.completeness(entries)
    state = {
        "id": entry.id,
        "translation_version": entry.translation_version,
        "sha256": digest,
        "url": entry.url,
        "installed_at": int(time.time()),
        "entry_count": total,
        "translated_count": done,
        "completeness": round(ratio, 4),
    }
    store.write_json(os.path.join(directory, STATE_FILE), state)
    return state


def installed_state(package_id):
    try:
        directory = package_path(package_id)
    except PackageError:
        return None
    state = store.read_json(os.path.join(directory, STATE_FILE))
    if not isinstance(state, dict):
        return None
    if not os.path.exists(os.path.join(directory, DATA_FILE)):
        return None
    return state


def is_installed(package_id):
    return installed_state(package_id) is not None


def needs_update(package_id, entry):
    state = installed_state(package_id)
    return state is None or state.get("sha256") != str(entry.sha256).lower()


def backup(package_id):
    """更新前把现有包目录挪到旁边备份；返回备份路径，没装过则返回 None。"""
    path = package_path(package_id)
    if not os.path.isdir(path):
        return None
    backup_path = path + ".bak"
    if os.path.isdir(backup_path):
        shutil.rmtree(backup_path, ignore_errors=True)
    os.replace(path, backup_path)
    return backup_path


def restore(package_id, backup_path):
    """安装/启用失败时把备份换回来。"""
    path = package_path(package_id)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    os.replace(backup_path, path)


def drop_backup(backup_path):
    if backup_path and os.path.isdir(backup_path):
        shutil.rmtree(backup_path, ignore_errors=True)


def uninstall(package_id):
    try:
        directory = package_path(package_id)
    except PackageError:
        return False
    if not os.path.isdir(directory):
        return False
    shutil.rmtree(directory, ignore_errors=True)
    # ignore_errors 会吞掉失败，返回真实结果，调用方才能提示
    return not os.path.isdir(directory)


def load_entries(package_id):
    path = os.path.join(package_dir(package_id), DATA_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            return po.loads(handle.read())
    except OSError:
        return []


def load_translations(package_id):
    return po.translation_map(load_entries(package_id))


def completeness(package_id):
    return po.completeness(load_entries(package_id))
