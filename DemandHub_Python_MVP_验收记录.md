# DemandHub Python MVP 验收记录

日期：2026-09-30。基线：`main@783c80f`。工作分支：`codex/python-mvp`。

## 结论

代码实现与本地验收完成。主 Agent 审计发现的问题已修复并回归，当前没有遗留的本地交付阻断项。真实模型、公司发布平台、创金零售及真机验收尚未执行。本地验收结束时未上传、发布、push 或提交 Git commit；后续测试镜像推送单独记录在 `server/artifacts/`。

本轮只实现需求收集、完善和整理记录，不含分派交付及 CLI/Skill 客户端。Java、PC、旧部署和旧 phase 脚本未改动；删除旧系统须等真正上线并稳定至少三个工作日。

## 执行记录

实施基线为重构方案 v1.3、实施计划 v1.1。主 Agent 修订文档、审计代码并独立复跑最终验收。具体代码及审计修复均由实现协作聊天的三个 `gpt-6.1-sol / high` Subagent 编写，实际模型配置已确认。

实现协作聊天：`01a0f1ff-d13b-7382-976f-396bc3b2c7ba`，标题为“DemandHub Python MVP 实现协作”。

| Subagent | 范围 |
|---|---|
| backend_foundation | 配置、认证、数据库、需求、导出、容器、本地 E2E |
| agent_rules_stream | 标准、抽取、规则、会话、SSE、真实模型评测脚手架 |
| h5_client | H5 页面、登录、草稿与对话交互、打包 |

## 最终检查

环境：Python 3.12.14、MySQL 8.0.46、Node 25.9.0、Docker 29.7.2。数据库使用本轮独立开发编排，测试库为 `demandhub_test`，没有操作旧系统数据库。

| 验证 | 实际结果 |
|---|---|
| MySQL 迁移 | 实现代理执行隔离测试库 upgrade → downgrade base → upgrade；主 Agent 对开发库 upgrade 成功 |
| 后端 `uv run pytest` | 主 Agent 独立复跑：123 passed、2 deselected，2.10 秒；排除的 2 项为真实模型评测 |
| 后端 `uv run ruff check app tests alembic` | 主 Agent 独立复跑通过 |
| MySQL 事务/并发 | 包含 20 份需求并发提交、同请求 10 并发创建、同草稿 10 并发提交、失败回滚编号与会话状态 |
| H5 `npm test` | 主 Agent 独立复跑：9 个文件、48 项测试全部通过 |
| H5 `npm run typecheck` / `npm run build` | 主 Agent 独立复跑通过；生产构建 394 modules |
| 生产配置容器 | 本地镜像构建成功；主 Agent 验证 uid 10001、无 pytest/ruff、health UP、dev-login 404 |
| HTTP SSE E2E | 主 Agent 对 18000 容器执行 Mock 流式闭环通过；需求 11、编号 `TECH-20260930-010`、2 条持久化消息 |
| 无 Agent HTTP E2E | 主 Agent 对 8000 执行纯手填闭环通过；需求 12、编号 `TECH-20260930-011`、0 条消息 |
| Git | `git diff --check` 通过；变更保留在工作区，未提交/推送 |
| H5 包 | 打包脚本 warnings=[]；主 Agent 验证 22 个条目、根目录 index.html、相对资源路径、无源码/环境文件/脚本；zip 内容与独立最新构建逐文件一致 |

后端命令在 `server/` 执行，前端命令在 `frontend/h5/` 执行。HTTP E2E 在仓库根目录执行：

```sh
python3 scripts/e2e_mvp.py --api-base http://127.0.0.1:18000/demandhub-api --agent-mode mock
python3 scripts/e2e_mvp.py --api-base http://127.0.0.1:8000/demandhub-api --agent-mode none
```

Mock 流式闭环经过真实 TCP、SSO HMAC 契约验证、业务服务、MySQL、模型 HTTP 协议模拟器；校验 processing/message/structured/done 顺序及 requestId、落库后原请求重放、提交、Markdown、管理员 XLSX 和撤销。Mock 固定结果不代表真实模型理解能力。

## 浏览器验收

主 Agent 使用 Chrome、390×844 视口验证了以下实际页面行为，结束后恢复原窗口尺寸：

