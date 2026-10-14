"""P2 状态机与全流程流转单测（2026-10-12）。

覆盖口径（对应验收门禁）：
- 12 态全路径：DRAFT→SUBMITTED→TRIAGE→ANALYZING→SOLUTION_REVIEW→CONFIRMED→IN_PROGRESS→ACCEPTANCE→DONE
- 非法流转统一 1001；角色守卫 403 与 ADMIN 直通
- ON_HOLD 叠加态：挂起中他事件拒绝、快照复原、日志 from/to 语义
- 并发领取仅一成功（1208，仅数据库行锁）
- 方案评审状态联动：PASS→CONFIRMED+expect_delivery_at+confirmed_at；REJECT→ANALYZING；同需求仅一个在评
- 验收三前置（1209）与验收双评分；退单 RETURN_POOL；comment 仅作者可改；split 实例化
- 规则热重载：配置表原子替换、坏配置跳过、空表回落内置兜底
"""
import asyncio
import json
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.errors import BizError, ErrorCode
from app.core.statemachine import engine
from app.db.models import (
    Assignment,
    Demand,
    DemandAttachment,
    DemandChangeLog,
    DemandRelation,
    DemandTransitionLog,
    Review,
    Solution,
    StateMachineConfig,
    User,
    now,
)
from app.services import (
    comment_service,
    demand_service,
    effort_service,
    flow_service,
    solution_service,
    triage_service,
)

