# DemandHub Python V1

首批客户端为创金零售内嵌 H5。V1 收集、完善和整理需求，正式记录使用提交时的标准快照；Java、PC、旧部署和旧 phase 脚本保留。

## 本地运行

从仓库根目录启动隔离依赖：`docker compose -f deploy/docker-compose.dev.yml up -d --build`。MySQL8 暴露127.0.0.1:3308，严格SSO契约Mock为127.0.0.1:8199（容器内仍8099；宿主端口错开 Java test 栈同名契约Mock的8099，两套栈可同时运行），卷和项目名均独立于旧版。

进入 `server/`，执行 `cp .env.example .env`，仅在本机填写真实凭据。随后：

```sh
uv python install 3.12
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

关闭访问日志是为了避免 GET SSO ticket 出现在URL日志中。应用日志也不回显token、上游响应原文、SQL参数或连接URL。开发登录只在APP_ENV=dev/test且AUTH_DEV_LOGIN=true时注册。

Windows 本机两个已知环境坑（已踩过）：① 系统代理打开时 Python 会经 `urllib.getproxies()` 读取注册表代理，导致访问 127.0.0.1 的 verify/签票请求被错误代理——启动服务与跑 e2e 前必须设 `NO_PROXY=127.0.0.1,localhost`（大小写各一份）；② Windows Python 无 IANA 时区库，`Asia/Shanghai` 依赖 `tzdata` 包（已列入 dependencies，勿删）。

健康检查路径 `/demandhub-api/health`：DB正常200，异常503。公开路由使用实际前缀，Kong应保留路径（strip_path=false）。开发OpenAPI路径 `/demandhub-api/openapi.json`，生产禁用。

## 宿主参数测试联调

`CHANNEL_ENTRY_AUTH_MODE` 默认 `ticket`，现有 `/auth/channel-sso` 票据链路保留。仅在独立测试环境设置以下组合，才注册 `POST /demandhub-api/auth/channel-parameters`：

```env
APP_ENV=test
CHANNEL_ENTRY_AUTH_MODE=trusted_parameters
AUTH_DEV_LOGIN=false
```

`trusted_parameters` 在 dev/prod，或与 `AUTH_DEV_LOGIN=true` 同时使用时，启动校验直接拒绝。默认模式和生产环境中的参数入口返回404；此模式不需要开发登录。

请求JSON固定为 `userid`（必填，最多64字）、`authToken`（必填，最多4096字）、`userName`（必填，最多64字）、`department`（可省略/null，最多128字）。userid、userName去除两侧空格且不得为空；authToken仅检查非空和长度，**完全不验证宿主Token的真实性**。该模式仅用于测试联调，身份直接信任传入userid，不能作为正式宿主认证方案。

userid对应稳定用户身份，重复登录更新姓名/部门；停用账号仍拒绝登录。管理员只按 `ADMIN_WECOM_USERIDS` 中的账号标识判断，姓名、部门和宿主Token不授予权限。登录返回现有 `accessToken/tokenType/expiresIn/user`，其中accessToken为DemandHub自行签发的Bearer JWT。

宿主Token不传入持久化或JWT，不存储、不散列、不回显，不写入日志。参数DTO隐藏Token的repr和错误输入，校验/系统错误不回显请求值。测试与文档均使用合成Token，不需读取真实服务配置。

## 验证

```sh
uv run pytest
uv run ruff check app tests alembic
python ../scripts/e2e_mvp.py --agent-mode none
```

pytest只使用 `demandhub_test`，默认排除eval；`TEST_DATABASE_URL`可覆盖连接但库名必须相同。普通service fixture事务回滚；API/并发提交测试独立连接并在前后清理受控测试库。鉴权与业务使用同一个测试factory。不要并行启动两套数据库测试清理进程。

真实模型：仅在可信本机环境注入LLM_API_KEY，显式执行 `uv run pytest -m eval -o addopts='' tests/eval`。无真实Key的外置Ark mock需要显式配置ARK_BASE_URL到测试进程，并运行E2E `--agent-mode mock`；它只验证协议和闭环，不代表真实模型质量或延迟验收。可运行 `uv run python tests/ark_mock.py --port 8188`，业务服务自身没有假模型开关。

## 本地镜像

```sh
docker build -t demandhub-python:local .
```

Python3.12、uv版本固定；frozen安装只含生产依赖，启动直接运行.venv进程不联网安装。非root运行，先迁移再启动单个业务进程。首次发布单副本；扩副本前应把迁移提取为独立作业。`FORWARDED_ALLOW_IPS`默认127.0.0.1，按实际代理地址配置。

## 外部发布待验收

生产配置APP_ENV=prod、AUTH_DEV_LOGIN=false；平台注入DEMANDHUB_DATABASE_URL、JWT_SECRET、LLM_API_KEY/ARK_BASE_URL/LLM_CHAT_MODEL、CHANNEL_LS_BASE_URL/CHANNEL_LS_APP_KEY/CHANNEL_LS_APP_SECRET、ADMIN_WECOM_USERIDS。白名单为空则管理员接口全部拒绝。LLM_THINKING及超时/冷却配置按.env.example变量名注入。

上线前验证：生产dev-login404；**`CHANNEL_ENTRY_AUTH_MODE=ticket` 且 `/demandhub-api/auth/channel-parameters` 返回404（参数联调门已关闭，禁止把 TEST 的 trusted_parameters 配置复制到生产）**；health；Kong前缀与SSE；H5域名配置；真实endpoint评测与延迟；创金零售测试SSO；iOS/Android真机。当前本地验收不能替代平台上线。

回滚通过发布平台恢复上一镜像tag/digest与H5包；本次无存量迁移。不得自动downgrade生产数据库，数据库回退须单独评估。

发布记录只记commit/tag/digest/产物路径和验证结果，不保存凭据。本轮未发布、未push。

## 2026-10-09 平台 TEST 部署记录（参数联调门已开启）

- 发布平台 TEST 环境后端服务 `demandhub-api`（deploy id 625，镜像 `test-20261008105223-757802bd8d4d` 不变仅重建容器），经 `h5pub backend configure` 合并注入：`APP_ENV=test`、`CHANNEL_ENTRY_AUTH_MODE=trusted_parameters`、`AUTH_DEV_LOGIN=false`（其余键 DEMANDHUB_DATABASE_URL/JWT_SECRET/API_ROOT_PATH 未动）。
- 目的：创金零售小程序以 `?userid=&X-Auth-Token=&userName=&department=` 直参 URL 跳转联调，`POST /demandhub-api/auth/channel-parameters` 已注册（此前 404，H5 提示"参数联调登录尚未开启"）。已用真实参数端到端验证换 JWT 成功。
- **风险提醒**：该模式不验证宿主 Token 真伪，URL 即身份，属测试专用。生产上线必须改回 `CHANNEL_ENTRY_AUTH_MODE=ticket`（重新 configure + deploy 同镜像即可），并按上方上线前验证清单确认参数端点 404。

## 2026-09-30 本地验收记录

- Python3.12.14，`uv sync --frozen`完成；独立MySQL8.0.46 healthy，demandhub_test执行upgrade → downgrade base → upgrade成功。
- 后端默认测试已覆盖草稿不完整、客户端幂等、实际需求20并发提交、同草稿并发、回滚编号与会话、来源保护、历史快照、认证/禁用、SSE提交后终态与竞态。最终 `uv run pytest -q --tb=short`：123 passed，2 deselected；`uv run ruff check app tests alembic ../scripts/e2e_mvp.py`：All checks passed。
- `docker build -t demandhub-python:local .`成功；容器`demandhub-python-local-e2e`在127.0.0.1:18000映射8000，production配置、uid10001，无pytest/ruff，health UP，dev-login404。
- 外置Ark协议Mock在127.0.0.1:8188；`python scripts/e2e_mvp.py --api-base http://127.0.0.1:18000/demandhub-api --agent-mode mock`通过，顺序验证processing/message/structured/done与原请求重放、2条持久消息、提交、Markdown、管理员XLSX和撤销。
- 开发8000同一脚本mock流式通过；`--agent-mode none`验证独立手填API闭环通过。真实方舟Key/endpoint评测、Kong、平台发布及创金零售真机链路仍待外部验收。

临时Ark进程与业务验收容器只用于本地验证，停止方法：`docker stop demandhub-python-local-e2e`；独立开发依赖停止方法：`docker compose -f deploy/docker-compose.dev.yml stop`。本轮保留测试环境供审计，不删除旧版或已有数据卷。
