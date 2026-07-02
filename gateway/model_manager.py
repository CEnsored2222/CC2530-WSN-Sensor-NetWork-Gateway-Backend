# -*- coding: utf-8 -*-
"""模型下载管理器。

管理两类视觉模型的下载与安装检测:
  - insightface_buffalo_l: 人脸识别模型 (~250MB, zip 包, 需解压)
  - yolo26n: 目标检测模型 (yolo26n.pt, ultralytics v8.4.0 YOLO26 release)
"""
import os
import zipfile

import config
from config import get_writable_dir

# 已知模型元数据
_MODELS = {
    "insightface_buffalo_l": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "subdir": "buffalo_l",
        "zip_name": "buffalo_l.zip",
        "display": "buffalo_l (重量模型, GPU 推荐)",
    },
    "insightface_buffalo_m": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_m.zip",
        "subdir": "buffalo_m",
        "zip_name": "buffalo_m.zip",
        "display": "buffalo_m (轻量模型, CPU/GPU 通用)",
    },
    "yolo26n": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo26n.pt",
        "file_name": "yolo26n.pt",
    },
}

# GitHub 下载加速镜像列表(国内用户加速)
# 顺序:原始 URL 优先(海外用户直连最快),失败时依次尝试镜像
# 镜像前缀会直接拼接到原始 GitHub URL 之前(ghproxy 风格)
_GITHUB_MIRRORS = [
    "",  # 原始 URL(直连 GitHub)
    "https://mirror.ghproxy.com/",  # ghproxy 镜像(GitHub releases 加速)
    "https://ghproxy.net/",  # ghproxy.net 备用
]


def _is_github_url(url: str) -> bool:
    return url.startswith("https://github.com/") or url.startswith("http://github.com/")


def _try_download_with_mirrors(url: str, on_progress=None):
    """依次尝试原始 URL 与镜像源下载,成功返回 Response 对象。

    :param url: 原始 GitHub URL
    :param on_progress: 仅用于在切换镜像时打印日志,实际进度回调由调用方处理
    :return: requests.Response(stream=True,已 raise_for_status)
    :raises: 最后一个镜像也失败时抛出最后一次异常
    """
    import requests
    last_exc = None
    for idx, mirror in enumerate(_GITHUB_MIRRORS):
        if mirror and not _is_github_url(url):
            # 非 GitHub URL 不使用镜像
            continue
        actual_url = mirror + url if mirror else url
        try:
            if mirror:
                print(f"[model_manager] 尝试镜像 #{idx}: {mirror}")
            else:
                print(f"[model_manager] 尝试直连 GitHub")
            resp = requests.get(actual_url, stream=True, timeout=30)
            resp.raise_for_status()
            print(f"[model_manager] 连接成功: {actual_url}")
            return resp
        except Exception as e:
            print(f"[model_manager] 镜像 #{idx} 失败({mirror or 'direct'}): {e}")
            last_exc = e
            continue
    # 全部镜像失败,抛出最后一次异常
    if last_exc is None:
        last_exc = RuntimeError("所有下载镜像均失败且无具体异常")
    raise last_exc


def get_models_dir() -> str:
    """返回模型存储目录路径，不存在时自动创建。

    所有模型统一存放在 {MODELS_DIR}/models/ 子目录下。
    与 insightface 的 {INSIGHTFACE_HOME}/models/{name}/ 路径约定一致。
    """
    val = config.MODELS_DIR
    if val:
        base = val  # 用户自定义目录
    else:
        base = get_writable_dir()  # 默认目录
    models_dir = os.path.join(base, "models")
    os.makedirs(models_dir, exist_ok=True)
    return models_dir