ACD = {"A": {"techSubtype": "DATA_RPT"},
       "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各机构持仓汇总",
             "useScenario": "客户经理每天晨会前查看各机构持仓", "painPoint": "手工汇总20多个机构持仓每次近1小时"},
       "D": {"functionDescription": "按机构汇总前一交易日持仓并展示", "inputOutput": "输入交易流水输出持仓汇总报表",
             "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}

PLAN_DATE = date(2026, 11, 1)


# ---- 基座工具 ----

async def make_user(factory, name, wecom_userid, role="HANDLER"):
    async with factory() as db:
        async with db.begin():
            user = User(name=name, wecom_userid=wecom_userid, channel="CHUANGJIN_LS", role=role)
            db.add(user)
            await db.flush()
            db.expunge(user)
            return user


async def make_submitted(factory, user):
    """造一条 SUBMITTED 需求（完整要素直提），返回 demand_id。"""
    async with factory() as db:
        async with db.begin():
            demand = await demand_service.create_draft(db, user, {
                "clientRequestId": f"p2-{uuid4().hex}", "title": "晨会持仓报表", "demandTypeCode": "TECH",
                "content": "机构业务部客户经理每天晨会前查看持仓汇总", "urgency": "NORMAL",
                "elements": ACD, "fieldSources": {"demandTypeCode": "default"}})
            submitted = await demand_service.submit(db, user, demand.id, demand.revision)
            return submitted.id


async def insert_demand(factory, submitter, **overrides):
    """测试夹具：绕过流程直接落库一条需求（仅用于构造特定状态场景）。"""
    async with factory() as db:
        async with db.begin():
            demand = Demand(
                title="夹具需求", demand_type_code="TECH", content="内容", urgency="NORMAL",
                status="SUBMITTED", submitter_id=submitter.id, submitter_name=submitter.name,
                channel="CHUANGJIN_LS", client_request_id=f"raw-{uuid4().hex}",
                create_request_hash="raw", submitted_at=now(), revision=0)
            for key, value in overrides.items():
                setattr(demand, key, value)
            db.add(demand)
            await db.flush()
            return demand.id


async def get_demand(factory, demand_id):
    async with factory() as db:
        return await db.get(Demand, demand_id)


async def to_analyzing(factory, admin, handler, demand_id, by="assign"):
    async with factory() as db:
        async with db.begin():
            await triage_service.accept(db, admin, demand_id, None)
    async with factory() as db:
        async with db.begin():
            if by == "claim":
                await triage_service.claim(db, handler, demand_id)
            else:
                await triage_service.assign(db, admin, demand_id, handler.id, None)


async def to_confirmed(factory, admin, handler, demand_id, *, from_analyzing=False):
    """走到 CONFIRMED（含 APPROVED 方案），返回 solution_id。from_analyzing=True 表示已在 ANALYZING。"""
    if not from_analyzing:
        await to_analyzing(factory, admin, handler, demand_id)
    async with factory() as db:
        async with db.begin():
            solution = await solution_service.create(
                db, handler, demand_id=demand_id, spec_content="需求规格", solution_content="实现方案",
                plan_delivery_at=PLAN_DATE, remark=None)
            await solution_service.submit_review(db, handler, solution.id)
            solution_id = solution.id
    async with factory() as db:
        async with db.begin():
            await solution_service.review(db, admin, solution_id, result="PASS", opinion=None)
    return solution_id


async def to_in_progress(factory, admin, handler, demand_id):
    await to_confirmed(factory, admin, handler, demand_id)
    async with factory() as db:
        async with db.begin():
            await flow_service.start(db, handler, demand_id)


async def transition_logs(factory, demand_id):
    async with factory() as db:
        return list((await db.execute(select(DemandTransitionLog).where(
            DemandTransitionLog.demand_id == demand_id).order_by(DemandTransitionLog.id))).scalars())


@pytest.fixture
async def admin(session_factory):
    return await make_user(session_factory, "管理员", "p2-admin", role="ADMIN")


@pytest.fixture
async def handler(session_factory):
    return await make_user(session_factory, "处理人甲", "p2-handler")


@pytest.fixture
async def handler_b(session_factory):
    return await make_user(session_factory, "处理人乙", "p2-handler-b")


# ---- 1. 12 态全路径 ----

@pytest.mark.asyncio
async def test_full_happy_path(session_factory, user, admin, handler):
    did = await make_submitted(session_factory, user)
    assert (await get_demand(session_factory, did)).status == "SUBMITTED"

    await to_analyzing(session_factory, admin, handler, did)
    demand = await get_demand(session_factory, did)
    assert demand.status == "ANALYZING" and demand.assignee_id == handler.id

    solution_id = await to_confirmed(session_factory, admin, handler, did, from_analyzing=True)
    demand = await get_demand(session_factory, did)
    assert demand.status == "CONFIRMED"
    assert demand.confirmed_at is not None  # 评审联动：确认时间
    assert demand.expect_delivery_at == PLAN_DATE  # 评审联动：方案交期 → 期望交付

    async with session_factory() as db:
        async with db.begin():
            await flow_service.start(db, handler, did)
    assert (await get_demand(session_factory, did)).status == "IN_PROGRESS"

    # 验收三件套：工时 + 交付物（方案已 APPROVED）
    async with session_factory() as db:
        async with db.begin():
            await effort_service.add(db, handler, demand_id=did, work_date=date(2026, 10, 12), hours=2.5, remark="开发")
            db.add(DemandAttachment(demand_id=did, file_name="交付说明.md", kind="DOC", file_ext="md",
                                    size=64, storage_key=uuid4().hex, uploaded_by=handler.id,
                                    biz_type="DEMAND", biz_id=did))
            await flow_service.submit_acceptance(db, handler, did)
    assert (await get_demand(session_factory, did)).status == "ACCEPTANCE"

    async with session_factory() as db:
        async with db.begin():
            await flow_service.acceptance_review(db, user, did, result="PASS",
                                                 quality_score=5, satisfaction_score=4, opinion="符合预期")
    demand = await get_demand(session_factory, did)
    assert demand.status == "DONE" and demand.done_at is not None
    assert demand.quality_score == 5 and demand.satisfaction_score == 4

    # 全程每一次状态变更都有 transition_log（硬约束），事件序列完整
    events = [log.event for log in await transition_logs(session_factory, did)]
    assert events == ["SUBMIT", "ACCEPT", "ASSIGN", "SUBMIT_REVIEW", "REVIEW_PASS",
                      "START", "SUBMIT_ACCEPTANCE", "ACCEPT_PASS"]
    # 评审/验收留痕
    async with session_factory() as db:
        reviews = list((await db.execute(select(Review).where(Review.demand_id == did).order_by(Review.id))).scalars())
    assert [(r.review_type, r.result) for r in reviews] == [("SOLUTION", "PASS"), ("ACCEPTANCE", "PASS")]
    assert reviews[0].target_id == solution_id and reviews[1].quality_score == 5
    # 分派留痕
    async with session_factory() as db:
        assigns = list((await db.execute(select(Assignment).where(Assignment.demand_id == did))).scalars())
    assert [(a.action, a.to_user_id) for a in assigns] == [("ASSIGN", handler.id)]


# ---- 2. 非法流转与角色 ----

@pytest.mark.asyncio
async def test_illegal_transition_rejected(session_factory, user, admin):
    did = await make_submitted(session_factory, user)
    async with session_factory() as db:
        async with db.begin():
            # SUBMITTED 不允许 START（无规则）
            with pytest.raises(BizError) as error:
                await engine.transition(db, did, "START", admin)
            assert error.value.code == ErrorCode.ILLEGAL_STATE_TRANSITION.code
            assert "待受理" in error.value.message and "开始处理" in error.value.message
            # DRAFT 不允许 ACCEPT
            draft = await demand_service.create_draft(db, user, {
                "clientRequestId": f"p2-{uuid4().hex}", "title": "x", "demandTypeCode": "TECH"})
            with pytest.raises(BizError) as error2:
                await engine.transition(db, draft.id, "ACCEPT", admin)
            assert error2.value.code == 1001
            # 未登录操作者
            with pytest.raises(BizError) as error3:
                await engine.transition(db, did, "ACCEPT", None)
            assert error3.value.code == 401
    # 终态 DONE 拒绝一切事件
    raw = await insert_demand(session_factory, user, status="DONE", assignee_id=admin.id)
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error4:
                await engine.transition(db, raw, "START", admin)
            assert error4.value.code == 1001


@pytest.mark.asyncio
async def test_role_guard_and_admin_bypass(session_factory, user, admin, handler):
    did = await make_submitted(session_factory, user)
    # 受理限 ADMIN：HANDLER 403
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.accept(db, handler, did, None)
            assert error.value.code == 403 and "受理" in error.value.message
    # ADMIN 直通：CLAIM 规则只要 HANDLER，ADMIN 也可执行
    async with session_factory() as db:
        async with db.begin():
            await triage_service.accept(db, admin, did, None)
    async with session_factory() as db:
        async with db.begin():
            await triage_service.claim(db, admin, did)
    demand = await get_demand(session_factory, did)
    assert demand.status == "ANALYZING" and demand.assignee_id == admin.id


# ---- 3. ON_HOLD 叠加态 ----

@pytest.mark.asyncio
async def test_hold_resume_overlay(session_factory, user, admin, handler):
    did = await make_submitted(session_factory, user)
    await to_analyzing(session_factory, admin, handler, did)

    # 挂起：主状态列不动，快照 + 原因
    async with session_factory() as db:
        async with db.begin():
            await flow_service.hold(db, handler, did, "等业务方确认口径")
    demand = await get_demand(session_factory, did)
    assert demand.status == "ANALYZING"
    assert demand.hold_snapshot_status == "ANALYZING" and demand.hold_reason == "等业务方确认口径"
    log = (await transition_logs(session_factory, did))[-1]
    assert (log.from_status, log.to_status, log.event, log.hold_flag) == ("ANALYZING", "ON_HOLD", "HOLD", True)

    # 挂起中：除 RESUME 外一切事件按非法流转拒绝
    async with session_factory() as db:
        async with db.begin():
            for action in (
                lambda: flow_service.hold(db, handler, did, "重复挂起"),
                lambda: flow_service.return_pool(db, handler, did, "退单"),
                lambda: flow_service.split(db, handler, did, [{"title": "子需求"}]),
            ):
                with pytest.raises(BizError) as error:
                    await action()
                assert error.value.code == 1001
    # 挂起中可用操作仅剩 RESUME（前端按钮显隐依据）
    assert flow_service.available_actions(demand, handler) == ["RESUME"]

    # 管理员代为恢复：撕掉标签回到快照主态
    async with session_factory() as db:
        async with db.begin():
            await flow_service.resume(db, admin, did)
    demand = await get_demand(session_factory, did)
    assert demand.status == "ANALYZING"
    assert demand.hold_snapshot_status is None and demand.hold_reason is None
    log = (await transition_logs(session_factory, did))[-1]
    assert (log.from_status, log.to_status, log.event, log.hold_flag) == ("ON_HOLD", "ANALYZING", "RESUME", True)

    # 挂起原因必填；非处理人非管理员不可挂起
    other = await make_user(session_factory, "路人", "p2-stranger")
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await flow_service.hold(db, handler, did, "  ")
            assert error.value.code == 400
            with pytest.raises(BizError) as error2:
                await flow_service.hold(db, other, did, "越权")
            assert error2.value.code == 403


# ---- 4. 领取与并发 ----

@pytest.mark.asyncio
async def test_concurrent_claim_only_one_wins(session_factory, user, admin, handler, handler_b):
    did = await make_submitted(session_factory, user)
    async with session_factory() as db:
        async with db.begin():
            await triage_service.accept(db, admin, did, None)

    async def claim_by(operator):
        async with session_factory() as db:
            async with db.begin():
                await triage_service.claim(db, operator, did)

    results = await asyncio.gather(claim_by(handler), claim_by(handler_b), return_exceptions=True)
    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, BizError)]
    assert len(winners) == 1 and len(losers) == 1
    assert losers[0].code == ErrorCode.DEMAND_ALREADY_CLAIMED.code  # 1208
    demand = await get_demand(session_factory, did)
    assert demand.status == "ANALYZING" and demand.assignee_id in (handler.id, handler_b.id)
    # 领取留痕仅一条
    async with session_factory() as db:
        rows = list((await db.execute(select(Assignment).where(
            Assignment.demand_id == did, Assignment.action == "CLAIM"))).scalars())
    assert len(rows) == 1 and rows[0].to_user_id == demand.assignee_id


