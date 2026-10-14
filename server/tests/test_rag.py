"""P3 RAG 相似需求单测：余弦计算、阈值过滤、Top N、DONE 向量化幂等与降级、后台任务。

覆盖口径：
- cosine：相同向量 1.0、正交 0.0、维度不一致/零向量/空 → 0.0
- vectorize_done_demand：内容 = 标题+描述+最新方案（version 最大）+评审意见（空白跳过）；
  重复向量化幂等跳过、非 DONE 跳过、embedding 平台不可用 → False 不入库
- similar：阈值 0.08 过滤、score 降序 Top N、排除自身与 INACTIVE、平台不可用/需求不存在 → []
- GET /agent/rag/similar：topN clamp 1..10
- schedule_vectorize：同需求串行防重、异常吞掉不影响主流程（照 overview 先例）
"""
import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.llm_client import LlmUnavailable, get_llm_client
from app.db.models import Demand, RagVector, Review, Solution, User
from app.services import rag_service

BASE = "/demandhub-api"


class FakeEmbed:
    """embedding 桩：返回固定向量；unavailable 时抛 LlmUnavailable。"""

    def __init__(self, vector=(1.0, 0.0)):
        self.vector = list(vector)
        self.unavailable = False
        self.texts: list[str] = []

    async def embed(self, text):
        if self.unavailable:
            raise LlmUnavailable
        self.texts.append(text)
        return list(self.vector)


async def make_user(factory) -> User:
    async with factory() as db:
        async with db.begin():
            user = User(name="rag用户", wecom_userid=f"rag-{uuid4().hex[:8]}", channel="CHUANGJIN_LS")
            db.add(user)
            await db.flush()
            db.expunge(user)
            return user


async def make_demand(factory, user, status, title, content="需求描述", type_code="TECH") -> int:
    async with factory() as db:
        async with db.begin():
            demand = Demand(demand_no=f"DH{uuid4().hex[:12]}", title=title, content=content,
                            demand_type_code=type_code, status=status, submitter_id=user.id,
                            client_request_id=f"rag-{uuid4().hex}", create_request_hash=uuid4().hex)
            db.add(demand)
            await db.flush()
            return demand.id


async def make_vector(factory, demand_id, embedding, status="ACTIVE", demand_no=None, title="历史需求"):
    async with factory() as db:
        async with db.begin():
            db.add(RagVector(demand_id=demand_id, demand_no=demand_no or f"DH{uuid4().hex[:12]}",
                             title=title, demand_type_code="TECH", content="历史内容",
                             embedding=json.dumps(embedding), status=status))


