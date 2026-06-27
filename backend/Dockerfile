FROM python:3.11-slim

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 先装依赖(利用缓存层)
COPY requirements.txt .
# 一步安装所有依赖(torch CPU 版本通过 --extra-index-url 从 PyTorch 官方源获取)
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --extra-index-url https://download.pytorch.org/whl/cpu

# 复制源码
COPY . .

EXPOSE 5000

# Flask-SocketIO + threading 模式,单进程即可
CMD ["python", "app.py"]