@pytest.mark.asyncio
async def test_claim_guards(session_factory, user, admin, handler):
    # 非 TRIAGE 不可领取
    did = await make_submitted(session_factory, user)
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.claim(db, handler, did)
            assert error.value.code == 1001 and "待分派" in error.value.message
    # 已有处理人的 TRIAGE（夹具）→ 1208
    raw = await insert_demand(session_factory, user, status="TRIAGE", assignee_id=admin.id)
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error2:
                await triage_service.claim(db, handler, raw)
            assert error2.value.code == 1208


# ---- 5. 方案与评审联动 ----

@pytest.mark.asyncio
async def test_solution_review_reject_and_reguards(session_factory, user, admin, handler):
    did = await make_submitted(session_factory, user)
    await to_analyzing(session_factory, admin, handler, did)

    # 同需求仅允许一个在评方案
    async with session_factory() as db:
        async with db.begin():
            s1 = await solution_service.create(db, handler, demand_id=did, spec_content="v1 规格",
                                               solution_content="v1 方案", plan_delivery_at=None, remark=None)
            s2 = await solution_service.create(db, handler, demand_id=did, spec_content="v2 规格",
                                               solution_content="v2 方案", plan_delivery_at=None, remark=None)
            assert (s1.version, s2.version) == (1, 2)
            await solution_service.submit_review(db, handler, s1.id)
            with pytest.raises(BizError) as error:
                await solution_service.submit_review(db, handler, s2.id)
            assert "已有方案在评审中" in error.value.message
            s1_id = s1.id
    assert (await get_demand(session_factory, did)).status == "SOLUTION_REVIEW"

    # 打回意见必填；HANDLER 不可评审（403）
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await solution_service.review(db, admin, s1_id, result="REJECT", opinion=" ")
            assert error.value.code == 400
            with pytest.raises(BizError) as error2:
                await solution_service.review(db, handler, s1_id, result="PASS", opinion=None)
            assert error2.value.code == 403
    # REJECT → 需求回 ANALYZING + 方案 REJECTED + 留痕
    async with session_factory() as db:
        async with db.begin():
            await solution_service.review(db, admin, s1_id, result="REJECT", opinion="方案缺少回滚预案")
    assert (await get_demand(session_factory, did)).status == "ANALYZING"
    async with session_factory() as db:
        assert (await db.get(Solution, s1_id)).status == "REJECTED"
        review = (await db.execute(select(Review).where(Review.demand_id == did, Review.review_type == "SOLUTION"))).scalar_one()
        assert review.result == "REJECT" and review.opinion == "方案缺少回滚预案"
    # 已打回方案可重新提交评审
    async with session_factory() as db:
        async with db.begin():
            await solution_service.submit_review(db, handler, s1_id)
    assert (await get_demand(session_factory, did)).status == "SOLUTION_REVIEW"


