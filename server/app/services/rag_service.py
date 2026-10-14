"""RAG 相似需求知识库（照蓝本 RagService）：DONE 需求异步向量化，相似需求 Top N 召回。

一期：rag_vector 表 JSON 列存向量 + 应用层余弦相似度（蓝本同口径，阈值 0.08）；
embedding 平台不可用 → 相似推荐降级为空、向量化跳过，均不影响业务主流程。
ACCEPT_PASS（验收通过 → DONE）落点 asyncio.create_task 即发即忘（照 overview 先例）。
"""
import asyncio
import json
import logging
import math
import weakref

from sqlalchemy import select

from app.agent.llm_client import LlmUnavailable, get_llm_client
from app.db import session as db_session
from app.db.models import Demand, RagVector, Review, Solution, now

logger = logging.getLogger(__name__)
_locks = weakref.WeakValueDictionary()

# 相似度阈值（余弦）：低于不推荐（蓝本 SCORE_THRESHOLD）
SCORE_THRESHOLD = 0.08


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度；维度不一致或零向量得 0 分（跨 embedding 模型向量不可比，须重建）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def similar(db, demand_id: int, top_n: int, llm=None) -> list[dict]:
    """相似历史需求 Top N（处理人打开需求时调用）；平台不可用/无候选 → 空列表。"""
    demand = await db.get(Demand, demand_id)
    if demand is None:
        return []
    client = llm or get_llm_client()
    try:
        query_vec = await client.embed(demand.title + "\n" + (demand.content or ""))
    except LlmUnavailable:
        logger.warning("[RAG] embedding 不可用，相似推荐跳过 demand_id=%s", demand_id)
        return []
    docs = list((await db.execute(
        select(RagVector).where(RagVector.status == "ACTIVE", RagVector.demand_id != demand_id)
    )).scalars())
    scored = []
    for doc in docs:
        score = cosine(query_vec, json.loads(doc.embedding))
        if score >= SCORE_THRESHOLD:
            scored.append({"demandId": doc.demand_id, "demandNo": doc.demand_no, "title": doc.title,
                           "demandTypeCode": doc.demand_type_code, "score": round(score, 3)})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[: max(1, top_n)]


async def similar_docs(db, demand_id: int, top_n: int, llm=None) -> list[RagVector]:
    """检索 Top N 完整文档（处理辅助生成时引用，按命中顺序）。"""
    hits = await similar(db, demand_id, top_n, llm=llm)
    if not hits:
        return []
    ids = [hit["demandId"] for hit in hits]
    docs = list((await db.execute(select(RagVector).where(RagVector.demand_id.in_(ids)))).scalars())
    by_demand = {doc.demand_id: doc for doc in docs}
    return [by_demand[i] for i in ids if i in by_demand]


async def vectorize_done_demand(db, demand_id: int, llm=None) -> bool:
    """DONE 需求向量化入库（demand_id 唯一幂等）；内容 = 标题+需求描述+最新方案+评审意见。"""
    exists = (await db.execute(select(RagVector.id).where(RagVector.demand_id == demand_id))).first()
    if exists:
        return False
    demand = await db.get(Demand, demand_id)
    if demand is None or demand.status != "DONE":
        logger.warning("[RAG] 跳过向量化：需求不存在或非 DONE demand_id=%s", demand_id)
        return False
    parts = [demand.title]
    if demand.content:
        parts.append(demand.content)
    solution = (await db.execute(
        select(Solution).where(Solution.demand_id == demand_id)
        .order_by(Solution.version.desc()).limit(1)
    )).scalar_one_or_none()
    if solution is not None:
        if solution.spec_content:
            parts.append("【需求规约】" + solution.spec_content)
        if solution.solution_content:
            parts.append("【方案】" + solution.solution_content)
    reviews = list((await db.execute(
        select(Review).where(Review.demand_id == demand_id).order_by(Review.id)
    )).scalars())
    for review in reviews:
        if review.opinion and review.opinion.strip():
            parts.append(f"【评审意见-{review.result}】" + review.opinion)
    content = "\n".join(parts)
    client = llm or get_llm_client()
    try:
        embedding = await client.embed(content)
    except LlmUnavailable:
        logger.warning("[RAG] embedding 不可用，向量化跳过 demand_id=%s", demand_id)
        return False
    db.add(RagVector(demand_id=demand.id, demand_no=demand.demand_no, title=demand.title,
                     demand_type_code=demand.demand_type_code, content=content,
                     embedding=json.dumps(embedding), status="ACTIVE", vectorized_at=now()))
    logger.info("[RAG] 需求 %s 已向量化入库（%s 字）", demand.demand_no, len(content))
    return True


def _lock(demand_id: int) -> asyncio.Lock:
    lock = _locks.get(demand_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[demand_id] = lock
    return lock


def schedule_vectorize(demand_id: int):
    """验收通过事务提交后调用：即发即忘；同需求串行防重复消费（照 overview 先例）。"""

    async def run():
        async with _lock(demand_id):
            try:
                factory = db_session.get_session_factory()  # 模块属性访问：测试 monkeypatch 受控 factory 生效
                async with factory() as db:
                    async with db.begin():
                        await vectorize_done_demand(db, demand_id)
            except Exception:
                logger.warning("[RAG] 向量化后台任务异常 demand_id=%s", demand_id, exc_info=True)

    asyncio.create_task(run())