def test_cosine_math():
    assert rag_service.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert rag_service.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert rag_service.cosine([3.0, 4.0], [4.0, 3.0]) == pytest.approx(0.96)
    # 维度不一致 / 零向量 / 空：跨模型向量不可比，安全得 0 分
    assert rag_service.cosine([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0
    assert rag_service.cosine([0.0, 0.0], [1.0, 0.0]) == 0.0
    assert rag_service.cosine([], []) == 0.0


async def test_vectorize_done_demand_builds_content(session_factory):
    user = await make_user(session_factory)
    did = await make_demand(session_factory, user, "DONE", "持仓报表", "每天晨会前查询持仓")
    async with session_factory() as db:
        async with db.begin():
            db.add(Solution(demand_id=did, version=1, author_id=user.id,
                            spec_content="旧规约", solution_content="旧方案"))
            db.add(Solution(demand_id=did, version=2, author_id=user.id,
                            spec_content="新规约", solution_content="新方案"))
            db.add(Review(demand_id=did, review_type="SOLUTION", result="PASS",
                          opinion="方案合理", reviewer_id=user.id))
            db.add(Review(demand_id=did, review_type="SOLUTION", result="REJECT",
                          opinion="   ", reviewer_id=user.id))  # 空白意见跳过
            db.add(Review(demand_id=did, review_type="ACCEPTANCE", result="PASS",
                          opinion="验收通过", reviewer_id=user.id))
    fake = FakeEmbed((0.5, 0.5))
    async with session_factory() as db:
        async with db.begin():
            assert await rag_service.vectorize_done_demand(db, did, llm=fake) is True
    expected = ("持仓报表\n每天晨会前查询持仓\n【需求规约】新规约\n【方案】新方案"
                "\n【评审意见-PASS】方案合理\n【评审意见-PASS】验收通过")
    assert fake.texts == [expected]  # 取 version 最大的方案；空白评审意见不进向量
    async with session_factory() as db:
        rag = (await db.execute(select(RagVector).where(RagVector.demand_id == did))).scalar_one()
        assert rag.content == expected and json.loads(rag.embedding) == [0.5, 0.5]
        assert rag.status == "ACTIVE" and rag.demand_no and rag.vectorized_at


async def test_vectorize_idempotent_and_non_done_skipped(session_factory):
    user = await make_user(session_factory)
    done_id = await make_demand(session_factory, user, "DONE", "已完成需求")
    fake = FakeEmbed()
    async with session_factory() as db:
        async with db.begin():
            assert await rag_service.vectorize_done_demand(db, done_id, llm=fake) is True
    async with session_factory() as db:
        async with db.begin():
            assert await rag_service.vectorize_done_demand(db, done_id, llm=fake) is False  # 幂等
    draft_id = await make_demand(session_factory, user, "DRAFT", "草稿需求")
    async with session_factory() as db:
        async with db.begin():
            assert await rag_service.vectorize_done_demand(db, draft_id, llm=fake) is False  # 非 DONE
    async with session_factory() as db:
        rows = list((await db.execute(select(RagVector))).scalars())
        assert len(rows) == 1 and rows[0].demand_id == done_id
        assert len(fake.texts) == 1  # 跳过场景不调 embedding


async def test_vectorize_degrades_when_embed_unavailable(session_factory):
    user = await make_user(session_factory)
    did = await make_demand(session_factory, user, "DONE", "已完成需求")
    fake = FakeEmbed()
    fake.unavailable = True
    async with session_factory() as db:
        async with db.begin():
            assert await rag_service.vectorize_done_demand(db, did, llm=fake) is False
    async with session_factory() as db:
        assert (await db.execute(select(RagVector))).first() is None  # 平台故障不留垃圾数据


async def test_similar_threshold_topn_and_excludes_self(session_factory):
    user = await make_user(session_factory)
    current = await make_demand(session_factory, user, "ANALYZING", "当前需求", "当前内容")
    near = await make_demand(session_factory, user, "DONE", "高度相似")
    mid = await make_demand(session_factory, user, "DONE", "部分相似")
    far = await make_demand(session_factory, user, "DONE", "毫不相关")
    inactive = await make_demand(session_factory, user, "DONE", "已下线")
    await make_vector(session_factory, near, [1.0, 0.0])          # 1.0
    await make_vector(session_factory, mid, [1.0, 1.0])           # ≈0.707
    await make_vector(session_factory, far, [0.0, 1.0])           # 0.0 < 阈值
    await make_vector(session_factory, inactive, [1.0, 0.0], status="INACTIVE")  # 状态过滤
    await make_vector(session_factory, current, [1.0, 0.0])       # 自身排除
    fake = FakeEmbed((1.0, 0.0))
    async with session_factory() as db:
        hits = await rag_service.similar(db, current, 5, llm=fake)
        assert [h["demandId"] for h in hits] == [near, mid]
        assert hits[0]["score"] == 1.0 and hits[1]["score"] == 0.707  # 降序 + round(3)
        assert set(hits[0]) == {"demandId", "demandNo", "title", "demandTypeCode", "score"}
        # Top N 截断
        top1 = await rag_service.similar(db, current, 1, llm=fake)
        assert [h["demandId"] for h in top1] == [near]


async def test_similar_empty_when_unavailable_or_missing(session_factory):
    user = await make_user(session_factory)
    current = await make_demand(session_factory, user, "ANALYZING", "当前需求")
    fake = FakeEmbed()
    fake.unavailable = True
    async with session_factory() as db:
        assert await rag_service.similar(db, current, 5, llm=fake) == []  # 平台降级
        assert await rag_service.similar(db, 999999, 5, llm=fake) == []  # 需求不存在


async def test_similar_api_clamps_top_n(client, auth_headers, session_factory):
    user = await make_user(session_factory)
    current = await make_demand(session_factory, user, "ANALYZING", "当前需求")
    near = await make_demand(session_factory, user, "DONE", "相似一")
    mid = await make_demand(session_factory, user, "DONE", "相似二")
    await make_vector(session_factory, near, [1.0, 0.0])
    await make_vector(session_factory, mid, [1.0, 1.0])
    client._transport.app.dependency_overrides[get_llm_client] = lambda: FakeEmbed()
    # topN=99 → clamp 10（候选 2 个全返回）；topN=0 → clamp 1（只回最高分）
    wide = await client.get(BASE + "/agent/rag/similar", headers=auth_headers,
                            params={"demandId": current, "topN": 99})
    assert wide.json()["code"] == 0 and len(wide.json()["data"]) == 2
    narrow = await client.get(BASE + "/agent/rag/similar", headers=auth_headers,
                              params={"demandId": current, "topN": 0})
    assert [h["demandId"] for h in narrow.json()["data"]] == [near]


async def test_schedule_vectorize_serializes_concurrent_runs(monkeypatch):
    # 同一需求连续排两个后台任务：锁串行，第一个未完成时第二个等待（照 overview 先例）
    order = []
    release = asyncio.Event()

    async def fake_vectorize(db, demand_id):
        order.append(("start", demand_id))
        await release.wait()
        order.append(("end", demand_id))

    monkeypatch.setattr(rag_service, "vectorize_done_demand", fake_vectorize)
    rag_service.schedule_vectorize(111)
    await asyncio.sleep(0.01)
    rag_service.schedule_vectorize(111)
    await asyncio.sleep(0.01)
    assert order == [("start", 111)]
    release.set()
    await asyncio.sleep(0.05)
    assert order == [("start", 111), ("end", 111), ("start", 111), ("end", 111)]


async def test_schedule_vectorize_swallows_errors(monkeypatch):
    # 后台任务异常不外泄：验收主流程响应不受影响
    ran = []

    async def fake_vectorize(db, demand_id):
        ran.append(demand_id)
        raise RuntimeError("模拟向量化崩溃")

    monkeypatch.setattr(rag_service, "vectorize_done_demand", fake_vectorize)
    rag_service.schedule_vectorize(222)
    await asyncio.sleep(0.05)
    assert ran == [222]
