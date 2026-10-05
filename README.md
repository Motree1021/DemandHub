# DemandHub 需求管理系统

创金合信基金零售业务线需求管理系统。当前 Python MVP 只做科技、物料、培训需求的收集、完善和整理记录。

## 当前 Python MVP

新后端在 `server/`，移动端在 `frontend/h5/`。启动、环境变量、测试及镜像说明见 [server/README.md](server/README.md)，本轮完成情况和外部验收边界见 [Python MVP 验收记录](DemandHub_Python_MVP_验收记录.md)。H5 使用 hash 路由和 `/demandhub-api`，开发端口为 5174；在 `frontend/h5/` 执行 `npm ci`、`npm run dev` 即可连接本地 8000 后端。

Java、PC 和旧部署保留作移植参考，后续真正上线并稳定至少三个工作日后再清理。下文为旧 Java 版本说明；新版请按上述入口运行。

## 双栈并存开发说明

仓库当前并存两套后端栈：**Python 单体（主线，承接新需求）** 与 **Java 微服务（冻结，仅作蓝本与回归参照）**。演进路线见 [DemandHub_架构演进路线_v1.0.md](DemandHub_架构演进路线_v1.0.md)。并存期间遵守：

**端口对照（两套栈可同时运行，端口已错开）**

| 用途 | Python 栈 | Java 栈 |
|---|---|---|
| 后端 API | 8000（`/demandhub-api`） | 8180 网关 / 8080 单体 / 8081-8084 服务 |
| MySQL | 3308 | 3307（dev）/ 3317（test） |
| 契约 Mock | **8199**（容器内 8099） | 8099（test 栈） |
| 前端 dev | 5174（H5，代理到 8000） | 5173（PC，代理到 Java）/ 8088（test 栈 nginx） |
| e2e 入口 | `python scripts/e2e_mvp.py` | `python scripts/phase6_e2e.py`（参照） |

**守则**

1. Java 侧冻结：不加新功能、不开新提报入口；新需求一律走 Python 栈。
2. 正式需求编号只由 Python 侧 `demand_no_seq` 发放，两库严禁同库。
3. H5（5174）已切换到 Python 链路（hash 路由 + `/demandhub-api`）；旧 Java 版 H5 入口不再维护。
4. Python 栈本地起服：`docker compose -f deploy/docker-compose.dev.yml up -d --build` 后按 [server/README.md](server/README.md) 操作。

## 仓库结构

```
DemandHub/
├── backend/                    # 后端（Java 17 + Spring Boot 3 多模块）
│   ├── demandhub-common/       # 公共内核：统一返回体、异常、错误码、MP 配置、跨域、Knife4j
│   ├── demandhub-gateway/      # 统一网关（8080）
│   ├── demandhub-system/       # 系统管理与认证权限服务 M1/M8（8081）
│   ├── demandhub-demand/       # 需求核心流程服务 M2~M6（8082）
│   ├── demandhub-notification/ # 通知中心服务 M7（8083）
│   └── demandhub-agent/        # AI Agent 服务 M9（8084）
├── frontend/
│   ├── pc/                     # PC 端（Vue 3 + Vite + TS + Element Plus，5173）
│   └── h5/                     # 移动端 H5（Vue 3 + Vite + TS + Vant 4，5174，/h5/ 路径）
├── deploy/
│   ├── docker-compose.yml      # 本地中间件一键环境
│   ├── mysql/init/             # 建库建表 DDL + 初始化数据（容器首启自动执行）
│   └── rocketmq/broker.conf
└── *.md / *.html               # 设计文档（BRD/SRS/架构/数据库/原型）
```

## 环境准备

| 工具 | 版本要求 |
|---|---|
| JDK | 17+ |
| Maven | 3.8+ |
| Node.js | 18+ |
| Docker Desktop | 任意近期版本 |
| Git | 任意 |

## 本地启动步骤

### 1. 启动中间件（MySQL / Redis / MinIO / Nacos / RocketMQ）

```powershell
# 先确保 Docker Desktop 已启动
docker compose -f deploy/docker-compose.yml up -d
```

首次启动 MySQL 会自动执行 `deploy/mysql/init/` 下的 DDL 和初始化数据。

验证：
- MySQL：`localhost:3307`（宿主机 MySQL84 已占用 3306，故映射 3307），root / demandhub123，库名 `demandhub`
- MinIO 控制台：http://localhost:9001 （demandhub / demandhub123）
- Nacos 控制台：http://localhost:8848/nacos
- RocketMQ NameServer：`localhost:9876`

> 仅需后端联调时，最小启动 MySQL + Redis 即可：
> `docker compose -f deploy/docker-compose.yml up -d mysql redis`

### 2. 启动后端

```powershell
cd backend
mvn -DskipTests install
```

按需启动服务（每个服务一个终端，或用 IDE 运行对应 Application）：

```powershell
mvn -pl demandhub-gateway spring-boot:run      # 网关 8080
mvn -pl demandhub-system spring-boot:run       # 系统服务 8081
mvn -pl demandhub-demand spring-boot:run       # 需求服务 8082
mvn -pl demandhub-notification spring-boot:run # 通知服务 8083
mvn -pl demandhub-agent spring-boot:run        # Agent 服务 8084
```

接口文档（Knife4j）：http://localhost:8081/doc.html （各服务端口同理）

网关统一入口：`http://localhost:8080/api/{模块}/**`，如 `http://localhost:8080/api/system/ping`

### 3. 启动前端

```powershell
cd frontend/pc
npm install
npm run dev        # http://localhost:5173
```

```powershell
cd frontend/h5
npm install
npm run dev        # http://localhost:5174/h5/
```

## 分支与提交约定

- `main`：受保护主干，仅接受 MR 合入，禁止直接 push
- `develop`：集成分支
- 功能分支：`feature/阶段-模块-简述`，如 `feature/p2-m1-auth`
- 提交信息：`type(scope): 描述`，type ∈ feat / fix / chore / docs / refactor / test

## 常用命令

```powershell
# 后端全量编译
cd backend; mvn -DskipTests compile

# 查看中间件状态
docker compose -f deploy/docker-compose.yml ps

# 停止中间件
docker compose -f deploy/docker-compose.yml down

# 停止并清空数据（重新初始化数据库时用）
docker compose -f deploy/docker-compose.yml down -v
```
