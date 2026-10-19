# DemandHub OneID 身份体系 · 分期实施计划

| 项 | 内容 |
|---|---|
| 版本 | v1.0 |
| 日期 | 2026-10-17 |
| 状态 | 待评审（方案已获原则认可，本文档为落地计划） |
| 前置文档 | 《OneID 身份模型方案》（对话内已评审：人/身份分表、三种归并手段、三期路线） |

---

## 1. 背景与目标

### 1.1 要解决的问题

当前 `dh_user` 把"这个人是谁"与"他用什么方式登录"存在同一行：

- 渠道 SSO 登录 → 按 `wecom_userid` 建档（一行）
- 管理员建账密号 → `wecom_userid` 落 `acct:<账号>` 占位（另一行）
- 未来接入新渠道 → 渠道侧用户编号不同 → 又一行

同一个人多条用户记录，导致：历史数据割裂（提报单、处理单、工时分挂在不同 ID 下）、权限重复配置、渠道用户无法升级为正式用户。

### 1.2 目标

1. **OneID**：一个人无论用几种渠道/方式登录，系统内只对应一个用户（一行 `dh_user`）
2. **可扩展**：未来新增渠道 = 新增一种"身份类型" + 复用统一身份解析服务，权限/白名单/业务代码零改动
3. **平滑演进**：分三期上线，每期独立可验收、可回滚，不停机、不丢数据

### 1.3 非目标（本期不做）

- 不做跨企业主体的身份联邦（外部机构用户互通）
- 不做用户自行解绑身份（解绑一律走管理员，防误操作锁死账号）
- 不改动需求/状态机/看板等业务逻辑本身

---

## 2. 现状盘点（改动基线）

### 2.1 用户表关键字段（`dh_user`，迁移 head=0013）

| 字段 | 现状用途 | 目标去向 |
|---|---|---|
| `id` | 主键，全部业务外键的挂点 | **保留不动**（OneID 的"人"ID） |
| `wecom_userid` | 渠道用户存真实渠道ID；账密用户存 `acct:<login>` 占位 | 一期起登录不再读取，三期废弃 |
| `login_account` / `password_hash` | 账密登录凭证 | 一期迁入身份表，三期废弃 |
| `channel` | 建档来源渠道 | 保留（记录"人"的首次来源），身份表另有自己的 channel |
| `role` / `type_scope` / `status` / `dept_*` | 人的属性 | **保留不动** |

### 2.2 登录链路现状

| 入口 | 位置 | 现状行为 |
|---|---|---|
| `GET /channel-sso` | `app/api/auth.py:89` | 验渠道 ticket → `user_service.upsert_from_sso` 按 `wecom_userid` 查/建 → 发 JWT |
| `POST /login` | `app/api/auth.py:159` | `auth_service.login_by_password` 按 `login_account` 查 → 校验密码/锁定/状态 → 发双 token |
| JWT 载荷 | `app/core/security.py:35-42` | `sub=user.id`、`uid=wecom_userid`、`channel`——鉴权以 `sub` 为准 |

### 2.3 渠道白名单现状（0011，已上线）

SSO 登录前按 `channel + wecom_userid` 校验白名单（未命中报 1123）。**校验发生在建档之前，对象是"渠道凭证"本身**——拆表后该校验逻辑无需变化，一期只需明确其校验时点仍在身份解析之前。

### 2.4 业务外键依赖（合并工具的过户清单，共 17 张表 18 列）

| 表 | 列 |
|---|---|
| demand | `submitter_id`、`assignee_id` |
| demand_change_log | `changed_by` |
| demand_attachment | `uploaded_by` |
| agent_session | `user_id` |
| agent_draft | `created_by` |
| demand_transition_log | `operator_id` |
| assignment | `operator_id` |
| solution | `author_id` |
| review | `reviewer_id` |
| comment | `author_id` |
| effort_log | `user_id` |
| notification | `receiver_id` |
| notification_preference | `user_id` |
| report_export_task | `requester_id` |
| demand_role_grant | `user_id`、`granted_by` |
| refresh_token | `user_id` |
| （审计）demand_channel_whitelist_log 等操作人字段 | 若有操作人列一并纳入 |

