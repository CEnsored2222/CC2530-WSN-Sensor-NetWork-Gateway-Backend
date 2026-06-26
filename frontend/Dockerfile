# ====== 阶段1: 构建前端静态文件 ======
FROM node:20-alpine AS builder

WORKDIR /app

# 利用缓存:先装依赖
COPY package.json package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com && npm ci

# 复制源码并构建
COPY . .
RUN npm run build

# ====== 阶段2: Nginx 提供静态文件 + 反向代理 ======
FROM nginx:1.27-alpine

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 覆盖默认配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
