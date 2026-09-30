# DemandHub Python V1

首批客户端为创金零售内嵌 H5。V1 收集、完善和整理需求，正式记录使用提交时的标准快照；Java、PC、旧部署和旧 phase 脚本保留。

## 本地运行

从仓库根目录启动隔离依赖：`docker compose -f deploy/docker-compose.dev.yml up -d --build`。MySQL8 暴露127.0.0.1:3308，严格SSO契约Mock为127.0.0.1:8099，卷和项目名均独立于旧版。

进入 `server/`，执行 `cp .env.example .env`，仅在本机填写真实凭据。随后：

```sh
uv python install 3.12
uv sync --frozen
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

关闭访问日志是为了避免 GET SSO ticket 出现在URL日志中。应用日志也不回显token、上游响应原文、SQL参数或连接URL。开发登录只在APP_ENV=dev/test且AUTH_DEV_LOGIN=true时注册。

健康检查路径 `/demandhub-api/health`：DB正常200，异常503。公开路由使用实际前缀，Kong应保留路径（strip_path=false）。开发OpenAPI路径 `/demandhub-api/openapi.json`，生产禁用。

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

上线前验证：生产dev-login404；health；Kong前缀与SSE；H5域名配置；真实endpoint评测与延迟；创金零售测试SSO；iOS/Android真机。当前本地验收不能替代平台上线。

回滚通过发布平台恢复上一镜像tag/digest与H5包；本次无存量迁移。不得自动downgrade生产数据库，数据库回退须单独评估。

发布记录只记commit/tag/digest/产物路径和验证结果，不保存凭据。本轮未发布、未push。

## 2026-09-30 本地验收记录

- Python3.12.14，`uv sync --frozen`完成；独立MySQL8.0.46 healthy，demandhub_test执行upgrade → downgrade base → upgrade成功。
- 后端默认测试已覆盖草稿不完整、客户端幂等、实际需求20并发提交、同草稿并发、回滚编号与会话、来源保护、历史快照、认证/禁用、SSE提交后终态与竞态。最终 `uv run pytest -q --tb=short`：123 passed，2 deselected；`uv run ruff check app tests alembic ../scripts/e2e_mvp.py`：All checks passed。
- `docker build -t demandhub-python:local .`成功；容器`demandhub-python-local-e2e`在127.0.0.1:18000映射8000，production配置、uid10001，无pytest/ruff，health UP，dev-login404。
- 外置Ark协议Mock在127.0.0.1:8188；`python scripts/e2e_mvp.py --api-base http://127.0.0.1:18000/demandhub-api --agent-mode mock`通过，顺序验证processing/message/structured/done与原请求重放、2条持久消息、提交、Markdown、管理员XLSX和撤销。
- 开发8000同一脚本mock流式通过；`--agent-mode none`验证独立手填API闭环通过。真实方舟Key/endpoint评测、Kong、平台发布及创金零售真机链路仍待外部验收。

临时Ark进程与业务验收容器只用于本地验证，停止方法：`docker stop demandhub-python-local-e2e`；独立开发依赖停止方法：`docker compose -f deploy/docker-compose.dev.yml stop`。本轮保留测试环境供审计，不删除旧版或已有数据卷。
