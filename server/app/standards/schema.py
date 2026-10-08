"""标准既驱动表单，也约束所有保存入口。"""
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class StandardModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid", frozen=True)


class Rule(StandardModel):
    min_len: int | None = Field(default=None, ge=0)
    max_len: int | None = Field(default=None, ge=1)
    any_of: list[str] = Field(default_factory=list)
    any_of_regex: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_rule(self):
        if self.min_len is not None and self.max_len is not None and self.min_len > self.max_len:
            raise ValueError("min_len 不得大于 max_len")
        for pattern in self.any_of_regex:
            try:
                re.compile(pattern)
            except re.error:
                raise ValueError("标准正则表达式无效") from None
        return self


class Element(StandardModel):
    key: str
    label: str
    kind: Literal["text", "enum", "number", "date", "list"] = "text"
    path: str | None = None
    code: str = ""
    zone: Literal["A", "B", "C", "D"] | None = None
    system: bool = False
    required: bool = False
    options: dict[str, str] = Field(default_factory=dict)
    default: Any = None
    placeholder: str = ""
    ok_when: str = ""
    rule: Rule = Field(default_factory=Rule)
    vague_hint: str = "内容还不够具体"
    ask_missing: str = ""
    ask_l1: str = ""
    ask_l2: str = ""

    @property
    def field_path(self) -> str:
        return self.path or self.key

    @model_validator(mode="after")
    def valid_element(self):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", self.key):
            raise ValueError("标准 key 格式无效")
        if self.path and not re.fullmatch(r"ext\.[A-Za-z][A-Za-z0-9]*|elements\.[A-D]\.[A-Za-z][A-Za-z0-9]*", self.path):
            raise ValueError("扩展 path 必须是 ext.key 或 elements.区.key")
        if self.code:
            if not re.fullmatch(r"[A-D][1-9]\d*", self.code):
                raise ValueError("要素序号 code 必须是 A1..D9 形式")
            if self.zone is None or self.code[0] != self.zone:
                raise ValueError("要素序号 code 的区字母必须与 zone 一致")
        if self.system and self.zone != "A":
            raise ValueError("system 快照要素仅允许在 A 区")
        if self.kind == "enum" and not self.options:
            raise ValueError("enum 必须提供 options")
        if self.kind != "enum" and self.options:
            raise ValueError("仅 enum 可以提供 options")
        return self


class TypeSignal(StandardModel):
    label: str
    keywords: list[str] = Field(default_factory=list)


class TypeSignals(StandardModel):
    """PRD §4.3 三层判型信号表（供 LLM 判型提示词，P2 消费）。"""
    business: TypeSignal | None = None
    user: TypeSignal | None = None
    function: TypeSignal | None = None


class GranularityRule(StandardModel):
    keywords: list[str] = Field(default_factory=list)
    hint: str = ""


class Granularity(StandardModel):
    """BR-T13 粒度治理配置：目标级分解 / 字段级补全，收敛标准统一。"""
    converge: str = ""
    too_broad: GranularityRule = Field(default_factory=GranularityRule)
    too_narrow: GranularityRule = Field(default_factory=GranularityRule)


class Standard(StandardModel):
    type: Literal["TECH", "MATL", "TRAIN"]
    name: str
    version: str
    glossary: list[str] = Field(default_factory=list)
    elements: list[Element]
    follow_up_order: list[str] = Field(default_factory=list)
    max_attempts: int = Field(default=2, ge=1, le=2)
    vague_words: list[str] = Field(default_factory=list)
    skip_phrases: list[str] = Field(default_factory=list)
    optional_fields: list[Element] = Field(default_factory=list)
    subtype_fields: dict[str, list[Element]] = Field(default_factory=dict)
    common_fields: list[Element] = Field(default_factory=list)
    type_signals: TypeSignals = Field(default_factory=TypeSignals)
    granularity: Granularity = Field(default_factory=Granularity)
    content_hash: str = ""
    source_text: str = Field(default="", exclude=True)

    @property
    def fields(self) -> list[Element]:
        return self.elements + self.optional_fields + self.common_fields + [f for group in self.subtype_fields.values() for f in group]

    @model_validator(mode="after")
    def valid_standard(self):
        keys = [element.key for element in self.fields]
        paths = [element.field_path for element in self.fields]
        if len(keys) != len(set(keys)) or len(paths) != len(set(paths)):
            raise ValueError("标准字段 key/path 不得重复")
        codes = [element.code for element in self.elements if element.code]
        if len(codes) != len(set(codes)):
            raise ValueError("标准要素序号 code 不得重复")
        element_keys = {element.key for element in self.elements}
        if len(self.follow_up_order) != len(set(self.follow_up_order)) or not set(self.follow_up_order) <= element_keys:
            raise ValueError("follow_up_order 必须引用唯一的质量要素")
        required = {e.key for e in self.elements if e.required}
        if not {"title", "demandTypeCode", "content"} <= required:
            raise ValueError("标准必须声明 title/demandTypeCode/content 为必填")
        return self