@pytest.mark.asyncio
async def test_solution_create_update_compare_guards(session_factory, user, admin, handler):
    did = await make_submitted(session_factory, user)
    # 非 ANALYZING 不可撰写
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await solution_service.create(db, handler, demand_id=did, spec_content=None,
                                              solution_content=None, plan_delivery_at=None, remark=None)
            assert error.value.code == 1001
    await to_analyzing(session_factory, admin, handler, did)
    async with session_factory() as db:
        async with db.begin():
            s1 = await solution_service.create(db, handler, demand_id=did, spec_content="v1",
                                               solution_content="方案一", plan_delivery_at=PLAN_DATE, remark=None)
            # 仅作者可改、仅草稿可改
            with pytest.raises(BizError) as error2:
                await solution_service.update(db, admin, s1.id, spec_content="篡改", solution_content=None,
                                              plan_delivery_at=None, remark=None)
            assert error2.value.code == 403
            await solution_service.update(db, handler, s1.id, spec_content="v1 修订",
                                          solution_content="方案一改", plan_delivery_at=None, remark="备注")
            # 再落 v2 草稿（提交评审后需求离开 ANALYZING，不可再撰）
            await solution_service.create(db, handler, demand_id=did, spec_content="v2",
                                          solution_content="方案二", plan_delivery_at=None, remark=None)
            await solution_service.submit_review(db, handler, s1.id)
            with pytest.raises(BizError) as error3:
                await solution_service.update(db, handler, s1.id, spec_content="在评篡改",
                                              solution_content=None, plan_delivery_at=None, remark=None)
            assert "仅草稿" in error3.value.message
            s1_id = s1.id
    # 在评方案评审到 CONFIRMED 后 review 被拒（方案已不在评）
    async with session_factory() as db:
        async with db.begin():
            await solution_service.review(db, admin, s1_id, result="PASS", opinion=None)
            with pytest.raises(BizError) as error4:
                await solution_service.review(db, admin, s1_id, result="PASS", opinion=None)
            assert "不在评审中" in error4.value.message
    # 版本对比：v1/v2 对比返回两条；版本不足报 1202
    async with session_factory() as db:
        async with db.begin():
            compare = await solution_service.compare(db, admin, did, 1, 2)
    assert [item["version"] for item in compare["items"]] == [1, 2]
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error5:
                await solution_service.compare(db, admin, did, 8, 9)
            assert error5.value.code == ErrorCode.SOLUTION_NOT_FOUND.code


# ---- 6. 验收 ----

@pytest.mark.asyncio
async def test_acceptance_preconditions(session_factory, user, handler):
    """三前置缺项拼「、」一次报全；逐项补齐后放行。"""
    did = await insert_demand(session_factory, user, status="IN_PROGRESS", assignee_id=handler.id)

    async def submit_acceptance():
        async with session_factory() as db:
            async with db.begin():
                await flow_service.submit_acceptance(db, handler, did)

    with pytest.raises(BizError) as error:
        await submit_acceptance()
    assert error.value.code == ErrorCode.ACCEPTANCE_PRECONDITION.code
    assert error.value.message == "方案未确认、工时未填报、交付物未上传"

    async with session_factory() as db:  # 补交付物
        async with db.begin():
            db.add(DemandAttachment(demand_id=did, file_name="交付.md", kind="DOC", file_ext="md",
                                    size=8, storage_key=uuid4().hex, uploaded_by=handler.id,
                                    biz_type="DEMAND", biz_id=did))
    with pytest.raises(BizError) as error2:
        await submit_acceptance()
    assert error2.value.message == "方案未确认、工时未填报"

    async with session_factory() as db:  # 补工时
        async with db.begin():
            await effort_service.add(db, handler, demand_id=did, work_date=date(2026, 10, 12), hours=1, remark=None)
    with pytest.raises(BizError) as error3:
        await submit_acceptance()
    assert error3.value.message == "方案未确认"

    async with session_factory() as db:  # 补已确认方案
        async with db.begin():
            db.add(Solution(demand_id=did, version=1, author_id=handler.id, status="APPROVED"))
    await submit_acceptance()
    assert (await get_demand(session_factory, did)).status == "ACCEPTANCE"