---

## 3. 目标模型

### 3.1 两张表

**人表 `dh_user`**（一行 = 一个人）：字段基本不变，仅三期做减法。

**身份表 `dh_user_identity`（新建）**：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | bigint PK | — |
| user_id | bigint FK→dh_user.id | 这是谁 |
| identity_type | varchar(16) | `WECOM`（企微）/ `ACCOUNT`（账密）/ `MOBILE`（手机号）/ `DINGTALK` 等（新渠道 = 新类型） |
| identity_value | varchar(128) | 该渠道内唯一编号：企微userid / 登录账号 / 手机号 |
| channel | varchar(32) NULL | 该身份的来源渠道码（账密类为空） |
| credential | varchar(128) NULL | 凭证，仅 `ACCOUNT` 类存密码哈希 |
| is_verified | tinyint | 渠道带回且可信=1；待确认撮合=0 |
| created_at / updated_at | datetime | — |

**约束**：`UNIQUE(identity_type, identity_value)` —— 一把钥匙只能开一户门，这是 OneID 的根基。

**白话**：`dh_user` 是户口本（一人一本），`dh_user_identity` 是钥匙串（一人多把）。角色、类型权限、部门、状态全部记在户口本上，与用哪把钥匙进门无关。

### 3.2 统一身份解析服务（所有登录入口共用）

```
resolve_or_create(identity_type, identity_value, channel, 附带信息[姓名/手机号/部门]):
    命中身份表 → 返回对应的"人"（顺带用附带信息更新人表的姓名/部门快照）
    未命中 → （二期起：先按手机号撮合）仍无 → 新建"人"+ 挂上该身份（+可信手机号身份）
```

### 3.3 多渠道归并三手段（二期实现，优先级从高到低）

| 手段 | 触发方式 | 规则 |
|---|---|---|
| ① 手机号自动撮合 | 新渠道首次 SSO，渠道带回手机号 | 手机号命中已有 `MOBILE` 身份 → 新身份直接挂到同一人（is_verified=1），写审计日志；**只挂钥匙不删数据** |
| ② 登录态绑定 | 已登录用户在个人页主动绑定 | 已登录态即本人证明，跳目标渠道授权后挂身份，最安全 |
| ③ 管理员合并 | 管理端选两个用户合并 | 指定主账号；副账号的身份+全部业务数据过户（§2.4 清单），副账号置 DISABLED 并吊销其 refresh token；全程审计，可追责 |

> 防护原则：自动撮合只"加钥匙"，任何"并户口"级操作必须人工（管理员）确认；手机号回收再分配场景由手段③兜底纠错。

---

## 4. 分期路线图

| 期 | 代号 | 目标 | 迁移 | 依赖 |
|---|---|---|---|---|
| 一期 | 打地基 | 身份表落地，全部登录入口切换走身份表，存量数据回填 | 0014 | — |
| 二期 | 通归并 | 手机号撮合 + 登录态绑定 + 管理员合并工具 | 0015 | 一期稳定运行 |
| 三期 | 收口子 | 废弃老字段，发布新渠道接入标准 | 0016 | 二期稳定运行 ≥ 2 周 |

---

## 5. 一期：打地基（身份表 + 登录链路切换）

**目标**：用户无感的前提下，把"查人"逻辑从 `dh_user.wecom_userid / login_account` 切换到身份表。本期结束后，模型已是 OneID，但归并手段尚未开放。

### 5.1 数据库（迁移 0014）

