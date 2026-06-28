# -*- coding: utf-8 -*-
"""本地网关 CLI 入口。

启动流程(待审主题隔离):
1. 读取/生成网关 UUID
2. 打开串口
3. 连接 EMQX,订阅本网关下行主题,发布注册请求
4. 等待后端审批 -> 收到 approved 后启动串口监听/MAC超时/心跳/数据转发
5. Ctrl+C 优雅退出

运行:
  pip install -r requirements.txt
  python main.py
"""
from gateway_core import GatewayCore
from log_handler import log


def main():
    core = GatewayCore()
    core.start()
    core.wait()       # 阻塞等待,直到 Ctrl+C 或 stop() 被调用


if __name__ == "__main__":
    main()