@pytest.mark.asyncio
async def test_acceptance_review_rules(session_factory, user, admin, handler):
    did = await insert_demand(session_factory, user, status="ACCEPTANCE", assignee_id=handler.id)
    # 非提报人不可验收（管理员也不行）
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await flow_service.acceptance_review(db, admin, did, result="PASS",
                                                     quality_score=5, satisfaction_score=5, opinion=None)
            assert error.value.code == 403 and "提报人" in error.value.message
            # PASS 双评分必填且 1-5
            with pytest.raises(BizError) as error2:
                await flow_service.acceptance_review(db, user, did, result="PASS",
                                                     quality_score=None, satisfaction_score=6, opinion=None)
            assert error2.value.code == 400 and "质量评分" in error2.value.message
            # REJECT 意见必填
            with pytest.raises(BizError) as error3:
                await flow_service.acceptance_review(db, user, did, result="REJECT",
                                                     quality_score=None, satisfaction_score=None, opinion=" ")
            assert error3.value.code == 400 and "意见" in error3.value.message
    # REJECT → 回 IN_PROGRESS 继续处理 + 留痕
    async with session_factory() as db:
        async with db.begin():
            await flow_service.acceptance_review(db, user, did, result="REJECT",
                                                 quality_score=None, satisfaction_score=None, opinion="报表数据对不上")
    assert (await get_demand(session_factory, did)).status == "IN_PROGRESS"
    async with session_factory() as db:
        review = (await db.execute(select(Review).where(
            Review.demand_id == did, Review.review_type == "ACCEPTANCE"))).scalar_one()
        assert review.result == "REJECT" and review.quality_score is None
    # PASS → DONE + 评分 + done_at（REJECT 已回 IN_PROGRESS，另取一条 ACCEPTANCE 需求验收通过）
    did2 = await insert_demand(session_factory, user, status="ACCEPTANCE", assignee_id=handler.id)
    async with session_factory() as db:
        async with db.begin():
            await flow_service.acceptance_review(db, user, did2, result="PASS",
                                                 quality_score=4, satisfaction_score=5, opinion=None)
    demand = await get_demand(session_factory, did2)
    assert demand.status == "DONE" and demand.done_at is not None
    assert (demand.quality_score, demand.satisfaction_score) == (4, 5)


# ---- 7. 退单 ----

@pytest.mark.asyncio
async def test_return_pool(session_factory, user, admin, handler, handler_b):
    did = await make_submitted(session_factory, user)
    await to_analyzing(session_factory, admin, handler, did)

    # 非处理人不可退单
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await flow_service.return_pool(db, handler_b, did, "做不了")
            assert error.value.code == 403
    # 处理人退单：回 TRIAGE + 清处理人 + Assignment/transition 双留痕
    async with session_factory() as db:
        async with db.begin():
            await flow_service.return_pool(db, handler, did, "技能不匹配，退回池子")
    demand = await get_demand(session_factory, did)
    assert demand.status == "TRIAGE" and demand.assignee_id is None
    async with session_factory() as db:
        assignment = (await db.execute(select(Assignment).where(
            Assignment.demand_id == did, Assignment.action == "RETURN"))).scalar_one()
        assert assignment.from_user_id == handler.id and assignment.to_user_id is None
    log = (await transition_logs(session_factory, did))[-1]
    assert (log.event, log.from_status, log.to_status, log.comment) == (
        "RETURN_POOL", "ANALYZING", "TRIAGE", "技能不匹配，退回池子")
    # 退回后可被他人领取
    async with session_factory() as db:
        async with db.begin():
            await triage_service.claim(db, handler_b, did)
    assert (await get_demand(session_factory, did)).assignee_id == handler_b.id
    # 管理员收回：ANALYZING → TRIAGE
    async with session_factory() as db:
        async with db.begin():
            await flow_service.return_pool(db, admin, did, "管理员收回改派")
    assert (await get_demand(session_factory, did)).status == "TRIAGE"


# ---- 8. 评论与工时 ----

@pytest.mark.asyncio
async def test_comment_author_only(session_factory, user, admin, handler):
    did = await make_submitted(session_factory, user)
    async with session_factory() as db:
        async with db.begin():
            comment = await comment_service.add(db, handler, demand_id=did, content="请补充数据来源",
                                                mentioned_user_ids=[user.id, admin.id])
            comment_id = comment.id
            assert comment.mentioned_user_ids == f"{user.id},{admin.id}"
            with pytest.raises(BizError) as error:
                await comment_service.add(db, handler, demand_id=did, content="  ", mentioned_user_ids=None)
            assert error.value.code == 400
            # 仅作者可改
            with pytest.raises(BizError) as error2:
                await comment_service.update(db, user, comment_id, content="篡改")
            assert error2.value.code == 403
            updated = await comment_service.update(db, handler, comment_id, content="请补充数据来源与口径")
            assert updated.content == "请补充数据来源与口径"
    comments = None
    async with session_factory() as db:
        comments = await comment_service.list_comments(db, admin, did)
    assert [c["content"] for c in comments] == ["请补充数据来源与口径"]
    assert comments[0]["authorName"] == "处理人甲" and comments[0]["updatedAt"] is not None
    # 无删除入口：模型层也没有 delete 服务函数（不可物理删除，拍板口径）
    assert not hasattr(comment_service, "delete")