def is_model_installed(model_name: str) -> bool:
    """检测模型是否已安装。"""
    try:
        if model_name.startswith("insightface_"):
            # 提取模型子目录名 (如 "insightface_buffalo_l" → "buffalo_l")
            subdir = model_name.replace("insightface_", "")
            model_dir = os.path.join(get_models_dir(), subdir)
            if not os.path.isdir(model_dir):
                return False
            for entry in os.listdir(model_dir):
                if entry.lower().endswith(".onnx"):
                    return True
            return False
        if model_name == "yolo26n":
            return os.path.isfile(os.path.join(get_models_dir(), "yolo26n.pt"))
    except Exception as e:
        print(f"[model_manager] is_model_installed 异常: {e}")
    return False


def get_model_path(model_name: str) -> str:
    """返回模型文件/目录的完整路径，未知模型返回空字符串。"""
    if model_name.startswith("insightface_"):
        return os.path.join(get_models_dir(), model_name.replace("insightface_", ""))
    if model_name == "yolo26n":
        return os.path.join(get_models_dir(), "yolo26n.pt")
    return ""


def download_model(model_name: str, on_progress=None) -> dict:
    """下载模型，返回 {"ok": bool, "path": str, "error": str|None}。

    :param model_name: 模型名 (insightface_buffalo_l / yolo26n)
    :param on_progress: 进度回调 on_progress(downloaded_bytes, total_bytes, percent)
    """
    result = {"ok": False, "path": "", "error": None}
    if model_name not in _MODELS:
        result["error"] = f"未知模型: {model_name}"
        return result

    meta = _MODELS[model_name]
    url = meta["url"]
    models_dir = get_models_dir()

    try:
        print(f"[model_manager] 开始下载 {model_name}: {url}")
        print(f"[model_manager] 模型目录: {models_dir}")
        # 依次尝试原始 URL 与 GitHub 加速镜像,提高国内下载成功率
        resp = _try_download_with_mirrors(url, on_progress=on_progress)
        with resp:
            total_bytes = int(resp.headers.get("Content-Length", -1))
            print(f"[model_manager] Content-Length: {total_bytes} bytes")

            if model_name.startswith("insightface_"):
                save_path = os.path.join(models_dir, meta["zip_name"])
            else:
                save_path = os.path.join(models_dir, meta["file_name"])

            # 防御性确保目录存在(get_models_dir 已创建,但用户可能在中途删除)
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            print(f"[model_manager] 保存路径: {save_path}")

            downloaded = 0
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    percent = (downloaded / total_bytes * 100.0) if total_bytes > 0 else -1.0
                    if on_progress:
                        try:
                            on_progress(downloaded, total_bytes, percent)
                        except Exception as e:
                            print(f"[model_manager] on_progress 回调异常: {e}")

            print(f"[model_manager] 下载完成: {save_path}")

        # insightface 需解压后删除 zip
        if model_name.startswith("insightface_"):
            extract_dir = os.path.join(models_dir, meta["subdir"])
            print(f"[model_manager] 解压到: {extract_dir}")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(save_path, "r") as zf:
                zf.extractall(extract_dir)
            try:
                os.remove(save_path)
                print(f"[model_manager] 已删除 zip: {save_path}")
            except Exception as e:
                print(f"[model_manager] 删除 zip 失败: {e}")
            result["path"] = extract_dir
        else:
            result["path"] = save_path

        result["ok"] = True
        return result
    except Exception as e:
        print(f"[model_manager] 下载失败 {model_name}: {e}")
        result["error"] = str(e)
        return result


def _compute_size_mb(path: str) -> float:
    """计算文件或目录大小（MB）。"""
    if os.path.isfile(path):
        return round(os.path.getsize(path) / (1024 * 1024), 2)
    if os.path.isdir(path):
        total = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                fp = os.path.join(root, name)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return round(total / (1024 * 1024), 2)
    return 0.0


def list_models() -> list:
    """返回所有已知模型的安装状态。"""
    items = []
    for name in _MODELS:
        path = get_model_path(name)
        installed = is_model_installed(name)
        size_mb = _compute_size_mb(path) if (installed and path) else None
        items.append({
            "name": name,
            "installed": installed,
            "size_mb": size_mb,
            "path": path,
        })
    return items
