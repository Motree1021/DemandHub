# DemandHub 需求管理系统

创金合信基金零售业务线需求管理系统（科技/物料/培训需求全流程管理）。

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
