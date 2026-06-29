# -*- coding: utf-8 -*-
"""网关配置：Config 单例类，支持 gateway.ini 读写 + 环境变量回退 + 硬编码默认值。

通过模块级 __getattr__/__setattr__ 代理保持:
    import config
    config.EMQX_HOST, config.SERIAL_PORT 等访问方式不变。
"""
import configparser
import os
import sys


def get_writable_dir() -> str:
    """获取可写目录路径。

    - 开发环境 (python gui_web.py)：返回脚本所在目录
    - exe 环境 (PyInstaller 打包后)：返回 %APPDATA%/WSN-Gateway/
      (用户数据目录, EXE 同目录保持干净, 避免旧 gw_uuid.txt/gateway.ini 残留
      导致 UUID 不匹配而审批不通过)
    """
    if getattr(sys, 'frozen', False):
        app_data = os.environ.get('APPDATA') or os.path.expanduser('~')
        data_dir = os.path.join(app_data, 'WSN-Gateway')
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    return os.path.dirname(os.path.abspath(__file__))


class Config:
    """网关配置单例，三重来源优先级：gateway.ini > 环境变量 > 硬编码默认"""

    # ============ 默认值 ============
    _DEFAULTS = {
        "EMQX_HOST": "127.0.0.1",
        "EMQX_PORT": 1883,
        "EMQX_USERNAME": "",
        "EMQX_PASSWORD": "",
        "EMQX_KEEPALIVE": 60,
        "SERIAL_PORT": "COM1",
        "SERIAL_BAUDRATE": 38400,
        "TOPIC_PREFIX": "smart_home/gateway",
        "MAC_TIMEOUT_SECONDS": 5,
        "HEARTBEAT_INTERVAL": 30,
    }

    _INT_KEYS = {"EMQX_PORT", "EMQX_KEEPALIVE", "SERIAL_BAUDRATE", "MAC_TIMEOUT_SECONDS", "HEARTBEAT_INTERVAL"}

    # 订阅指标名 -> 业务主题后缀 的映射（非用户可配置，保持不变）
    METRIC_TO_TOPIC = {
        "temperature": "temperature",
        "humidity": "humidity",
        "light": "light",
        "led_status": "led",
        "device_status": "status",
    }

    def __init__(self):
        self._values = {}
        self._load_defaults()
        self._load_from_env()
        self._load_from_ini()

    # ---------- 加载 ----------
    def _load_defaults(self):
        for k, v in self._DEFAULTS.items():
            self._values[k] = v

    def _load_from_env(self):
        env_map = {
            "EMQX_HOST": "EMQX_HOST",
            "EMQX_PORT": "EMQX_PORT",
            "EMQX_USERNAME": "EMQX_USERNAME",
            "EMQX_PASSWORD": "EMQX_PASSWORD",
            "EMQX_KEEPALIVE": "EMQX_KEEPALIVE",
            "SERIAL_PORT": "SERIAL_PORT",
            "SERIAL_BAUDRATE": "SERIAL_BAUDRATE",
        }
        for key, env_name in env_map.items():
            val = os.getenv(env_name)
            if val is not None and val != "":
                self._values[key] = int(val) if key in self._INT_KEYS else val

    def _load_from_ini(self):
        ini_path = os.path.join(get_writable_dir(), "gateway.ini")
        if not os.path.exists(ini_path):
            return
        cp = configparser.ConfigParser()
        cp.optionxform = str  # 保持原始大小写
        cp.read(ini_path, encoding="utf-8")
        for section in cp.sections():
            for key, val in cp.items(section):
                if key in self._values:
                    self._values[key] = int(val) if key in self._INT_KEYS else val

    # ---------- 持久化 ----------
    def save_to_file(self, path=None):
        """将当前配置写入 gateway.ini"""
        if path is None:
            path = os.path.join(get_writable_dir(), "gateway.ini")
        cp = configparser.ConfigParser()
        cp.optionxform = str  # 保持键名大小写,避免 EMQX_HOST 被写成 emqx_host
        cp.add_section("mqtt")
        for k in ["EMQX_HOST", "EMQX_PORT", "EMQX_USERNAME", "EMQX_PASSWORD", "EMQX_KEEPALIVE"]:
            cp.set("mqtt", k, str(self._values[k]))
        cp.add_section("serial")
        for k in ["SERIAL_PORT", "SERIAL_BAUDRATE"]:
            cp.set("serial", k, str(self._values[k]))
        with open(path, "w", encoding="utf-8") as f:
            cp.write(f)

    # ---------- 动态属性 ----------
    @property
    def GW_UUID_FILE(self):
        return os.path.join(get_writable_dir(), "gw_uuid.txt")

    @property
    def EMQX_HOST(self):
        return self._values["EMQX_HOST"]

    @EMQX_HOST.setter
    def EMQX_HOST(self, v):
        self._values["EMQX_HOST"] = str(v)

    @property
    def EMQX_PORT(self):
        return self._values["EMQX_PORT"]

    @EMQX_PORT.setter
    def EMQX_PORT(self, v):
        self._values["EMQX_PORT"] = int(v)

    @property
    def EMQX_USERNAME(self):
        return self._values["EMQX_USERNAME"]

    @EMQX_USERNAME.setter
    def EMQX_USERNAME(self, v):
        self._values["EMQX_USERNAME"] = str(v) if v else ""

    @property
    def EMQX_PASSWORD(self):
        return self._values["EMQX_PASSWORD"]

    @EMQX_PASSWORD.setter
    def EMQX_PASSWORD(self, v):
        self._values["EMQX_PASSWORD"] = str(v) if v else ""

    @property
    def EMQX_KEEPALIVE(self):
        return self._values["EMQX_KEEPALIVE"]

    @EMQX_KEEPALIVE.setter
    def EMQX_KEEPALIVE(self, v):
        self._values["EMQX_KEEPALIVE"] = int(v)

    @property
    def SERIAL_PORT(self):
        return self._values["SERIAL_PORT"]

    @SERIAL_PORT.setter
    def SERIAL_PORT(self, v):
        self._values["SERIAL_PORT"] = str(v)

    @property
    def SERIAL_BAUDRATE(self):
        return self._values["SERIAL_BAUDRATE"]

    @SERIAL_BAUDRATE.setter
    def SERIAL_BAUDRATE(self, v):
        self._values["SERIAL_BAUDRATE"] = int(v)

    @property
    def TOPIC_PREFIX(self):
        return self._values["TOPIC_PREFIX"]

    @TOPIC_PREFIX.setter
    def TOPIC_PREFIX(self, v):
        self._values["TOPIC_PREFIX"] = str(v)

    @property
    def MAC_TIMEOUT_SECONDS(self):
        return self._values["MAC_TIMEOUT_SECONDS"]

    @MAC_TIMEOUT_SECONDS.setter
    def MAC_TIMEOUT_SECONDS(self, v):
        self._values["MAC_TIMEOUT_SECONDS"] = int(v)

    @property
    def HEARTBEAT_INTERVAL(self):
        return self._values["HEARTBEAT_INTERVAL"]

    @HEARTBEAT_INTERVAL.setter
    def HEARTBEAT_INTERVAL(self, v):
        self._values["HEARTBEAT_INTERVAL"] = int(v)

    def __repr__(self):
        return f"<Config EMQX={self.EMQX_HOST}:{self.EMQX_PORT} serial={self.SERIAL_PORT}@{self.SERIAL_BAUDRATE}>"


# ============ 模块级单例 + 向后兼容代理 ============
_config = None


def _get_config() -> Config:
    """获取 Config 单例（惰性初始化）。"""
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config_value(name: str, value):
    """运行时设置配置项（写入单例内部 _values）。

    用法: config.set_config_value("EMQX_HOST", "10.0.0.1")
    （Python 模块不支持 __setattr__，因此提供此显式函数。）
    """
    cfg = _get_config()
    setattr(cfg, name, value)


def __getattr__(name):
    """模块级属性访问代理 -> Config 单例（读取）。"""
    if name.startswith("_"):
        raise AttributeError(name)
    return getattr(_get_config(), name)