@pytest.mark.asyncio
async def test_effort_log_rules(session_factory, user, admin, handler, handler_b):
    did = await insert_demand(session_factory, user, status="IN_PROGRESS", assignee_id=handler.id)
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError):
                await effort_service.add(db, handler, demand_id=did, work_date=date(2026, 10, 12), hours=0, remark=None)
            with pytest.raises(BizError):
                await effort_service.add(db, handler, demand_id=did, work_date=date(2026, 10, 12), hours=25, remark=None)
            e1 = await effort_service.add(db, handler, demand_id=did, work_date=date(2026, 10, 11), hours=2, remark="分析")
            await effort_service.add(db, handler_b, demand_id=did, work_date=date(2026, 10, 12), hours=3.5, remark=None)
            with pytest.raises(BizError) as error:
                await effort_service.update(db, handler_b, e1.id, work_date=date(2026, 10, 11), hours=9, remark=None)
            assert error.value.code == 403
    async with session_factory() as db:
        summary = await effort_service.summary(db, admin, did)
    assert summary["totalHours"] == 5.5
    by_user = {row["userName"]: row["hours"] for row in summary["byUser"]}
    assert by_user == {"处理人甲": 2.0, "处理人乙": 3.5}
    # 终态不可登记
    done = await insert_demand(session_factory, user, status="DONE", assignee_id=handler.id)
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error2:
                await effort_service.add(db, handler, demand_id=done, work_date=date(2026, 10, 12), hours=1, remark=None)
            assert error2.value.code == 1001


# ---- 9. 拆分 ----

@pytest.mark.asyncio
async def test_split_instantiation(session_factory, user, admin, handler):
    did = await make_submitted(session_factory, user)
    await to_analyzing(session_factory, admin, handler, did)
    pending = [{"title": "持仓汇总接口", "summary": "按机构汇总持仓"},
               {"title": "报表展示页面", "summary": "晨会报表前端"}]
    async with session_factory() as db:  # 夹具：AI 打标的待实例化拆分
        async with db.begin():
            demand = await db.get(Demand, did)
            demand.ext = {**(demand.ext or {}), "pendingSplits": pending}

    async with session_factory() as db:
        async with db.begin():
            children = await flow_service.split(db, handler, did, None)
    assert len(children) == 2
    parent = await get_demand(session_factory, did)
    assert parent.split_group_id is not None
    assert "pendingSplits" not in (parent.ext or {})  # 已消费的打标被清除
    group_ids, demand_nos = set(), set()
    for index, child in enumerate(children):
        assert child.status == "TRIAGE"  # 直接入处理池
        assert child.split_from_id == did and child.title == pending[index]["title"]
        assert child.submitter_id == handler.id and child.demand_type_code == "TECH"
        assert child.demand_no and child.demand_no != parent.demand_no
        group_ids.add(child.split_group_id)
        demand_nos.add(child.demand_no)
    assert group_ids == {parent.split_group_id} and len(demand_nos) == 2  # 同组不同号
    # 关系与日志留痕
    async with session_factory() as db:
        relations = list((await db.execute(select(DemandRelation).where(
            DemandRelation.from_id == did, DemandRelation.type == "SPLIT"))).scalars())
        assert {r.to_id for r in relations} == {c.id for c in children}
        child_logs = list((await db.execute(select(DemandTransitionLog).where(
            DemandTransitionLog.demand_id == children[0].id))).scalars())
        assert len(child_logs) == 1
        assert (child_logs[0].event, child_logs[0].from_status, child_logs[0].to_status) == ("SPLIT", None, "TRIAGE")
        change = (await db.execute(select(DemandChangeLog).where(
            DemandChangeLog.demand_id == did, DemandChangeLog.field_key == "ext.pendingSplits"))).scalar_one()
        assert change.new_value is None and change.source == "user"


@pytest.mark.asyncio
async def test_split_guards(session_factory, user, admin, handler, handler_b):
    # 草稿态不可拆
    async with session_factory() as db:
        async with db.begin():
            draft = await demand_service.create_draft(db, user, {
                "clientRequestId": f"p2-{uuid4().hex}", "title": "x", "demandTypeCode": "TECH"})
            with pytest.raises(BizError) as error:
                await flow_service.split(db, user, draft.id, [{"title": "子"}])
            assert error.value.code == 1001
    did = await insert_demand(session_factory, user, status="ANALYZING", assignee_id=handler.id)
    async with session_factory() as db:
        async with db.begin():
            # 无待实例化拆分项
            with pytest.raises(BizError) as error2:
                await flow_service.split(db, handler, did, None)
            assert error2.value.code == 400
            # 非处理人非管理员
            with pytest.raises(BizError) as error3:
                await flow_service.split(db, handler_b, did, [{"title": "子"}])
            assert error3.value.code == 403
            # 标题必填
            with pytest.raises(BizError) as error4:
                await flow_service.split(db, handler, did, [{"title": " "}])
            assert error4.value.code == 400
    # 挂起中不可拆
    held = await insert_demand(session_factory, user, status="ANALYZING", assignee_id=handler.id,
                               hold_snapshot_status="ANALYZING", hold_reason="暂停")
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error5:
                await flow_service.split(db, handler, held, [{"title": "子"}])
            assert error5.value.code == 1001


