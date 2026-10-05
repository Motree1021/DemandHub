"""加载可审查的标准，并把完整内容保存成不可变版本。"""
import hashlib
import json
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert

from app.standards.schema import Standard

STANDARD_DIR = Path(__file__).parent
TEMPLATE_PATH = STANDARD_DIR.parent / "agent" / "prompts" / "submit_guide.md"
RENDERER_VERSION = "1"


class StandardLoader:
    def __init__(self, directory: Path = STANDARD_DIR):
        self.directory = Path(directory)
        self._standards: dict[str, Standard] = {}

    def load_all(self) -> dict[str, Standard]:
        loaded = {}
        for path in sorted(self.directory.glob("*.yaml")):
            source = path.read_text(encoding="utf-8")
            data = yaml.safe_load(source)
            if not isinstance(data, dict):
                raise ValueError("标准 YAML 须为对象")
            for group in data.get("subtype_fields", {}).values():
                for field in group:
                    field.setdefault("path", "ext." + field["key"])
                    field.setdefault("kind", "text")
            standard = Standard.model_validate({**data, "content_hash": hashlib.sha256(source.encode()).hexdigest(), "source_text": source})
            if standard.type in loaded:
                raise ValueError("需求类型标准重复")
            loaded[standard.type] = standard
        if not loaded:
            raise ValueError("没有需求标准")
        self._standards = loaded
        return dict(loaded)

    async def ensure_snapshot(self, db, standard, prompt_template=None, **kwargs):
        return await ensure_snapshot(db, standard, prompt_template, **kwargs)

    def get(self, type_code: str) -> Standard:
        if not self._standards:
            self.load_all()
        try:
            return self._standards[type_code]
        except KeyError:
            from app.core.errors import BizError, ErrorCode
            raise BizError(ErrorCode.DEMAND_TYPE_INVALID) from None


loader = StandardLoader()


def load_all():
    return loader.load_all()


def get(type_code: str) -> Standard:
    return loader.get(type_code)


def snapshot(standard: Standard, prompt_template: str | None = None, *, rendered_prompt=None, injected_standards=None) -> dict:
    return {
        "standard": standard.model_dump(mode="json", by_alias=True),
        "standardSource": standard.source_text,
        "promptTemplate": TEMPLATE_PATH.read_text(encoding="utf-8") if prompt_template is None else prompt_template,
        "rendererVersion": RENDERER_VERSION,
        "renderedPrompt": rendered_prompt,
        "injectedStandards": [{"standard": item.model_dump(mode="json", by_alias=True), "standardSource": item.source_text} for item in (injected_standards or [])],
    }


def snapshot_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


async def ensure_snapshot(db, standard: Standard, prompt_template: str | None = None, *, rendered_prompt=None, injected_standards=None):
    from app.db.models import PromptVersion
    value = snapshot(standard, prompt_template, rendered_prompt=rendered_prompt, injected_standards=injected_standards)
    digest = snapshot_hash(value)
    # 同一标准由不同会话并发使用时，以唯一 hash 原子去重，不覆盖旧正文。
    statement = insert(PromptVersion).values(code=standard.type, version=standard.version, content_hash=digest, snapshot=value)
    await db.execute(statement.on_duplicate_key_update(content_hash=statement.inserted.content_hash))
    return (await db.execute(select(PromptVersion).where(PromptVersion.content_hash == digest))).scalar_one()
