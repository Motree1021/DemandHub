"""处理辅助 Agent（照蓝本 AgentAssistService）：调研问题清单 + 方案初稿。

产出先写 agent_draft 草稿区（PENDING，标注"AI 生成需人工确认"）；
人工确认（可编辑后提交）才写 solution 表：版本号 max+1、状态 DRAFT，
与 solution_service.create 约定一致，之后走既有评审流程。
模板文本照蓝本 agent_prompt_template（09-ark-llm-prompt.sql 的 JSON 输出契约版）。
"""
import json
import logging
from string import Template

from sqlalchemy import func, select

from app.agent.llm_client import LlmUnavailable, get_llm_client
from app.core.errors import BizError, ErrorCode
from app.db.models import AgentDraft, AgentSession, Demand, Solution, User, now
from app.services import rag_service, session_service

logger = logging.getLogger(__name__)

SCENE = "HANDLE_ASSIST"
TYPE_QUESTIONS = "QUESTIONS"
TYPE_SOLUTION = "SOLUTION"

# 蓝本 HANDLE_ASSIST_QUESTIONS（09-ark-llm-prompt.sql JSON 契约版）
QUESTIONS_TEMPLATE = Template(
    '基于需求「${title}」（${demand_type}）描述：${content}，以及相似历史需求：${similar_docs}，'
    '生成处理前的调研问题清单（5~8 条，覆盖：核心使用角色与频次、数据来源与口径确认人、与上下游系统的边界、'
    '性能与数据权限约束、里程碑拆分与关键依赖；有相似历史需求时，指出其方案与验收经验中可复用的点与差异点）。'
    '只输出一个 JSON 对象，不要输出任何其他文字：{"questions":["问题1","问题2"]}')

# 蓝本 HANDLE_ASSIST_SOLUTION（09-ark-llm-prompt.sql JSON 契约版）
SOLUTION_TEMPLATE = Template(
    '基于需求「${title}」（${demand_type}）描述：${content}，参考相似历史方案：${similar_docs}，生成方案初稿。'
    'specContent 为需求理解（业务背景摘要 + 建议进一步确认的点），'
    'solutionContent 为方案内容（目标 / 范围含边界外事项 / 实施要点 / 验收口径），'
    '两段开头均标注"（AI 生成，需人工确认）"。'
    '只输出一个 JSON 对象，不要输出任何其他文字：{"specContent":"...","solutionContent":"..."}')


def _render_docs(docs) -> str:
    """相似历史需求注入 prompt：编号+标题+原文截断；无历史给「无」。"""
    if not docs:
        return "无"
    return "\n---\n".join(f"「{doc.title}」（{doc.demand_no}）\n{doc.content[:500]}" for doc in docs)


def _parse_questions(raw: str) -> list[str]:
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(value, dict):
        return []
    return [q.strip() for q in value.get("questions") or [] if isinstance(q, str) and q.strip()]


def _parse_solution(raw: str) -> dict | None:
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    spec, sol = value.get("specContent"), value.get("solutionContent")
    if not isinstance(spec, str) or not isinstance(sol, str) or (not spec.strip() and not sol.strip()):
        return None
    return {"specContent": spec, "solutionContent": sol}


async def _require_assist_session(db, user: User, session_id: int) -> AgentSession:
    session = await session_service.require_owned(db, user, session_id)
    if session.scene != SCENE:
        raise BizError(ErrorCode.PARAM_INVALID, "会话场景不是处理辅助")
    if session.demand_id is None:
        raise BizError(ErrorCode.PARAM_INVALID, "处理辅助会话未关联需求")
    return session


async def _require_demand(db, demand_id: int) -> Demand:
    demand = await db.get(Demand, demand_id)
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    return demand


async def _complete(db, user: User, session: AgentSession, demand: Demand,
                    template: Template, llm) -> str:
    docs = await rag_service.similar_docs(db, demand.id, 3, llm=llm)
    prompt = template.substitute(title=demand.title, demand_type=demand.demand_type_code or "",
                                 content=demand.content or "", similar_docs=_render_docs(docs))
    client = llm or get_llm_client()
    try:
        final = await client.complete_json([{"role": "system", "content": prompt}])
    except LlmUnavailable:
        raise BizError(ErrorCode.AI_SERVICE_UNAVAILABLE, "AI 服务暂不可用，请稍后重试") from None
    client.on_success()
    return final.raw


async def generate_questions(db, user: User, session_id: int, llm=None) -> AgentDraft:
    """生成调研问题清单（写草稿区 PENDING，同时追加一条会话消息）。"""
    session = await _require_assist_session(db, user, session_id)
    demand = await _require_demand(db, session.demand_id)
    raw = await _complete(db, user, session, demand, QUESTIONS_TEMPLATE, llm)
    questions = _parse_questions(raw)
    if not questions:
        logger.warning("[ASSIST] 问题清单输出无法解析 demand_id=%s（前80字符：%s）", demand.id, str(raw)[:80])
        raise BizError(ErrorCode.AI_SERVICE_UNAVAILABLE, "AI 输出异常，请稍后重试")
    draft = AgentDraft(demand_id=demand.id, session_id=session.id, draft_type=TYPE_QUESTIONS,
                       content=json.dumps(questions, ensure_ascii=False), status="PENDING",
                       created_by=user.id)
    db.add(draft)
    await db.flush()
    await session_service.append(db, session.id, "ASSISTANT",
                                 "【AI 生成 · 调研问题清单】（需人工确认）\n" + "\n".join("· " + q for q in questions))
    return draft