1. 建 `dh_user_identity` 表（§3.1 结构 + 唯一约束 + `user_id` 索引）
2. 存量回填（一次性 SQL，幂等）：
   - `channel = 'ACCOUNT'` 的用户 → 生成 `ACCOUNT` 身份：`identity_value = login_account`、`credential = password_hash`
   - 其余渠道用户 → 生成 `WECOM` 身份：`identity_value = wecom_userid`、`channel = 原 channel`
   - 回填校验：回填行数 = `dh_user` 总行数；唯一约束无冲突（`acct:` 命名空间与真实渠道ID天然隔离，不会撞）
3. `dh_user.wecom_userid / login_account / password_hash` **保留**（一期仅作对照，登录不再读取）

### 5.2 后端改动点

| 文件 | 改动 |
|---|---|
| `app/db/models.py` | 新增 `UserIdentity` 模型 |
| `app/services/identity_service.py`（新建） | 统一身份解析：`resolve(identity_type, identity_value)` / `resolve_or_create(...)` / `bind(...)`；建档逻辑从 `user_service.upsert_from_sso` 迁入并复用（姓名/部门快照更新规则不变） |
| `app/api/auth.py` `/channel-sso` | ticket 验签后 → `identity_service.resolve_or_create('WECOM', 渠道userid, channel, ...)`；白名单校验时点保持在解析之前（逻辑不变） |
| `app/services/auth_service.py` | `login_by_password` 改按 `('ACCOUNT', login_account)` 查身份 → 取人 → 校验 credential；锁定/禁用/强制改密规则不变 |
| `app/api/admin_users.py` | 新建账密用户 = 建人 + 建 `ACCOUNT` 身份（占位 `acct:` 写法废弃）；登录账号唯一性校验改查身份表 |
| `app/core/security.py` | `issue_token` 载荷不变（`sub` 仍是人 ID），保证已签发票据自然过渡 |

### 5.3 前端改动

无（登录页、管理端界面零变化；用户列表数据源不变）。

### 5.4 测试

- 单测：身份解析（命中/未命中建档/唯一冲突）、账密登录全路径（锁定、强制改密、refresh 旋转不受影响）、SSO 查建回归、白名单 1123 回归
- 回归：既有 484 例全量 + 新身份模型专项
- 冒烟：回填后逐类用户登录验证（渠道 SSO、账密、admin）

### 5.5 验收标准

1. 迁移后身份表行数 = 用户行数，抽样 10 人登录全部成功
2. 账密登录的锁定/强制改密/重置密码行为与迁移前一致
3. 渠道 SSO 新用户自动建档正常，白名单拦截正常
4. 老 JWT 在有效期内可正常调用（`sub` 未变）

### 5.6 回滚

迁移可逆（`downgrade` 删表）；若上线后异常，切回上一版镜像/代码即可——`dh_user` 老字段一期仍在且未被写入破坏，双跑无脏数据。

---

## 6. 二期：通归并（三种手段落地）

**目标**：提供"把多个身份/账号归为一人"的完整能力，解决历史已裂开的账号 + 未来多渠道自动归一。

### 6.1 数据库（迁移 0015）

1. 建 `dh_user_merge_log` 审计表：操作人、主账号、副账号、过户明细计数、时间、备注
2. （按需）`dh_user` 加 `merged_into` 列：副账号被合并后指向主账号，登录时给出明确提示

### 6.2 手机号自动撮合

- SSO 回携带手机号时：`resolve_or_create` 先查 `('MOBILE', 手机号)`
  - 命中 → 新渠道身份直接挂到该人（is_verified=1），写撮合审计
  - 未命中 → 正常建档，同时建 `WECOM` + `MOBILE` 两条身份
- **配置开关**：`oneid_mobile_match_enabled`（默认开；出现异常撮合投诉时可一键关闭，降级为手段③）
- 手机号渠道不返回/用户不授权 → 跳过撮合，不影响登录

### 6.3 登录态绑定（个人页）

- H5/管理端个人页新增"绑定登录方式"：已登录 → 跳目标渠道授权 → 回携凭证 → `identity_service.bind(当前人, 新身份)`
- 冲突处理：该身份已被他人占用 → 报错提示"该渠道账号已被其他用户绑定，请联系管理员合并"

