# DemandHub 系统架构（现状）

> 版本：v1.1（2026-09-30，基于当前代码整理；含火山方舟大模型接入、ADMIN 超级用户全线直通）
> 技术栈：Java 17 / Spring Boot 3.2 / Spring Cloud Gateway / MyBatis-Plus / Vue 3 / RocketMQ 5.2 / MySQL 8 / Redis 7 / MinIO

---

## 1. 系统总体架构图

```mermaid
%%{init: {'theme':'base', 'flowchart':{'useMaxWidth':false, 'htmlLabels':true, 'nodeSpacing':80, 'rankSpacing':100, 'curve':'linear'}, 'themeVariables':{'fontSize':'20px', 'background':'#ffffff', 'mainBkg':'#ffffff', 'primaryColor':'#ffffff', 'primaryBorderColor':'#ff7f00', 'primaryTextColor':'#000000', 'lineColor':'#ff7f00', 'secondaryColor':'#ffffff', 'tertiaryColor':'#ffffff', 'clusterBkg':'#ffffff', 'clusterBorder':'#ff7f00', 'titleColor':'#000000', 'edgeLabelBackground':'#ffffff'}}}%%
flowchart TB
    subgraph EXT["外部系统"]
        CJ["创金零售渠道<br/>SSO 签票 / verify 回源"]
        WECOM["企业微信<br/>应用消息推送"]
        ARK["火山方舟大模型<br/>OpenAI 兼容协议<br/>chat / embedding"]
    end

    subgraph CLIENT["用户端"]
        PC["PC 浏览器<br/>管理 / 看板 / 处理台 / 提报"]
        H5["H5 移动端<br/>渠道提报 / 初审 / 处理"]
    end

    subgraph ACCESS["接入层"]
        NGINX["Nginx（前端同域单端口）<br/>/ → PC 静态资源<br/>/h5/ → H5 静态资源<br/>/api → 网关（SSE 关缓冲）"]
        GW["demandhub-gateway :8080<br/>Spring Cloud Gateway<br/>AuthFilter：JWT 验签 + Redis 会话校验<br/>剥离伪造头，注入 X-User-Id / X-User-Roles / X-Channel<br/>StripPrefix=1 按 /api/{module}/** 路由"]
    end

    subgraph BIZ["业务微服务（Spring Boot 3.2 / Java 17）"]
        SYS["demandhub-system :8081<br/>认证 / 用户 / 组织 / 角色授权<br/>渠道 SSO / 用户映射合并"]
        DMD["demandhub-demand :8082<br/>需求全生命周期（自研状态机）<br/>草稿 / 初审 / 评论 / 附件 / 工时<br/>看板 / 报表导出 / SLA / 统计"]
        NTF["demandhub-notification :8083<br/>站内信 / 模板渲染<br/>偏好过滤 / 企微推送"]
        AGT["demandhub-agent :8084<br/>AI 提报引导（SSE 流式）<br/>辅助生成 / 会话管理 / RAG<br/>RealLlmClient 熔断降级"]
    end

    subgraph MIDDLE["中间件（Docker）"]
        MYSQL[("MySQL 8<br/>业务库 demandhub")]
        REDIS[("Redis 7<br/>会话 / 分布式锁 / SLA 去重")]
        MQ["RocketMQ 5.2<br/>namesrv :9876 / broker :10911<br/>异步事件 / 延迟重试"]
        MINIO[("MinIO<br/>附件对象存储")]
        NACOS["Nacos 2.3<br/>注册配置中心（standalone）"]
    end

    PC --> NGINX
    H5 --> NGINX
    CJ -. "ticket 跳转（TTL 60s）" .-> H5
    NGINX --> GW
    GW --> SYS
    GW --> DMD
    GW --> NTF
    GW --> AGT

    SYS --> MYSQL
    SYS --> REDIS
    DMD --> MYSQL
    DMD --> REDIS
    DMD --> MQ
    DMD --> MINIO
    NTF --> MYSQL
    NTF --> REDIS
    NTF --> MQ
    AGT --> MYSQL
    AGT --> MQ

    SYS -. "verify 回源验票" .-> CJ
    NTF -. "应用消息推送" .-> WECOM
    AGT -. "chat / embeddings<br/>（失败熔断冷却 → 前端降级手动）" .-> ARK

    linkStyle default stroke:#ff7f00,stroke-width:2.5px,color:#000000
    style EXT fill:#ffffff,stroke:#ff7f00,stroke-width:2px,color:#000000
    style CLIENT fill:#ffffff,stroke:#ff7f00,stroke-width:2px,color:#000000
    style ACCESS fill:#ffffff,stroke:#ff7f00,stroke-width:2px,color:#000000
    style BIZ fill:#ffffff,stroke:#ff7f00,stroke-width:2px,color:#000000
    style MIDDLE fill:#ffffff,stroke:#ff7f00,stroke-width:2px,color:#000000
```

