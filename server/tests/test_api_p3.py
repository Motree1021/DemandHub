"""P3 验收：响应体 changeLogs 联表（FR-06/E7）、legacy ext 写入兼容（P4 前 H5 手填）、export 五区分区排版（A8 置首/E 区附注）、SSE 下发判型与粒度字段。"""
import json

from app.agent.llm_client import get_llm_client
from tests.test_guide import FakeArk

ACD = {"A": {"techSubtype": "DATA_RPT"},
       "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各渠道持仓汇总",
             "useScenario": "客户经理每天晨会前查询各渠道持仓并整理晨会材料",
             "painPoint": "手工统计20多个渠道持仓每次近40分钟容易出错"},
       "D": {"functionDescription": "按渠道汇总前一交易日持仓并生成报表支持导出",
             "inputOutput": "输入交易流水输出持仓汇总报表",
             "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}

FULL = {"title": "持仓自动报表", "demandTypeCode": "TECH", "urgency": "NORMAL",
        "content": "每天晨会前客户经理需要查询渠道持仓并汇总报表，替代手工统计，提高晨会准备效率。",
        "elements": ACD, "fieldSources": {"title": "user", "demandTypeCode": "user", "content": "user", "urgency": "user"}}


async def create_full(client, auth_headers, request_id="p3-full"):
    return (await client.post("/demandhub-api/demand", headers=auth_headers,
                              json={"clientRequestId": request_id, **FULL})).json()["data"]


async def test_submit_then_detail_elements_complete_and_change_logs_empty(client, auth_headers):
    draft = await create_full(client, auth_headers)
    assert draft["changeLogs"] == []  # 创建不产生留痕
    submitted = (await client.post(f"/demandhub-api/demand/{draft['id']}/submit", headers=auth_headers,
                                   json={"expectedRevision": draft["revision"]})).json()["data"]
    assert submitted["status"] == "SUBMITTED" and submitted["changeLogs"] == []
    detail = (await client.get(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers)).json()["data"]
    demand = detail["demand"]
    assert demand["changeLogs"] == []
    # 五区要素完整返回（A/C/D 分组）+ quality + fieldSources
    assert demand["elements"]["A"]["techSubtype"] == "DATA_RPT"
    assert demand["elements"]["C"]["useScenario"].startswith("客户经理每天晨会前")
    assert demand["elements"]["D"]["acceptanceCriteria"] == "连续7天与核心系统对账误差为0"
    assert demand["quality"] and demand["fieldSources"]["elements.C.useScenario"] == "user"
    assert detail["standard"]["type"] == "TECH"


async def test_update_then_detail_change_logs_grow(client, auth_headers):
    draft = await create_full(client, auth_headers, "p3-grow")
    updated = (await client.put(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers,
                                json={"expectedRevision": draft["revision"], "title": "持仓自动汇总报表",
                                      "elements": {"C": {"useScenario": "客户经理每周一晨会前查询各渠道持仓并整理材料"}}})).json()["data"]
    assert updated["revision"] == draft["revision"] + 1
    keys = [log["fieldKey"] for log in updated["changeLogs"]]
    assert keys == ["title", "elements.C.useScenario"]
    assert updated["changeLogs"][0]["oldValue"] == "持仓自动报表" and updated["changeLogs"][0]["source"] == "user"
    detail = (await client.get(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers)).json()["data"]
    assert [log["fieldKey"] for log in detail["demand"]["changeLogs"]] == keys
    # 再次修改 → 留痕增行，旧值正确
    again = (await client.put(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers,
                              json={"expectedRevision": updated["revision"], "title": "持仓自动报表"})).json()["data"]
    assert len(again["changeLogs"]) == 3
    assert again["changeLogs"][-1]["oldValue"] == "持仓自动汇总报表" and again["changeLogs"][-1]["newValue"] == "持仓自动报表"


async def test_overview_update_persisted_but_not_logged(client, auth_headers):
    # ext.overview 是 AI 派生摘要：RESERVED_EXT_KEYS 保留可写，但变更留痕排除（避免每轮重写刷噪音）
    draft = await create_full(client, auth_headers, "p3-overview")
    updated = (await client.put(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers,
                                json={"expectedRevision": draft["revision"],
                                      "ext": {"overview": {"problem": "手工拼表每次40分钟｜现有统计方式低效"}}})).json()["data"]
    assert updated["ext"]["overview"]["problem"].startswith("手工拼表")
    assert all(log["fieldKey"] != "ext.overview" for log in updated["changeLogs"])


async def test_legacy_ext_write_maps_to_elements(client, auth_headers):
    # P4 前 H5 六要素手填兼容：旧 ext 字段映射进五区，显式 elements 同 key 优先
    draft = (await client.post("/demandhub-api/demand", headers=auth_headers,
                               json={"clientRequestId": "p3-legacy", "title": "渠道日报", "demandTypeCode": "TECH",
                                     "content": "客户经理每天需要查看渠道业务日报汇总",
                                     "ext": {"techSubtype": "DATA_RPT", "businessScenario": "客户经理每天晨会前查看渠道日报汇总"}})).json()["data"]
    assert draft["elements"]["A"]["techSubtype"] == "DATA_RPT"
    assert draft["elements"]["C"]["useScenario"] == "客户经理每天晨会前查看渠道日报汇总"
    assert draft["ext"]["techSubtype"] == "DATA_RPT"  # ext 保留兼容副本（概念模型 §6.2）
    assert draft["fieldSources"]["elements.A.techSubtype"] == "user"
    updated = (await client.put(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers,
                                json={"expectedRevision": draft["revision"],
                                      "ext": {"techSubtype": "DATA_RPT", "acceptanceCriteria": "连续7天对账误差为0"},
                                      "elements": {"A": {"techSubtype": "SYS_INT"}}})).json()["data"]
    assert updated["elements"]["A"]["techSubtype"] == "SYS_INT"  # 显式 elements 优先于 legacy 映射
    assert updated["elements"]["D"]["acceptanceCriteria"] == "连续7天对账误差为0"
    keys = [log["fieldKey"] for log in updated["changeLogs"]]
    assert "elements.A.techSubtype" in keys and "elements.D.acceptanceCriteria" in keys


async def test_export_markdown_zones_source_text_first_and_e_zone(client, auth_headers):
    draft = await create_full(client, auth_headers, "p3-export")
    await client.put(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers,
                     json={"expectedRevision": draft["revision"], "title": "持仓自动汇总报表"})
    response = await client.get(f"/demandhub-api/demand/{draft['id']}/export.md", headers=auth_headers)
    assert response.headers["content-type"].startswith("text/markdown")
    markdown = response.text
    # A8 原文置首（位于基本信息之前）
    assert markdown.index("## 原始提报文本（A8）") < markdown.index("## 基本信息")
    # A/C/D 分区排版（B 区未填不出空段）
    for section in ("## A 区 · 公共要素", "## C 区 · 用户需求要素", "## D 区 · 功能需求要素"):
        assert section in markdown
    # E 区状态附注：状态/修改次数/字段来源/变更留痕
    assert "## E 区 · 状态信息" in markdown and "修改次数：1" in markdown
    assert "### 字段来源" in markdown and "elements.C.useScenario" in markdown
    assert "### 变更留痕" in markdown and "持仓自动报表" in markdown  # 留痕旧值


async def test_sse_structured_carries_type_recognition_and_granularity_hint(client, auth_headers):
    draft = (await client.post("/demandhub-api/demand", headers=auth_headers,
                               json={"clientRequestId": "p3-sse", "title": "持仓报表", "demandTypeCode": "TECH",
                                     "content": "客户经理每天晨会前查看各机构持仓"})).json()["data"]
    session = (await client.post("/demandhub-api/agent/session", headers=auth_headers,
                                 json={"demandId": draft["id"], "scene": "SUBMIT_GUIDE"})).json()["data"]
    fake = FakeArk({"structured": {"elements": {"A": {"techSubtype": "DATA_RPT"}}}, "elements": [],
                    "typeSignals": {"business": {"confidence": 0.9, "evidence": "部门年度考核指标"},
                                    "user": {"confidence": 0.2, "evidence": ""}, "function": {"confidence": 0.1, "evidence": ""}}})
    client._transport.app.dependency_overrides[get_llm_client] = lambda: fake
    req = {"demandId": draft["id"], "sessionId": session["id"], "requestId": "p3-sse-1",
           "revision": draft["revision"], "message": "提升部门年度考核指标完成率"}
    response = await client.post("/demandhub-api/agent/guide/chat/stream", headers=auth_headers, json=req)
    frames = [frame for frame in response.text.strip().split("\n\n") if frame.startswith("event: structured")]
    assert len(frames) == 1
    payload = json.loads(frames[0].split("data:", 1)[1])
    # SSE structured 载荷：五区结构 + 判型卡片 + 粒度提示（对齐 H5 原型交互）
    assert payload["structured"]["elements"]["A"]["techSubtype"] == "DATA_RPT"
    assert payload["typeRecognition"]["business"] == 0.9
    assert payload["typeRecognition"]["evidence"]["business"] == "部门年度考核指标"
    assert payload["granularityHint"]["level"] == "too_broad"  # "提升"命中且 D 区未填
    assert payload["granularityHint"]["converge"] == "可验证、可追踪、可独立受理"
    assert payload["impactHints"] == []
