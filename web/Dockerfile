# 边缘容器的镜像：前端在这里构建，产物由 nginx 直接发。
#
# **这个镜像同时是反向代理** —— compose 里的 nginx 服务就是它。反代配置仍由
# docker/nginx.conf 挂进来，改配置只要 restart，不必重建镜像；镜像里只烤进
# `dist/`，因此**改了前端代码必须重建**（`make rebuild`），restart 是不够的。
#
# 构建上下文是本目录，与 `pnpm build` 在本地看到的输入一模一样。
FROM node:24-bookworm-slim AS build

# pnpm 版本跟着 package.json 的 packageManager 走 —— 在这里再写一个版本号，
# 两处迟早分叉，而分叉的症状是本地构建得出与镜像里构建得出的产物不一样
RUN corepack enable

WORKDIR /web

# 依赖单独一层：改前端代码不必重装依赖。
# pnpm-workspace.yaml 带的是构建脚本白名单，缺了它 esbuild 装不上
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . ./
RUN pnpm build

FROM nginx:1.27-alpine

# 站点根，nginx.conf 里 `location /` 的 root 指的就是这里
COPY --from=build /web/dist /usr/share/nginx/html
