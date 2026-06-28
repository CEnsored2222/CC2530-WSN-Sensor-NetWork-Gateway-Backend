FROM python:3.11-slim

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 先装依赖(利用缓存层)
COPY requirements.txt .
# 第一步: 装除 torch 外的依赖(避免从清华源下载含 CUDA 的 GPU 版本 torch,约 2GB)
RUN grep -v '^torch' requirements.txt > /tmp/req-no-torch.txt && \
    pip install --no-cache-dir -r /tmp/req-no-torch.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    rm /tmp/req-no-torch.txt
# 第二步: 单独装 torch CPU 版本(--index-url 强制只查 PyTorch 官方 CPU 源,服务器无 GPU)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 复制源码
COPY . .

EXPOSE 5000

# Flask-SocketIO + threading 模式,单进程即可
CMD ["python", "app.py"]
