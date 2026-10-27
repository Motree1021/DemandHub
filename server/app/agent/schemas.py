"""模型结果、客户端请求和最终响应分别定义，拒绝游离表单输入。"""
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class AgentModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ElementStatus(AgentModel):
    key: str
    label: str = ""
    status: Literal["OK", "VAGUE", "MISSING", "SKIP"]
    note: str = ""
    attempts: int = Field(default=0, ge=0, le=2)


class GuideChatRequest(AgentModel):
    demand_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    request_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    revision: int = Field(ge=0)
    message: str = Field(min_length=1, max_length=20000)

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("消息内容不能为空")
        return value


class CreateSessionRequest(AgentModel):
    demand_id: int = Field(gt=0)
    scene: Literal["SUBMIT_GUIDE", "HANDLE_ASSIST"] = "SUBMIT_GUIDE"
    first_message: str = Field(default="", max_length=20000)


class TypeSignalVote(AgentModel):
    """单层判型投票：置信度 + 依据原文片段（PRD §4.3、FR-03）。"""
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: str = ""


class TypeSignalsOutput(AgentModel):
    business: TypeSignalVote = Field(default_factory=TypeSignalVote)
    user: TypeSignalVote = Field(default_factory=TypeSignalVote)
    function: TypeSignalVote = Field(default_factory=TypeSignalVote)


class ModeSignalOutput(AgentModel):
    """微需求快速通道（2026-10-11 方案②）：AI 轻重判定票，light 走 4 项最小集。"""
    level: Literal["light", "standard"]
    evidence: str = ""


class Intent(AgentModel):
    """本轮消息意图（2026-10-19 拍板）：模型只判断「用户在做什么」；
    计不计 attempts、说什么话、流程怎么走由纯函数决定（policy.process）。
    answer=在回答当前问题（默认，缺省按此处理，向后兼容）；supplement=补充/纠正之前的内容，
    未回答当前问题（targetKey 指向被补充要素）；chitchat=纯寒暄/与需求无关；
    question=在向 AI 提问（targetKey 指向相关要素）；command=发出指令（如「提交吧」）。"""
    kind: Literal["answer", "supplement", "chitchat", "question", "command"] = "answer"
    target_key: str | None = None


class ModelOutput(BaseModel):
    structured: dict[str, Any] = Field(default_factory=dict)
    elements: list[ElementStatus] = Field(default_factory=list)
    type_signals: TypeSignalsOutput | None = None
    mode_signal: ModeSignalOutput | None = None
    intent: Intent | None = None


class GuideResult(AgentModel):
    demand_id: int
    session_id: int
    request_id: str
    revision: int
    reply: str
    structured: dict[str, Any]
    field_sources: dict[str, str]
    missing: list[str]
    elements: list[ElementStatus]
    asked_target: str | None
    can_submit: bool
    guidance_complete: bool
    quality_complete: bool
    ready: bool
    quick_replies: list[str]
    type_recognition: dict[str, Any] | None = None
    mode: dict[str, Any] | None = None
    granularity_hint: dict[str, str] | None = None
    # 本轮意图（2026-10-20 拍板）：随 ASSISTANT 消息 payload 落库，提交时按 request_id 配对
    # 排除闲聊/提问/指令轮的用户消息，底稿只拼接有效对话；存量消息无此字段视为有效（保守保留）
    intent: str | None = None


def _parse_type_signals(value) -> TypeSignalsOutput | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("typeSignals 必须为对象")
    votes = {}
    for layer in ("business", "user", "function"):
        item = value.get(layer) or {}
        if not isinstance(item, dict):
            raise ValueError("typeSignals 层必须为对象")
        confidence = item.get("confidence", 0)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("typeSignals 置信度必须为0~1数值")
        votes[layer] = TypeSignalVote(confidence=float(confidence), evidence=item.get("evidence") if isinstance(item.get("evidence"), str) else "")
    return TypeSignalsOutput(**votes)


def parse_model_output(raw: str) -> ModelOutput:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines[-1].strip() != "```":
            raise ValueError("JSON 围栏未结束")
        raw = "\n".join(lines[1:-1])
    value = json.loads(raw)
    if not isinstance(value, dict) or not isinstance(value.get("structured"), dict) or not isinstance(value.get("elements"), list):
        raise ValueError("模型必须输出 structured 对象和 elements 数组")
    seen = set()
    elements = []
    for item in value["elements"]:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str) or item["key"] in seen:
            raise ValueError("模型质量 key 无效或重复")
        seen.add(item["key"])
        status = item.get("status")
        if status not in {"OK", "VAGUE", "MISSING"}:
            status = "VAGUE"
        elements.append(ElementStatus(key=item["key"], status=status, note=item.get("note") if isinstance(item.get("note"), str) else ""))
    return ModelOutput(structured=value["structured"], elements=elements, type_signals=_parse_type_signals(value.get("typeSignals")), mode_signal=_parse_mode_signal(value.get("modeSignal")), intent=_parse_intent(value.get("intent")))


def _parse_intent(value) -> Intent | None:
    """intent 可选且宽容（2026-10-19 拍板）：五选一辅助信号，kind 非法/结构畸形时按未输出
    （answer）处理，不像 modeSignal 那样抛错走整轮修复——为一个辅助标签重试整轮不划算。"""
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if kind not in ("answer", "supplement", "chitchat", "question", "command"):
        return None
    target_key = value.get("targetKey") if isinstance(value.get("targetKey"), str) else None
    return Intent(kind=kind, target_key=target_key or None)


def _parse_mode_signal(value) -> ModeSignalOutput | None:
    """modeSignal 轻重判定票可选；level 非法按格式错误处理（与 typeSignals 同口径走修复重试）。"""
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("level") not in ("light", "standard"):
        raise ValueError("modeSignal.level 必须为 light/standard")
    return ModeSignalOutput(level=value["level"], evidence=value.get("evidence") if isinstance(value.get("evidence"), str) else "")