## 2. 后端模块结构

Maven 多模块（`backend/pom.xml`），7 个模块：

| 模块 | 职责 | 核心组件 |
|---|---|---|
| **demandhub-common** | 公共基础 | `Result`/`ErrorCode` 统一响应体；`UserContextFilter`（只信网关注入头）；`@RequireRole` + AOP（**ADMIN 直通**）；`DataScopeInterceptor`（MyBatis 拦截器，自动过滤 demand SELECT）；`AuditMetaObjectHandler`（自动填充 created_by/updated_by）；`GlobalExceptionHandler`（HTTP 200 + body `{code,message,data}`） |
| **demandhub-system** | 系统管理 | `AuthController`（PC 账密登录 / refresh / logout / me）；渠道 SSO：`ChuangjinLsSsoClient`、`ChannelSsoTicketVerifier`（env 三件套优先于 `demand_channel.config_json`）、`SecretCrypto`（AES-GCM）；`ChannelUserMatcher` / `UserMergeService`（渠道用户映射合并）；`OrgService`（物化路径子树匹配）；`RoleGrantService`（角色族 + demand_type_scope + org 范围） |
| **demandhub-demand** | 需求核心 | 自研轻量状态机 `DemandStateMachine`（`state_machine_config` 表驱动、热加载，**ADMIN 角色校验直通**）；`DemandNoGenerator`（Redis 锁 + DB 乐观锁，TECH/MATL/TRAIN-YYYYMMDD-NNN 无空洞）；`DemandEventRelay`（事务提交后 Spring 事件 → RocketMQ）；`SlaScanJob`（30s 扫描 + Redis 去重告警）；`StatDailyJob`（5min 增量聚合 `demand_stat_daily`）；`ReportExportExecutor`（POI 异步导出）；类型扩展表 tech/material/training |
| **demandhub-notification** | 通知中心 | `DemandEventConsumer` 订阅需求事件 → `TemplateService`（`${demand_no}` 变量渲染）→ `PreferenceService`（用户可关非关键通知）→ `RecipientResolver` → 站内信落库 + `WecomPushProducer/Consumer`（延迟队列指数退避，最多 5 次） |
| **demandhub-agent** | AI 助手 | `AgentGuideController`（SSE 流式提报引导）；`LlmClient` 双实现按 `@ConditionalOnProperty(demandhub.integration.llm.mock)` 互斥装配：**MockLlmClient**（默认，本地/测试确定性）/ **RealLlmClient**（火山方舟，OpenAI 兼容协议 REST 直连无 SDK：chat 走 `/chat/completions` + JSON mode，embedding 走 `/embeddings` 或多模态 `/embeddings/multimodal`；连续失败 3 次进入 60s 冷却，超时/5xx/解析失败 → 1401 前端降级手动流程）；`LlmSwitch` 运行期切换模拟故障；`RagService` + `RagVectorizeConsumer`（MQ 异步向量化）；`PromptTemplateService`（方舟提示词配置 `09-ark-llm-prompt.sql`） |
| **demandhub-gateway** | 网关 | Spring Cloud Gateway；`AuthFilter`：JWT 验签 + Redis 会话存在性校验；剥离客户端伪造用户头，注入 `X-User-Id` / `X-User-Uid` / `X-User-Roles` / `X-Channel`；CORS；按路径路由四模块 |
| **demandhub-server** | 单体装配 | 合并四业务模块为单进程（H5 Publish 部署形态）；Servlet 版 `AuthFilter` 统一鉴权；`context-path=/api` 与微服务形态路径完全一致，nginx / 前端 / e2e 零改动 |

## 3. 两种部署形态（代码同构）

```mermaid
%%{init: {'theme':'base', 'flowchart':{'useMaxWidth':false, 'htmlLabels':true, 'nodeSpacing':70, 'rankSpacing':90}, 'themeVariables':{'fontSize':'20px', 'background':'#ffffff', 'mainBkg':'#ffffff', 'primaryColor':'#ffffff', 'primaryBorderColor':'#ff7f00', 'primaryTextColor':'#000000', 'lineColor':'#ff7f00', 'clusterBkg':'#ffffff', 'clusterBorder':'#ff7f00', 'edgeLabelBackground':'#ffffff'}}}%%
flowchart LR
    subgraph A["形态 A：微服务（dev / test / prod 编排）"]
        direction TB
        G["gateway :8080"] --> S1["system :8081"]
        G --> D1["demand :8082"]
        G --> N1["notification :8083"]
        G --> A1["agent :8084"]
    end
    subgraph B["形态 B：单体装配（H5 Publish 部署）"]
        direction TB
        SRV["demandhub-server :8080<br/>scanBasePackages 合并四模块<br/>Servlet AuthFilter 统一鉴权<br/>context-path=/api"]
    end

    linkStyle default stroke:#ff7f00,stroke-width:2.5px,color:#000000
    style A fill:#ffffff,stroke:#ff7f00,stroke-width:2px,color:#000000
    style B fill:#ffffff,stroke:#ff7f00,stroke-width:2px,color:#000000
```