# ---- 10. 受理台：队列/池/计数/分派/关闭/改型 ----

@pytest.mark.asyncio
async def test_triage_lists_counts_assign_close_change_type(session_factory, user, admin, handler):
    did1 = await make_submitted(session_factory, user)
    did2 = await make_submitted(session_factory, user)
    async with session_factory() as db:
        counts = await triage_service.counts(db)
        assert counts == {"queue": 2, "pool": 0}
        rows, total = await triage_service.list_queue(db, urgency=None, type_code=None, page=1, size=10)
        assert total == 2 and [r.id for r in rows] == [did1, did2]  # FIFO
    # 受理一条后改型（主状态不变）
    async with session_factory() as db:
        async with db.begin():
            await triage_service.accept(db, admin, did1, None)
            with pytest.raises(BizError) as error:
                await triage_service.change_type(db, handler, did2, "MATL", None)
            assert error.value.code == 403
            await triage_service.change_type(db, admin, did2, "MATL", "类型修正")
    demand2 = await get_demand(session_factory, did2)
    assert demand2.status == "SUBMITTED" and demand2.demand_type_code == "MATL" and demand2.subtype_code is None
    log = (await transition_logs(session_factory, did2))[-1]
    assert log.event == "CHANGE_TYPE" and log.extra == {"fromType": "TECH", "toType": "MATL"}
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error2:  # 同类型
                await triage_service.change_type(db, admin, did2, "MATL", None)
            assert "相同" in error2.value.message
            with pytest.raises(BizError) as error3:  # 非法类型
                await triage_service.change_type(db, admin, did2, "NOPE", None)
            assert error3.value.code == 1207
    # 池内 urgency 排序：CRITICAL 优先
    async with session_factory() as db:
        async with db.begin():
            demand1 = await db.get(Demand, did1)
            demand1.urgency = "NORMAL"
            await triage_service.accept(db, admin, did2, None)
            demand2 = await db.get(Demand, did2)
            demand2.urgency = "CRITICAL"
    async with session_factory() as db:
        counts = await triage_service.counts(db)
        assert counts == {"queue": 0, "pool": 2}
        pool, _ = await triage_service.list_pool(db, urgency=None, page=1, size=10)
        assert [r.id for r in pool] == [did2, did1]
    # 分派校验：停用用户 / 非处理人角色
    stranger = await make_user(session_factory, "观察员", "p2-viewer", role="USER")
    inactive = await make_user(session_factory, "停用", "p2-inactive")
    async with session_factory() as db:
        async with db.begin():
            (await db.get(User, inactive.id)).status = "DISABLED"
            with pytest.raises(BizError) as error4:
                await triage_service.assign(db, admin, did1, inactive.id, None)
            assert error4.value.code == 1119
            with pytest.raises(BizError) as error5:
                await triage_service.assign(db, admin, did1, stranger.id, None)
            assert "不是处理人" in error5.value.message
            await triage_service.assign(db, admin, did1, handler.id, "分派给甲")
    # 我的处理单
    async with session_factory() as db:
        mine, total = await triage_service.list_mine(db, handler, status=None, page=1, size=10)
        assert total == 1 and mine[0].id == did1
    # 重复关闭：写 DemandRelation DUPLICATE
    async with session_factory() as db:
        async with db.begin():
            await triage_service.close(db, admin, did2, "与已有需求重复", did1)
    demand2 = await get_demand(session_factory, did2)
    assert demand2.status == "CLOSED" and demand2.close_reason == "与已有需求重复" and demand2.closed_at is not None
    async with session_factory() as db:
        async with db.begin():
            relation = (await db.execute(select(DemandRelation).where(
                DemandRelation.from_id == did2, DemandRelation.type == "DUPLICATE"))).scalar_one()
            assert relation.to_id == did1
            with pytest.raises(BizError):  # 关闭原因必填
                await triage_service.close(db, admin, did1, " ", None)


# ---- 11. 热重载与配置校验 ----

def test_parse_rules_validation():
    with pytest.raises(ValueError, match="非空数组"):
        engine.parse_rules(json.dumps({"rules": []}))
    with pytest.raises(ValueError, match="源状态"):
        engine.parse_rules(json.dumps({"rules": [{"from": "X", "event": "A", "to": None, "roles": []}]}))
    with pytest.raises(ValueError, match="目标状态"):
        engine.parse_rules(json.dumps({"rules": [{"from": "TRIAGE", "event": "A", "to": "X", "roles": []}]}))
    with pytest.raises(ValueError, match="角色仅允许"):
        engine.parse_rules(json.dumps({"rules": [{"from": "TRIAGE", "event": "A", "to": None, "roles": ["SUPERUSER"]}]}))
    # P4 角色扩展：四值角色均合法
    parsed = engine.parse_rules(json.dumps({"rules": [
        {"from": "TRIAGE", "event": "A", "to": None, "roles": ["ADMIN", "EXECUTIVE", "MANAGER", "HANDLER"]}]}))
    assert parsed[0].roles == frozenset({"ADMIN", "EXECUTIVE", "MANAGER", "HANDLER"})