- 不完整草稿保存、从“我的需求”恢复、继续填写并提交；提交详情保留质量缺口，未错误显示信息全部到位。
- AI 不可用时保留用户输入，手工填报仍可使用。
- AI 流式回复后草稿版本递增、字段回填、历史恢复；刷新相同 revision 的草稿恢复对应质量清单。
- 手改标题“人工确认标题保留”及主动清空“价值与影响”经过下一轮 AI 后保持原值，质量为 6/7，缺失项继续追问。
- 创金零售式外层 ticket 配合 hash 路由进入管理员页；认证后 URL 清理为 `/#/admin`。
- 管理员默认显示 12 条、筛选已提交后 1 条、重置后恢复 12 条。非管理员 API 拒绝、跨用户需求不可访问也已验证。

导出 API 返回的 Markdown 内容及 XLSX 文件格式已通过 HTTP E2E，Bearer 下载、业务错误和过期登录行为有前端回归测试。Chrome 原生下载保存弹窗受到 Mac 锁屏限制，实际浏览器落盘未确认，需在解锁或真实宿主环境补验。

## 审计问题闭环

以下发现均已交指定模型 Subagent 修复，并通过相应回归；主 Agent 复核最终代码与测试。

| 编号 | 问题与修复 |
|---|---|
| R1 | “不要跳过”或引用语句被子串匹配误判；改为整句明确跳过表达 |
| R2 | LLM 失败计数引用缺失配置、流读取异常未统一降级；补配置与异常/冷却测试 |
| R3 | contract-mock 被业务 .dockerignore 排除导致构建失败；改用独立测试构建上下文 |
| R4 | 空白日期、非法紧急度可能进入错误存储路径；归一空值并统一校验 |
| R5 | Agent 全量合并误改未变化字段的来源；保留 default/user、以落库来源为响应准据 |
| R6 | 模型非法类型绕过格式修复与失败统计；统一进入一次修复和降级路径 |
| R7 | 创建响应丢失后刷新无法用同 ID 原内容恢复；持久化原请求并在恢复后保存后续手改 |
| R8 | 明确 revision 冲突后无限复用失效请求；保留文字，改用新 ID 和最新 revision；未知结果仍按原 ID 重放 |
| R9 | 迟到的旧草稿/会话响应串写当前页面；增加请求代次和绑定校验 |
| R10 | 物料/培训自由文本子类写入短枚举列导致 500；仅科技枚举写入 subtype_code |
| R11 | pytest 找不到 app 包；明确 pythonpath 并验证标准测试命令 |
| R12 | 标准 loader 模块/实例名称冲突导致提交 500；显式导入快照函数并用真实 HTTP 回归 |
| R13 | StandardField 多根节点导致 class 丢失、高亮无效；增加稳定根节点与组件测试 |
| R14 | 评测提示词/多轮状态偏离生产，模型耗时冒充完整延迟；共用生产 build_prompt、串联状态、分别报告模型与 GuideService 延迟，来源保护断言强制失败 |
| R15 | 刷新 AI 草稿丢失质量清单；仅恢复与当前 demand/session/revision 匹配的最后响应 |
| R16 | 管理员“全部”空筛选触发后端校验失败；列表、重置、我的需求及 XLSX 共用非空筛选转换 |

## 本地产物

- H5：`frontend/h5/artifacts/demandhub-h5.zip`，218663 bytes。
- H5 SHA-256：`31981691566beb8fa44f0f97c8d298df7118024c3f9cfbfdf75dfb6c5c1743db`。
- 后端镜像：`demandhub-python:local`。
- 本地 image ID：`sha256:1130a8d56bc1d0f2e650bf65aafe587b8cae910e2798b13af979ccf9561a100d`。这是本地镜像 ID，未推 Harbor，不是仓库 digest。
- 本地验收基线为 `783c80f` 加本轮工作区修改；后续测试镜像推送将先提交源码，再绑定镜像与 commit，详见对应发布记录。

启动及环境变量见 `server/README.md` 和 `frontend/h5/README.md`。本轮临时业务、模型 Mock、Vite 进程及独立开发编排在收尾停止，镜像、zip 与数据库卷保留。未删除旧系统文件或数据卷。

## 外部验收待办

1. 提供真实方舟配置后，显式运行 `uv run pytest -m eval -o addopts='' tests/eval`。已准备 20 案例、87 个抽取断言、40 个判质断言与完整 GuideService 延迟报告；本轮没有真实质量/延迟成绩。
2. 提供发布目标和配置后，验证 Harbor 镜像及 H5 包部署、平台数据库、Kong `/demandhub-api` 路径保留及 SSE。
3. 在创金零售测试入口完成真实 SSO、域名白名单及 iOS/Android 宿主的交互与文件下载验收。

本记录不保存 token、ticket、真实密钥或数据库凭据。上述待办是上线条件，不能用本地 Mock 成功替代。
