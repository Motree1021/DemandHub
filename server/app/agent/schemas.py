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
    scene: Literal["SUBMIT_GUIDE"] = "SUBMIT_GUIDE"
    first_message: str = Field(default="", max_length=20000)


class TypeSignalVote(AgentModel):
    """单层判型投票：置信度 + 依据原文片段（PRD §4.3、FR-03）。"""
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: str = ""


class TypeSignalsOutput(AgentModel):
    business: TypeSignalVote = Field(default_factory=TypeSignalVote)
    user: TypeSignalVote = Field(default_factory=TypeSignalVote)
    function: TypeSignalVote = Field(default_factory=TypeSignalVote)


class ModelOutput(BaseModel):
    structured: dict[str, Any] = Field(default_factory=dict)
    elements: list[ElementStatus] = Field(default_factory=list)
    type_signals: TypeSignalsOutput | None = None


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
    granularity_hint: dict[str, str] | None = None
    impact_hints: list[str] = Field(default_factory=list)


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
    return ModelOutput(structured=value["structured"], elements=elements, type_signals=_parse_type_signals(value.get("typeSignals")))