async def generate_solution(db, user: User, session_id: int, llm=None) -> AgentDraft:
    """生成方案初稿（写草稿区 PENDING；确认后才入 solution 表）。"""
    session = await _require_assist_session(db, user, session_id)
    demand = await _require_demand(db, session.demand_id)
    raw = await _complete(db, user, session, demand, SOLUTION_TEMPLATE, llm)
    content = _parse_solution(raw)
    if content is None:
        logger.warning("[ASSIST] 方案初稿输出无法解析 demand_id=%s（前80字符：%s）", demand.id, str(raw)[:80])
        raise BizError(ErrorCode.AI_SERVICE_UNAVAILABLE, "AI 输出异常，请稍后重试")
    draft = AgentDraft(demand_id=demand.id, session_id=session.id, draft_type=TYPE_SOLUTION,
                       content=json.dumps(content, ensure_ascii=False), status="PENDING",
                       created_by=user.id)
    db.add(draft)
    await db.flush()
    await session_service.append(db, session.id, "ASSISTANT",
                                 content["specContent"] + "\n\n" + content["solutionContent"])
    return draft


async def drafts(db, demand_id: int) -> list[AgentDraft]:
    """需求的草稿列表（PENDING 优先，再按时间倒序）。"""
    await _require_demand(db, demand_id)
    result = list((await db.execute(
        select(AgentDraft).where(AgentDraft.demand_id == demand_id).order_by(AgentDraft.id.desc())
    )).scalars())
    result.sort(key=lambda d: (0 if d.status == "PENDING" else 1, -d.id))
    return result


def _require_pending_draft(draft: AgentDraft | None) -> AgentDraft:
    if draft is None:
        raise BizError(ErrorCode.AGENT_DRAFT_NOT_FOUND)
    if draft.status != "PENDING":
        raise BizError(ErrorCode.AGENT_DRAFT_CONFIRMED)
    return draft


async def confirm(db, user: User, draft_id: int, *, spec_content: str | None,
                  solution_content: str | None, plan_delivery_at) -> AgentDraft:
    """确认方案初稿入库：写 solution（版本 max+1、DRAFT）→ 草稿标记 CONFIRMED。

    允许确认前编辑内容（未编辑用草稿原文）；前置校验与 solution_service.create 一致
    （需求需处于 ANALYZING）。
    """
    draft = _require_pending_draft(await db.get(AgentDraft, draft_id))
    if draft.draft_type != TYPE_SOLUTION:
        raise BizError(ErrorCode.PARAM_INVALID, "仅方案初稿草稿支持确认入库")
    demand = await _require_demand(db, draft.demand_id)
    if demand.status != "ANALYZING":
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅分析中的需求可确认方案入库")
    spec, sol = spec_content, solution_content
    if (not spec or not spec.strip()) and (not sol or not sol.strip()):
        origin = _parse_solution(draft.content) or {"specContent": "", "solutionContent": draft.content}
        spec, sol = origin["specContent"], origin["solutionContent"]
    max_version = (await db.execute(
        select(func.max(Solution.version)).where(Solution.demand_id == draft.demand_id)
    )).scalar_one() or 0
    solution = Solution(demand_id=draft.demand_id, version=max_version + 1, author_id=user.id,
                        spec_content=spec, solution_content=sol,
                        plan_delivery_at=plan_delivery_at, status="DRAFT",
                        remark="AI 生成，人工确认入库")
    db.add(solution)
    await db.flush()
    draft.status = "CONFIRMED"
    draft.confirmed_by = user.id
    draft.confirmed_at = now()
    draft.target_solution_id = solution.id
    await db.flush()
    return draft


async def discard(db, user: User, draft_id: int) -> None:
    """废弃草稿（PENDING → DISCARDED）。"""
    draft = _require_pending_draft(await db.get(AgentDraft, draft_id))
    draft.status = "DISCARDED"
    draft.confirmed_by = user.id
    draft.confirmed_at = now()
    await db.flush()


def serialize_draft(draft: AgentDraft) -> dict:
    from app.core.result import encode

    try:
        content = json.loads(draft.content)
    except (ValueError, TypeError):
        content = draft.content
    return {"id": draft.id, "demandId": draft.demand_id, "sessionId": draft.session_id,
            "draftType": draft.draft_type, "content": content, "status": draft.status,
            "createdBy": draft.created_by, "confirmedBy": draft.confirmed_by,
            "confirmedAt": encode(draft.confirmed_at), "targetSolutionId": draft.target_solution_id,
            "createdAt": encode(draft.created_at), "updatedAt": encode(draft.updated_at)}
