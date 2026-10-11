"""手改要素后的概述后台重写（FR-06 联动）：读最新表单→锁内串行调模型→短事务复验写回。

失败静默跳过（AI 冷却/超时/解析失败保留旧概述），不影响保存动作；不加 revision、
不写聊天消息、不写留痕（ext.overview 是 AI 派生摘要，与 guide 链路同口径）。
"""
import asyncio
import json
import logging
import weakref

from sqlalchemy import select

from app.agent.llm_client import LlmUnavailable, get_llm_client
from app.db import session as db_session
from app.db.models import Demand

logger = logging.getLogger(__name__)
_locks = weakref.WeakValueDictionary()

# 概述四段固定键（与 submit_guide.md 概述规则、详情页 OVERVIEW_LABELS 同源）
OVERVIEW_KEYS = ("problem", "userScene", "goal", "acceptance")

PROMPT = """你是 DemandHub 的需求摘要助手，基于给定需求表单生成「需求概述」，供详情页给提报人一眼看懂自己提了什么。
只输出一个 JSON 对象，不加 Markdown。固定四个键：problem（问题/机会）、userScene（用户&场景）、goal（目标&期望效果）、acceptance（验收标准）。
每段值格式为"详细描述｜一句话概括"：详细描述整合对应要素的事实（problem←用户痛点、userScene←用户角色+使用场景、goal←用户目标/业务目标+功能描述、acceptance←验收标准），不新增表单没有的信息；一句话概括20字内点出本质。用大白话，不使用「业务需求/用户需求/功能需求」术语。
对应要素缺失的段省略该键，四段都无依据时输出 {}。
【需求表单】
{form}"""


def _lock(demand_id: int) -> asyncio.Lock:
    lock = _locks.get(demand_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[demand_id] = lock
    return lock


def parse_overview(raw: str) -> dict | None:
    """解析模型输出：仅保留四键内的非空字符串段；结构非法或全空返回 None。"""
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    result = {key: value[key].strip() for key in OVERVIEW_KEYS
              if isinstance(value.get(key), str) and value[key].strip()}
    return result or None


def schedule_overview_rewrite(demand_id: int, user_id: int):
    """手工改要素保存事务提交后调用：即发即忘排队执行，串行保证最后完成的任务用最新表单。"""

    async def run():
        async with _lock(demand_id):
            try:
                await rewrite_overview(demand_id, user_id)
            except Exception:
                logger.warning("概述后台重写异常 demand_id=%s", demand_id, exc_info=True)

    asyncio.create_task(run())


async def rewrite_overview(demand_id: int, user_id: int, llm=None) -> None:
    """锁内执行：读最新表单→锁外占用仅模型调用→短事务复验写回。测试经 llm 参数注入桩。"""
    client = llm or get_llm_client()
    if not client.available():
        logger.info("AI不可用跳过概述重写 demand_id=%s", demand_id)
        return
    factory = db_session.get_session_factory()  # 模块属性访问：测试 monkeypatch 受控 factory 生效
    async with factory() as db:
        demand = (await db.execute(select(Demand).where(Demand.id == demand_id,
                                                        Demand.submitter_id == user_id))).scalar_one_or_none()
        if demand is None or demand.status != "DRAFT":
            return
        from app.services.demand_service import form_of
        form = form_of(demand)
        await db.rollback()  # ORM 读取 autobegin：显式结束，模型等待不占数据库连接
        messages = [{"role": "system", "content": PROMPT.replace("{form}",
                     json.dumps(form, ensure_ascii=False))}]
        try:
            final = await client.complete_json(messages)
        except LlmUnavailable:
            logger.warning("概述重写模型调用失败，保留旧概述 demand_id=%s", demand_id)
            return
        overview = parse_overview(final.raw)
        if overview is None:
            logger.warning("概述重写输出无法解析，保留旧概述 demand_id=%s（前80字符：%s）",
                           demand_id, str(final.raw)[:80])
            return
        client.on_success()
        async with db.begin():
            fresh = (await db.execute(select(Demand).where(Demand.id == demand_id,
                Demand.submitter_id == user_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
            if fresh is None or fresh.status != "DRAFT":
                return  # 模型等待期间草稿已提交/关闭：概述无需再写
            ext = dict(fresh.ext or {})
            ext["overview"] = overview
            fresh.ext = ext
            sources = dict(fresh.field_sources or {})
            sources["ext.overview"] = "agent"
            fresh.field_sources = sources
        logger.info("概述后台重写完成 demand_id=%s 段数=%s", demand_id, len(overview))
