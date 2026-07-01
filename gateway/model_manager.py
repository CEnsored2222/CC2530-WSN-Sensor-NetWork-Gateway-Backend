# -*- coding: utf-8 -*-
"""模型下载管理器。

管理两类视觉模型的下载与安装检测:
  - insightface_buffalo_l: 人脸识别模型 (~250MB, zip 包, 需解压)
  - yolo26n: 目标检测模型 (yolo11n.pt, ultralytics 官方)
"""
import os
import zipfile

import requests

import config
from config import get_writable_dir

# 已知模型元数据
_MODELS = {
    "insightface_buffalo_l": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "subdir": "buffalo_l",
        "zip_name": "buffalo_l.zip",
    },
    "yolo26n": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
        "file_name": "yolo26n.pt",
    },
}


def get_models_dir() -> str:
    """返回模型存储目录路径，不存在时自动创建。"""
    models_dir = config.MODELS_DIR
    if not models_dir:
        models_dir = os.path.join(get_writable_dir(), "models")
    os.makedirs(models_dir, exist_ok=True)
    return models_dir


def is_model_installed(model_name: str) -> bool:
    """检测模型是否已安装。"""
    try:
        if model_name == "insightface_buffalo_l":
            model_dir = os.path.join(get_models_dir(), "buffalo_l")
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
    if model_name == "insightface_buffalo_l":
        return os.path.join(get_models_dir(), "buffalo_l")
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
        with requests.get(url, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total_bytes = int(resp.headers.get("Content-Length", -1))

            if model_name == "insightface_buffalo_l":
                save_path = os.path.join(models_dir, meta["zip_name"])
            else:
                save_path = os.path.join(models_dir, meta["file_name"])

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
        if model_name == "insightface_buffalo_l":
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