### 6.4 管理员合并工具

- 管理端【用户管理】新增"合并用户"入口：选主账号 + 副账号 → 二次确认（展示双方将过户的数据量）→ 执行
- 过户动作（单事务）：
  1. §2.4 清单 18 列外键 `UPDATE ... SET col=主 WHERE col=副`
  2. 副账号身份全部移到主账号
  3. 副账号 `status=DISABLED`、`merged_into=主ID`、refresh token 全吊销
  4. 角色冲突处理：以主账号为准（主账号角色/类型权限不变）
  5. 写 `dh_user_merge_log`
- 权限：仅 ADMIN

### 6.5 测试

- 撮合：命中/未命中/开关关闭/渠道不返手机号 4 条路径
- 绑定：正常绑定、身份被占冲突
- 合并：过户后 18 列零残留、副账号全端不可登录、审计完整、合并后类型权限以主账号生效
- 冒烟：构造"同一人的渠道号 + 账密号"执行合并，验证历史需求单归一

### 6.6 验收标准

1. 同一人从两个渠道登录，看到的是同一份"我的需求"
2. 合并操作可演示、可审计、副账号彻底失效
3. 撮合开关关闭后系统行为退化为纯人工合并且无副作用

---

## 7. 三期：收口子（废弃老字段 + 接入标准）

**目标**：清理过渡遗产，固化新渠道接入规范。前置条件：二期稳定运行 ≥ 2 周，无未处理的合并工单。

### 7.1 数据库（迁移 0016）

- 删除 `dh_user.wecom_userid`、`login_account`、`password_hash`（删除前全量备份 + 导出归档）
- `issue_token` 载荷移除 `uid` 字段（`sub`/`name`/`channel` 保留）

### 7.2 新渠道接入标准（文档化）

新渠道上线 checklist：① 定 `identity_type` 与渠道码 → ② 实现 SSO ticket 验签适配器 → ③ 回调统一调 `identity_service.resolve_or_create` → ④ 白名单按需配置 → ⑤ 回归登录与权限。**明确承诺：接入新渠道不触碰权限、白名单、业务代码。**

### 7.3 文档更新

《数据库表结构说明》《系统架构文档》同步至 OneID 终态；本计划归档。

### 7.4 验收标准

1. 全量测试通过，无代码再引用被删字段
2. 按 checklist 在测试环境模拟接入一个"演示渠道"，1 天内跑通登录

---

## 8. 兼容与风险控制（贯穿三期）

| 风险 | 对策 |
|---|---|
| 迁移期已登录用户票据失效 | JWT 以 `sub=user.id` 鉴权，一期载荷不变 → 老票据自然有效至过期 |
| 回填错漏导致用户登不进 | 一期老字段只读保留，登录异常时可秒级回滚代码；回填 SQL 幂等可重跑 |
| 手机号错并（号码回收再用） | 撮合只挂身份不删数据 + 全程审计 + 管理员合并工具可纠错 + 开关可关 |
| 合并操作不可逆 | 合并前导出双方数据快照归档；副账号仅 DISABLED 不物理删除 |
| 白名单语义漂移 | 一期明确校验时点不变（身份解析前）；三期写入接入标准 |

---

## 9. 里程碑一览

| # | 交付物 | 验收方式 |
|---|---|---|
| 一期 | 迁移 0014 + 登录链路切换 + 全量测试绿 | §5.5 四条 + 冒烟记录 |
| 二期 | 撮合/绑定/合并三能力 + 审计 | §6.6 三条 + 演示 |
| 三期 | 迁移 0016 + 接入标准文档 | §7.4 两条 |

每期开工前出当期的详细开发清单（到文件/接口级），完工后出验收记录归档。

---

*本计划基于 2026-10-17 代码基线（迁移 head=0013、后端 484 例测试）编制；若基线变化，开工前需重新盘点 §2。*
