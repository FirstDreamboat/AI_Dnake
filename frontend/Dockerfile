# 狄耐克AI驱动嵌入式测试用例自动生成平台 - 前端镜像（Nginx 托管构建产物）
FROM node:20-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN npm install --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

# 注意：钉 1.26-alpine——更新的 nginx 镜像(1.27+/Alpine 3.20+)在 CentOS 7 老内核(3.10)上
# 启动报 "pwrite() /run/nginx.pid failed (1: Operation not permitted)"，无法运行
FROM nginx:1.26-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
