"""读快照→无锁模型请求→短事务复验保存→发送成功，失败不补写。"""
import asyncio
import hashlib
import json
import logging
import time
import weakref
from copy import deepcopy
from dataclasses import dataclass

from sqlalchemy import select

from app.agent.llm_client import LlmUnavailable, get_llm_client
from app.agent.policy import process
from app.agent.schemas import ElementStatus, GuideChatRequest, GuideResult, parse_model_output
from app.core.errors import BizError, ErrorCode
from app.db.models import AgentMessage, Demand
from app.services import session_service
from app.standards.loader import TEMPLATE_PATH, ensure_snapshot, loader

logger = logging.getLogger(__name__)
_session_locks = weakref.WeakValueDictionary()


def session_lock(session_id):
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


def request_hash(req):
    return hashlib.sha256(json.dumps(req.model_dump(by_alias=True), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def demand_form(demand):
    from app.services.demand_service import form_of
    return form_of(demand)


@dataclass
class Prepared:
    form: dict
    sources: dict
    prev_elements: list
    prev_target: str | None
    previous_form: dict
    history: list
    replay: GuideResult | None = None


def build_prompt(form, sources, previous_elements, asked_target, history, message, *, registry=None):
    """真实对话与模型评测共用相同输入结构及模板。"""
    registry = registry or {code: loader.get(code) for code in ("TECH", "MATL", "TRAIN")}
    standards = {code: standard.model_dump(mode="json", by_alias=True) for code, standard in registry.items()}
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    section = {"activeType": form.get("demandTypeCode"), "standards": standards}
    rendered = template.replace("{{standard_section}}", json.dumps(section, ensure_ascii=False))
    current = {"message": message, "form": form, "fieldSources": sources, "previousElements": [e.model_dump(by_alias=True) for e in previous_elements], "askedTarget": asked_target}
    return [{"role": "system", "content": rendered}, *history, {"role": "user", "content": json.dumps(current, ensure_ascii=False)}], rendered, registry, template


class GuideService:
    def __init__(self, db, user, llm=None):
        self.db = db
        self.user = user
        self.user_id = user.id
        self.llm = llm or get_llm_client()

    async def _saved(self, req):
        saved = (await self.db.execute(select(AgentMessage).where(AgentMessage.session_id == req.session_id, AgentMessage.request_id == req.request_id, AgentMessage.role == "ASSISTANT"))).scalar_one_or_none()
        if saved is None:
            return None
        if saved.request_hash != request_hash(req):
            raise BizError(ErrorCode.CONFLICT, "同一requestId不能对应不同输入")
        return GuideResult.model_validate(saved.structured_payload)

    async def prepare(self, req: GuideChatRequest):
        try:
            agent_session = await session_service.require_owned(self.db, self.user, req.session_id)
            demand = (await self.db.execute(select(Demand).where(Demand.id == req.demand_id, Demand.submitter_id == self.user_id).execution_options(populate_existing=True))).scalar_one_or_none()
            if demand is None:
                raise BizError(ErrorCode.DEMAND_NOT_FOUND)
            if agent_session.demand_id != demand.id or demand.session_id != agent_session.id or agent_session.scene != "SUBMIT_GUIDE":
                raise BizError(ErrorCode.CONFLICT, "会话与草稿不匹配")
            replay = await self._saved(req)
            if replay:
                return Prepared({}, {}, [], None, {}, [], replay)
            if demand.status != "DRAFT" or agent_session.status != "ACTIVE":
                raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "草稿或会话已关闭")
            if demand.revision != req.revision:
                raise BizError(ErrorCode.CONFLICT)
            if not self.llm.available():
                logger.warning("AI不可用拦截（密钥未配置或冷却中，冷却至 %.0f）", self.llm.cooldown_until)
                raise BizError(ErrorCode.AI_SERVICE_UNAVAILABLE)
            history = await session_service.messages(self.db, self.user, req.session_id, limit=20)
            previous = next((m.structured_payload for m in reversed(history) if m.role == "ASSISTANT" and m.structured_payload), {})
            form = demand_form(demand)
            sources = deepcopy(demand.field_sources or {})
            # FR-02/D6 原文保真：content 为空时本轮消息原文即 A8 底稿（来源 user，模型不得改写）
            if not (form.get("content") or "").strip() and req.message.strip():
                form["content"] = req.message
                sources["content"] = "user"
            return Prepared(form, sources, [ElementStatus.model_validate(e) for e in previous.get("elements", [])], agent_session.asked_target, deepcopy(previous.get("structured", {})), [{"role": "user" if m.role == "USER" else "assistant", "content": m.content} for m in history if m.role in {"USER", "ASSISTANT"}])
        finally:
            # ORM读取默认autobegin，显式结束，模型等待不占数据库连接。
            if self.db.in_transaction():
                await self.db.rollback()

    def _messages(self, prepared, req):
        return build_prompt(prepared.form, prepared.sources, prepared.prev_elements, prepared.prev_target, prepared.history, req.message)

    async def execute(self, req):
        async with session_lock(req.session_id):
            prepared = await self.prepare(req)
            if prepared.replay:
                return prepared.replay
            started = time.monotonic()
            model_messages, rendered_prompt, registry, raw_template = self._messages(prepared, req)
            try:
                final = None
                async for event in self.llm.stream_json(model_messages):
                    if event.kind == "final":
                        final = event
                try:
                    if final is None:
                        raise ValueError("上游流未返回完整输出")
                    output = parse_model_output(final.raw)
                    result = process(output, prepared.form, prepared.sources, prepared.prev_elements, prepared.prev_target, prepared.previous_form, req.message, standards=registry)
                except (ValueError, TypeError, KeyError):
                    # 完整格式错误最多修复一次，不重复发送任何模型措辞。
                    repaired = await self.llm.complete_json([*model_messages, {"role": "user", "content": "上次输出格式不符合契约。请重新输出合法JSON，structured闭集字段及当前类型完整elements；不要提问。"}])
                    try:
                        output = parse_model_output(repaired.raw)
                        result = process(output, prepared.form, prepared.sources, prepared.prev_elements, prepared.prev_target, prepared.previous_form, req.message, standards=registry)
                    except (ValueError, TypeError, KeyError):
                        self.llm.on_failure()
                        logger.warning("模型输出连续两次解析失败，按AI不可用处理（首次原始输出前80字符：%s）", str(final.raw)[:80])
                        raise LlmUnavailable from None
                    final = repaired
                self.llm.on_success()
            except LlmUnavailable:
                raise BizError(ErrorCode.AI_SERVICE_UNAVAILABLE) from None
            from app.services.demand_service import apply_agent_patch
            async with self.db.begin():
                demand = (await self.db.execute(select(Demand).where(Demand.id == req.demand_id, Demand.submitter_id == self.user_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
                if demand is None:
                    raise BizError(ErrorCode.DEMAND_NOT_FOUND)
                agent_session = await session_service.require_owned(self.db, self.user, req.session_id, lock=True)
                saved = await self._saved(req)
                if saved:
                    return saved
                if demand.session_id != agent_session.id or agent_session.demand_id != demand.id:
                    raise BizError(ErrorCode.CONFLICT)
                if agent_session.status != "ACTIVE" or demand.status != "DRAFT":
                    raise BizError(ErrorCode.CONFLICT, "模型处理期间草稿已提交或关闭")
                if demand.revision != req.revision:
                    raise BizError(ErrorCode.CONFLICT, "模型处理期间草稿已更新")
                demand = await apply_agent_patch(self.db, self.user, demand, expected_revision=req.revision, patch=result["structured"], field_sources=result["fieldSources"])
                result["structured"] = demand_form(demand)
                result["fieldSources"] = deepcopy(demand.field_sources or {})
                result.update(demandId=req.demand_id, sessionId=req.session_id, requestId=req.request_id, revision=demand.revision)
                response = GuideResult.model_validate(result)
                prompt_standard = registry[prepared.form.get("demandTypeCode") or "MATL"]
                version = await ensure_snapshot(self.db, prompt_standard, prompt_template=raw_template, rendered_prompt=rendered_prompt, injected_standards=list(registry.values()))
                payload = response.model_dump(mode="json", by_alias=True)
                usage = final.usage or {}
                metadata = dict(request_id=req.request_id, request_hash=request_hash(req), prompt_version_id=version.id, model=self.llm.settings.llm_chat_model, prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"), latency_ms=int((time.monotonic() - started) * 1000))
                await session_service.append(self.db, req.session_id, "USER", req.message, **metadata)
                await session_service.append(self.db, req.session_id, "ASSISTANT", response.reply, payload, **metadata)
                agent_session.asked_target = response.asked_target
            return response

    async def stream(self, req):
        yield sse("processing", {"requestId": req.request_id, "status": "processing"})
        try:
            result = await self.execute(req)
        except BizError as error:
            yield sse("error", {"code": error.code, "message": error.message, "requestId": req.request_id})
            return
        except Exception as error:
            logger.error("Agent对话处理失败，异常类型=%s", type(error).__name__)
            if self.db.in_transaction():
                await self.db.rollback()
            yield sse("error", {"code": 500, "message": "系统内部错误", "requestId": req.request_id})
            return
        # 已提交成功才发回复与结构化结果；取消时不在finally补写。
        yield sse("message", {"delta": result.reply})
        yield sse("structured", result.model_dump(mode="json", by_alias=True, exclude={"reply"}))
        yield sse("done", {"requestId": req.request_id, "status": "completed"})


def sse(event, payload):
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
