# DemandHub 前端镜像（阶段 8）：PC 端 + H5 端构建产物由同一 Nginx 托管
# 用法：docker build -t demandhub/frontend:1.0.0 frontend/
# Nginx 80 端口同域托管：PC 端 / 、H5 端 /h5/，/api 反代后端网关（P5 合并原 80/81 双端口）
# REGISTRY：Docker Hub 不可达时可传镜像加速源，如 --build-arg REGISTRY=docker.m.daocloud.io/library

ARG REGISTRY=docker.io/library

FROM ${REGISTRY}/node:20-alpine AS build-pc
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /app
COPY pc/package.json pc/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm config set registry ${NPM_REGISTRY} && npm ci --no-audit --no-fund
COPY pc/ ./
RUN npm run build

FROM ${REGISTRY}/node:20-alpine AS build-h5
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /app
COPY h5/package.json h5/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm config set registry ${NPM_REGISTRY} && npm ci --no-audit --no-fund
COPY h5/ ./
RUN npm run build

FROM ${REGISTRY}/nginx:1.27-alpine
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build-pc /app/dist /usr/share/nginx/html/pc
COPY --from=build-h5 /app/dist /usr/share/nginx/html/h5
EXPOSE 80