@pytest.mark.asyncio
async def test_engine_hot_reload(session_factory, user, admin):
    did = await make_submitted(session_factory, user)
    trimmed = {"rules": [
        {"from": "SUBMITTED", "event": "RETURN", "to": "NEED_INFO", "roles": ["ADMIN"], "remark": "退回"}]}
    try:
        async with session_factory() as db:
            async with db.begin():
                db.add(StateMachineConfig(config_key="DEFAULT", config_name="裁剪版",
                                          config_json=json.dumps(trimmed), status="ACTIVE"))
                db.add(StateMachineConfig(config_key="BROKEN", config_name="坏配置",
                                          config_json="{not json", status="ACTIVE"))
                loaded = await engine.load_from_db(db)
        by_key = {row["key"]: row for row in loaded}
        assert by_key["DEFAULT"]["ruleCount"] == 1
        assert by_key["BROKEN"]["ruleCount"] == 0  # 坏配置跳过，不污染缓存
        # 新规则生效：ACCEPT 已无规则 → 1001；RETURN 仍在
        async with session_factory() as db:
            async with db.begin():
                with pytest.raises(BizError) as error:
                    await triage_service.accept(db, admin, did, None)
                assert error.value.code == 1001
                await demand_service.return_demand(db, admin, did, "裁剪版规则下打回")
        assert (await get_demand(session_factory, did)).status == "NEED_INFO"
    finally:
        # 恢复兜底规则，避免污染同进程其他用例
        async with session_factory() as db:
            async with db.begin():
                await db.execute(StateMachineConfig.__table__.delete())
                await engine.load_from_db(db)
    assert engine.find_rule("SUBMITTED", "ACCEPT") is not None


# ---- 12. flow 序列化 ----

@pytest.mark.asyncio
async def test_flow_detail_serialization(session_factory, user, admin, handler):
    did = await make_submitted(session_factory, user)
    await to_analyzing(session_factory, admin, handler, did)
    async with session_factory() as db:
        detail = await flow_service.flow_detail(db, handler, did)
    last = detail["transitions"][-1]
    assert last["event"] == "ASSIGN" and last["eventLabel"] == "分派"
    assert last["fromStatusLabel"] == "待分派/待领取" and last["toStatusLabel"] == "分析中"
    assert last["operatorName"] == "管理员" and last["holdFlag"] is False
    # 处理人视角可用操作（分析中）：提交评审/退回池/挂起
    events = {item["event"] for item in detail["availableActions"]}
    assert {"SUBMIT_REVIEW", "RETURN_POOL", "HOLD"} <= events
    assert "START" not in events  # 未到 CONFIRMED
    async with session_factory() as db:
        admin_detail = await flow_service.flow_detail(db, admin, did)
    admin_events = {item["event"] for item in admin_detail["availableActions"]}
    assert "CHANGE_TYPE" in admin_events  # 管理员额外有改型


# ---- 13. API 层门禁 ----

BASE = "/demandhub-api"


async def login(client, name, wecom_userid):
    response = await client.post(BASE + "/auth/dev-login", json={"name": name, "wecomUserid": wecom_userid})
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_api_role_gates(client, session_factory, user, admin):
    did = await make_submitted(session_factory, user)
    user_headers = await login(client, "测试用户", "test-user")
    admin_headers = await login(client, "管理员", "mvp-admin")
    # 受理队列限 ADMIN
    assert (await client.get(BASE + "/triage/queue", headers=user_headers)).json()["code"] == 403
    assert (await client.get(BASE + "/triage/queue", headers=admin_headers)).json()["code"] == 0
    # 受理动作限 ADMIN
    assert (await client.post(f"{BASE}/triage/{did}/accept", headers=user_headers, json={})).json()["code"] == 403
    accepted = await client.post(f"{BASE}/triage/{did}/accept", headers=admin_headers, json={})
    assert accepted.json()["code"] == 0 and accepted.json()["data"]["status"] == "TRIAGE"
    # 领取 HANDLER 以上可执行（提报人角色同为 HANDLER，拍板口径）
    claimed = await client.post(f"{BASE}/triage/{did}/claim", headers=user_headers)
    assert claimed.json()["code"] == 0 and claimed.json()["data"]["status"] == "ANALYZING"
    assert claimed.json()["data"]["assigneeName"] == "测试用户"
    # 热重载限 ADMIN
    assert (await client.post(BASE + "/admin/state-machines/reload", headers=user_headers)).json()["code"] == 403
    assert (await client.post(BASE + "/admin/state-machines/reload", headers=admin_headers)).json()["code"] == 0
    # 时间线接口：提报人可见，含 availableActions
    flow = (await client.get(f"{BASE}/demand/{did}/flow", headers=user_headers)).json()
    assert flow["code"] == 0
    assert [t["event"] for t in flow["data"]["transitions"]][-2:] == ["ACCEPT", "CLAIM"]
    events = {a["event"] for a in flow["data"]["availableActions"]}
    assert {"SUBMIT_REVIEW", "HOLD", "RETURN_POOL"} <= events  # 提报人即处理人
