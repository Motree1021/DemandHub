# DemandHub 后端多模块共用镜像构建（阶段 8）
# 用法：docker build --build-arg MODULE=demandhub-gateway -t demandhub/gateway:1.0.0 backend/
# MODULE ∈ demandhub-gateway / demandhub-system / demandhub-demand / demandhub-notification / demandhub-agent
# REGISTRY：Docker Hub 不可达时可传镜像加速源，如 --build-arg REGISTRY=docker.m.daocloud.io/library

ARG REGISTRY=docker.io/library

FROM ${REGISTRY}/maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
# 构建容器内访问 Maven Central 受限时走阿里云镜像（本地开发不受影响）
COPY maven-settings.xml /root/.m2/settings.xml
# 全量拷贝源码（-am 会连带构建依赖的 demandhub-common）
COPY pom.xml ./
COPY demandhub-common ./demandhub-common
COPY demandhub-system ./demandhub-system
COPY demandhub-demand ./demandhub-demand
COPY demandhub-notification ./demandhub-notification
COPY demandhub-agent ./demandhub-agent
COPY demandhub-gateway ./demandhub-gateway
COPY demandhub-server ./demandhub-server
ARG MODULE
# 挂载 .m2 缓存：5 个模块共用依赖，本机多次构建显著提速
RUN --mount=type=cache,target=/root/.m2 mvn -q -DskipTests install -pl ${MODULE} -am

FROM ${REGISTRY}/eclipse-temurin:17-jre
ARG MODULE
WORKDIR /app
COPY --from=build /build/${MODULE}/target/${MODULE}-exec.jar /app/app.jar
ENV TZ=Asia/Shanghai
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
