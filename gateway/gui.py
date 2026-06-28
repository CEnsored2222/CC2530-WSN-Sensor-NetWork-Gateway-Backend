# -*- coding: utf-8 -*-
"""网关 GUI 启动器 — 使用 tkinter 提供配置界面与运行日志。

双击 exe 即可运行,无需任何环境配置。
提供 EMQX_HOST, SERIAL_PORT, SERIAL_BAUDRATE, MAC_TIMEOUT_SECONDS 四个配置项。
"""
import os
import sys
import json
import queue
import threading
import importlib
import tkinter as tk
from tkinter import ttk, messagebox

# ── 配置文件路径(与 exe 同目录) ──────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
CONFIG_FILE = os.path.join(BASE_DIR, "gateway_config.json")

DEFAULT_CONFIG = {
    "EMQX_HOST": "127.0.0.1",
    "SERIAL_PORT": "COM1",
    "SERIAL_BAUDRATE": "38400",
    "MAC_TIMEOUT_SECONDS": "5",
}


def load_config():
    """从 JSON 文件加载上次保存的配置。"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(saved)
            return cfg
    except Exception:
        pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    """保存配置到 JSON 文件。"""
    try:
        with open(CONFIG_FILE, "r" if os.path.exists(CONFIG_FILE) else "w",
                  encoding="utf-8") as f:
            pass  # 仅触发文件存在检查
    except Exception:
        pass
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ── 日志缓冲区 — 线程安全的 stdout 重定向 ──────────────────────
class LogStream:
    """将 print 输出重定向到 tkinter Text 控件。"""

    def __init__(self, text_widget: tk.Text, log_queue: queue.Queue):
        self.text_widget = text_widget
        self.log_queue = log_queue

    def write(self, s: str):
        if s and s.strip():
            self.log_queue.put(s)

    def flush(self):
        pass


class GatewayGUI:
    """网关 GUI 主窗口。"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Smart Home Gateway")
        self.root.geometry("700x520")
        self.root.minsize(560, 400)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 状态
        self.running = False
        self.gateway_thread = None
        self.log_queue = queue.Queue()

        self._build_ui()
        self._load_config_to_ui()

        # 启动队列轮询
        self._poll_log_queue()

    # ── UI 构建 ──────────────────────────────────────────────
    def _build_ui(self):
        # 顶部标题
        header = ttk.Label(
            self.root,
            text="Smart Home Gateway — 本地网关",
            font=("Microsoft YaHei", 14, "bold"),
        )
        header.pack(pady=(12, 8))

        # 配置区域 Frame
        cfg_frame = ttk.LabelFrame(self.root, text="配置参数", padding=10)
        cfg_frame.pack(fill=tk.X, padx=16, pady=(0, 8))

        # EMQX_HOST
        ttk.Label(cfg_frame, text="EMQX Host:").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4
        )
        self.emqx_host_var = tk.StringVar()
        ttk.Entry(cfg_frame, textvariable=self.emqx_host_var, width=30).grid(
            row=0, column=1, sticky=tk.EW, pady=4
        )

        # SERIAL_PORT
        ttk.Label(cfg_frame, text="Serial Port:").grid(
            row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4
        )
        self.serial_port_var = tk.StringVar()
        port_frame = ttk.Frame(cfg_frame)
        port_frame.grid(row=1, column=1, sticky=tk.EW, pady=4)
        ttk.Entry(port_frame, textvariable=self.serial_port_var, width=20).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(port_frame, text="扫描串口", command=self._scan_ports, width=10).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        # SERIAL_BAUDRATE
        ttk.Label(cfg_frame, text="Serial Baudrate:").grid(
            row=2, column=0, sticky=tk.W, padx=(0, 8), pady=4
        )
        self.baudrate_var = tk.StringVar()
        baud_combo = ttk.Combobox(
            cfg_frame,
            textvariable=self.baudrate_var,
            values=["9600", "19200", "38400", "57600", "115200"],
            width=18,
        )
        baud_combo.grid(row=2, column=1, sticky=tk.W, pady=4)

        # MAC_TIMEOUT_SECONDS
        ttk.Label(cfg_frame, text="MAC Timeout (秒):").grid(
            row=3, column=0, sticky=tk.W, padx=(0, 8), pady=4
        )
        self.timeout_var = tk.StringVar()
        ttk.Spinbox(
            cfg_frame,
            textvariable=self.timeout_var,
            from_=1,
            to=300,
            width=8,
        ).grid(row=3, column=1, sticky=tk.W, pady=4)

        cfg_frame.columnconfigure(1, weight=1)

        # 按钮区域
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 8))

        self.start_btn = ttk.Button(
            btn_frame, text="启动网关", command=self._start_gateway
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(
            btn_frame, text="停止网关", command=self._stop_gateway, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="● 已停止")
        self.status_label = ttk.Label(btn_frame, textvariable=self.status_var, foreground="gray")
        self.status_label.pack(side=tk.RIGHT)

        # 日志输出区域
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 12))

        self.log_text = tk.Text(
            log_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            font=("Consolas", 9),
            relief=tk.FLAT,
        )
        scrollbar = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ── 串口扫描 ──────────────────────────────────────────────
    def _scan_ports(self):
        """枚举系统可用串口。"""
        try:
            import serial.tools.list_ports

            ports = [p.device for p in serial.tools.list_ports.comports()]
            if ports:
                self.serial_port_var.set(ports[0])
                messagebox.showinfo("扫描结果", f"找到 {len(ports)} 个串口:\n" + "\n".join(ports))
            else:
                messagebox.showinfo("扫描结果", "未检测到可用串口")
        except ImportError:
            messagebox.showwarning("提示", "pyserial 未安装,无法扫描串口")
        except Exception as e:
            messagebox.showerror("错误", f"扫描串口失败:\n{e}")

    # ── 配置持久化 ─────────────────────────────────────────────
    def _load_config_to_ui(self):
        cfg = load_config()
        self.emqx_host_var.set(cfg["EMQX_HOST"])
        self.serial_port_var.set(cfg["SERIAL_PORT"])
        self.baudrate_var.set(cfg["SERIAL_BAUDRATE"])
        self.timeout_var.set(cfg["MAC_TIMEOUT_SECONDS"])

    def _save_config_from_ui(self):
        cfg = {
            "EMQX_HOST": self.emqx_host_var.get().strip(),
            "SERIAL_PORT": self.serial_port_var.get().strip(),
            "SERIAL_BAUDRATE": self.baudrate_var.get().strip(),
            "MAC_TIMEOUT_SECONDS": self.timeout_var.get().strip(),
        }
        save_config(cfg)
        return cfg

    # ── 网关注册 / 生命周期 ─────────────────────────────────────
    def _apply_env(self, cfg: dict):
        """将 GUI 配置写入环境变量(必须在 import gateway 模块前调用)。"""
        os.environ["EMQX_HOST"] = cfg["EMQX_HOST"]
        os.environ["SERIAL_PORT"] = cfg["SERIAL_PORT"]
        os.environ["SERIAL_BAUDRATE"] = cfg["SERIAL_BAUDRATE"]
        os.environ["MAC_TIMEOUT_SECONDS"] = cfg["MAC_TIMEOUT_SECONDS"]

    def _start_gateway(self):
        if self.running:
            return

        cfg = self._save_config_from_ui()

        # 校验必填项
        if not cfg["EMQX_HOST"]:
            messagebox.showwarning("提示", "请输入 EMQX Host")
            return

        try:
            int(cfg["MAC_TIMEOUT_SECONDS"])
        except ValueError:
            messagebox.showwarning("提示", "MAC Timeout 必须为整数")
            return

        try:
            int(cfg["SERIAL_BAUDRATE"])
        except ValueError:
            messagebox.showwarning("提示", "Serial Baudrate 必须为整数")
            return

        self._apply_env(cfg)

        # 清空日志
        self._clear_log()
        self._append_log("=" * 55)
        self._append_log(f"  EMQX Host     : {cfg['EMQX_HOST']}")
        self._append_log(f"  Serial Port   : {cfg['SERIAL_PORT']}")
        self._append_log(f"  Baudrate      : {cfg['SERIAL_BAUDRATE']}")
        self._append_log(f"  MAC Timeout   : {cfg['MAC_TIMEOUT_SECONDS']}s")
        self._append_log("=" * 55)

        # 重定向 stdout 到日志窗口
        self._old_stdout = sys.stdout
        sys.stdout = LogStream(self.log_text, self.log_queue)

        self.running = True
        self._update_ui_state(running=True)

        # 在后台线程启动网关
        self.gateway_thread = threading.Thread(
            target=self._gateway_entry, daemon=True, name="gateway-main"
        )
        self.gateway_thread.start()

    def _gateway_entry(self):
        """网关主线程入口。"""
        try:
            # 此时配置已在 os.environ 中,重载模块确保读取最新配置
            for mod_name in ["config", "state", "mac_registry", "serial_parser",
                             "mqtt_client", "serial_writer", "serial_reader", "main"]:
                if mod_name in sys.modules:
                    importlib.reload(sys.modules[mod_name])

            import main as gateway_main

            gateway_main.main()
        except Exception as e:
            print(f"\n[GUI] 网关异常退出: {e}")
            import traceback

            traceback.print_exc()
        finally:
            self.root.after(0, self._on_gateway_stopped)

    def _stop_gateway(self):
        if not self.running:
            return
        print("\n[GUI] 正在停止网关...")
        try:
            import main as gateway_main

            gateway_main.stop_gateway()
        except Exception as e:
            print(f"[GUI] 停止网关异常: {e}")

    def _on_gateway_stopped(self):
        """网关线程退出后的 UI 清理(在主线程中执行)。"""
        self.running = False
        if hasattr(self, "_old_stdout"):
            sys.stdout = self._old_stdout
        self._update_ui_state(running=False)
        self._append_log("\n[GUI] 网关已停止")

    def _update_ui_state(self, running: bool):
        if running:
            self.start_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
            self.status_var.set("● 运行中")
            self.status_label.configure(foreground="green")
        else:
            self.start_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)
            self.status_var.set("● 已停止")
            self.status_label.configure(foreground="gray")

    # ── 日志处理 ───────────────────────────────────────────────
    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _append_log(self, text: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _poll_log_queue(self):
        """定时从队列拉取日志并显示。"""
        while True:
            try:
                msg = self.log_queue.get_nowait()
                self._append_log(msg)
            except queue.Empty:
                break
        self.root.after(100, self._poll_log_queue)

    # ── 窗口关闭 ───────────────────────────────────────────────
    def _on_close(self):
        if self.running:
            if messagebox.askyesno("确认", "网关正在运行,确定要退出吗?"):
                self._stop_gateway()
                # 等待网关线程退出
                if self.gateway_thread and self.gateway_thread.is_alive():
                    self.gateway_thread.join(timeout=3)
                self.root.destroy()
        else:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


# ── 入口 ────────────────────────────────────────────────────
def main():
    app = GatewayGUI()
    app.run()


if __name__ == "__main__":
    main()