## 4. 环境拓扑

| 环境 | 编排文件 | 关键端口（宿主） | 说明 |
|---|---|---|---|
| dev 中间件 | `deploy/docker-compose.yml`（demandhub-infra，6 容器） | MySQL 3307 / Redis 6379 / MinIO 9000·9001 / Nacos 8848·9848 / RocketMQ 9876·10909·10911 | 业务模块本地 IDE 启动：网关 8080、system 8081、demand 8082、notification 8083、agent 8084；LLM 默认 Mock |
| test | `deploy/docker-compose.test.yml`（demandhub-test，13 容器） | Nginx 8088（同域）/ 网关 8180 / MySQL 3317 / Redis 6380 / MinIO 9010·9011 / Nacos 8858 / 契约 Mock 8099 | `CHANNEL_SSO_MOCK=false`，verify 回源走契约 Mock（严格验签）；LLM 默认 Mock（e2e 确定性），页面验证真实模型时 shell 注入 `DEMANDHUB_INTEGRATION_LLM_MOCK=false` + `LLM_API_KEY` |
| prod | `deploy/docker-compose.prod.yml`（demandhub-prod） | Nginx 80 / 网关 8080 | `CHANNEL_SSO_MOCK=false` 强制；`SECRET_STORE_KEY` / `CHANNEL_LS_*` / `LLM_API_KEY` env 注入（`:?` 缺失即拒启）；agent 强制 `DEMANDHUB_INTEGRATION_LLM_MOCK=false` 走火山方舟真实模型 |

## 5. 核心链路

### 5.1 渠道 SSO 登录（H5）

```
创金零售 App → https://host/h5/report?from=chuangjinls&ticket=xxx（TTL 60s，URL 只带 ticket）
  → GET /api/system/auth/channel-sso（白名单）
  → ChannelSsoTicketVerifier 验签 → verify 回源渠道换取身份
  → 渠道用户映射 / 合并（ChannelUserMatcher / UserMergeService）
  → 签发 JWT（access 2h / refresh 8h）+ Redis 会话（auth:session:{jti}）
  → 后续请求：AuthFilter 验签 + Redis 会话校验 → 注入用户头（X-Channel 来自会话，不信前端）
```

### 5.2 需求流转与通知（异步解耦）

```
提报 / 流转操作 → DemandStateMachine.transition()（配置表校验，ADMIN 直通）
  → 同事务：demand 更新 + demand_transition_log 落库 + 发布 DemandTransitionEvent（Spring）
  → AFTER_COMMIT：DemandEventRelay → RocketMQ DEMAND_EVENT_TOPIC（失败只告警不阻塞主流程）
  → notification 消费：模板渲染 → 偏好过滤 → 站内信落库 + 企微 MQ 推送（延迟重试 ≤ 5 次）
```

### 5.3 AI 提报引导（SSE + 火山方舟）

```
PC / H5 → /api/agent/guide/**（SSE，Nginx proxy_buffering off）
  → AgentGuideService → LlmClient（Mock / RealLlmClient 按 env 互斥装配）
  → 火山方舟 /chat/completions（JSON mode）流式输出
  → 失败策略：超时 / 5xx / 解析失败 → LlmUnavailableException(1401) 前端降级手动流程；
    连续失败 3 次进入 60s 冷却期，期间直接降级不打平台，冷却结束自动恢复探测
  → 解析结果回填表单（高亮 + 角标）→ 缺失要素逐项追问
```

## 6. 安全与横切约束

- **统一鉴权**：真实 401 只来自 AuthFilter（网关 / 单体 Servlet 版）；业务接口异常一律 HTTP 200 + `{code,message,data}`
- **头信任边界**：业务模块只信网关注入的 `X-User-*` / `X-Channel`；绕过网关直连 8081~8084 返回 401
- **ADMIN 超级用户全线直通**（产品决策）：`@RequireRole` 鉴权、`DataScopeService` 数据范围、`OrgScopeService` 组织范围、`DemandStateMachine` 角色校验均放行
- **数据权限**（非 ADMIN）：`DataScopeInterceptor` 按角色族（EXECUTIVE 全量 / MANAGER / HANDLER）+ `demand_type_scope` + org 物化路径子树自动过滤查询；任何登录用户可见自己提报的需求
- **并发安全**：需求认领 = Redis 分布式锁 + DB 乐观锁双保险；需求单号并发无空洞
- **密钥管理**：`SECRET_STORE_KEY`（渠道配置 ENC: 密文 AES-GCM 主密钥）、`CHANNEL_LS_*`、`LLM_API_KEY` 一律 env 注入，不落库、不入仓库；prod 缺失即拒绝启动
