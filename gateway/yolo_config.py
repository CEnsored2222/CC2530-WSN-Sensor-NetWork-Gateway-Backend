# -*- coding: utf-8 -*-
"""Yolo 配置注入层。

将 gateway Config 的值在运行时注入 Yolo Config 类的类属性，
避免直接修改 Yolo/ 源码，保持 Yolo 模块独立部署能力。
"""
import os
import sys
import importlib.util

# 必须在任何 setup_yolo_path() 调用之前预导入 gateway 的 config 模块。
# 原因：gateway/ 与 Yolo/ 都有 config.py，setup_yolo_path 会把 Yolo/ 插到
# sys.path[0]，导致后续 `import config` 命中 Yolo/config.py 而非 gateway/config.py。
# 此处提前导入并缓存到 sys.modules，之后 `import config` 始终返回 gateway 的 config。
_gateway_dir = os.path.dirname(os.path.abspath(__file__))
if _gateway_dir not in sys.path:
    sys.path.insert(0, _gateway_dir)
import config as gateway_config  # noqa: E402  模块级缓存 gateway 配置

# 注入完成后的 Yolo Config 类缓存
_yolo_config_cls = None


def get_yolo_dir() -> str:
    """返回 Yolo/ 目录的绝对路径。

    兼容 PyInstaller 打包环境（sys._MEIPASS 下查找）与开发环境（gateway/ 上级目录）。
    找不到时返回空字符串。
    """
    # PyInstaller 打包环境：资源被解压到 sys._MEIPASS
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidate = os.path.join(base, "Yolo")
        if os.path.isdir(candidate):
            return os.path.abspath(candidate)

    # 开发环境：从本文件所在目录的上级查找
    parent_dir = os.path.dirname(_gateway_dir)
    candidate = os.path.join(parent_dir, "Yolo")
    if os.path.isdir(candidate):
        return os.path.abspath(candidate)

    print("[yolo_config] Yolo directory not found")
    return ""


def setup_yolo_path() -> bool:
    """将 Yolo/ 目录加入 sys.path（如尚未存在）。

    成功添加返回 True；路径为空或已存在返回 False。
    """
    yolo_dir = get_yolo_dir()
    if not yolo_dir:
        return False
    if yolo_dir in sys.path:
        return False
    sys.path.insert(0, yolo_dir)
    print(f"[yolo_config] added to sys.path: {yolo_dir}")
    return True


def inject_to_yolo() -> bool:
    """将 gateway Config 的值注入 Yolo Config 类的类属性。

    使用 importlib 显式从 Yolo 路径加载 config.py，避免与 gateway 的 config 模块
    命名冲突。注入通过 setattr 修改 Yolo Config 的类属性。
    """
    global _yolo_config_cls
    try:
        # 确保 Yolo 模块可被导入（Yolo 内部代码用 `from config import Config`）
        setup_yolo_path()

        yolo_dir = get_yolo_dir()
        if not yolo_dir:
            print("[yolo_config] inject failed: yolo_dir is empty")
            return False

        # 显式按文件路径加载 Yolo 的 config.py，避免与 gateway config 命名冲突
        spec = importlib.util.spec_from_file_location(
            "yolo_config_module", os.path.join(yolo_dir, "config.py")
        )
        yolo_config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(yolo_config_module)
        YoloConfig = yolo_config_module.Config

        setattr(YoloConfig, "DEVICE", gateway_config.YOLO_DEVICE)
        setattr(YoloConfig, "IMGSZ", gateway_config.YOLO_IMGSZ)
        setattr(YoloConfig, "FACE_MODEL", gateway_config.FACE_MODEL)
        setattr(YoloConfig, "FACE_SIM_THRESHOLD", gateway_config.FACE_SIM_THRESHOLD)
        setattr(YoloConfig, "BACKEND_URL", gateway_config.BACKEND_URL)
        setattr(YoloConfig, "INTERNAL_TOKEN", gateway_config.INTERNAL_TOKEN)

        _yolo_config_cls = YoloConfig
        print("[yolo_config] inject success")
        return True
    except Exception as e:
        print(f"[yolo_config] inject failed: {e}")
        return False


def get_yolo_config():
    """返回 Yolo Config 类（已注入配置后）。失败返回 None。"""
    if not inject_to_yolo():
        return None
    return _yolo_config_cls
