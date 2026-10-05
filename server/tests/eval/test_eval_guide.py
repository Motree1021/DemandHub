"""真实模型评价抽取/判质；全服务延迟另以实际GuideService测量。"""
import time
from pathlib import Path

import pytest
import yaml

from app.agent.guide import GuideService, build_prompt
from app.agent.llm_client import LlmUnavailable
from app.agent.policy import process
from app.agent.schemas import ElementStatus, GuideChatRequest, parse_model_output
from app.services import demand_service, session_service
from app.standards.rules import set_value

pytestmark = pytest.mark.eval
CASE_DIR = Path(__file__).parent / "cases"
REPORT_PATH = Path(__file__).parent / "report.md"
LATENCY_PATH = Path(__file__).parent / "latency_report.md"


def at(value, path):
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def percentile(values, quantile):
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * quantile))] if values else None


async def test_real_extraction_and_quality_accuracy_at_least_80_percent(real_ark):
    field_total = quality_total = field_hits = quality_hits = 0
    timings, differences, protection_failures = [], [], []
    for path in sorted(CASE_DIR.glob("*.yaml")):
        case = yaml.safe_load(path.read_text())
        history, previous_elements, asked_target, previous_form = [], [], None, {}
        form = case["turns"][0]["form_before"]
        sources = {"demandTypeCode": "default", "urgency": "default"}
        for turn_index, turn in enumerate(case["turns"]):
            expected_fields = turn["expect"].get("structured_contains", {})
            expected_quality = turn["expect"].get("elements_status", {})
            field_total += len(expected_fields)
            quality_total += len(expected_quality)
            for field_path, value in turn.get("user_patch", {}).items():
                set_value(form, field_path, value)
                sources[field_path] = "user"
            messages, _, registry, _ = build_prompt(form, sources, previous_elements, asked_target, history, turn["user"])
            started = time.monotonic()
            try:
                final = None
                async for event in real_ark.stream_json(messages):
                    if event.kind == "final":
                        final = event
                output = parse_model_output(final.raw)
                result = process(output, form, sources, previous_elements, asked_target, previous_form, turn["user"], standards=registry)
                timings.append(time.monotonic() - started)
                real_ark.on_success()
            except Exception as error:
                # 失败纳入分母并记录，不因首个坏case丢掉整份报告。
                if not isinstance(error, LlmUnavailable):
                    real_ark.on_failure()
                differences.append(f"{case['name']} / turn{turn_index + 1}: 失败 {type(error).__name__}")
                continue
            status = {item.key: item.status for item in output.elements}
            for key, expected in expected_fields.items():
                if at(output.structured, key) == expected:
                    field_hits += 1
                else:
                    differences.append(f"{case['name']} / turn{turn_index + 1}: {key} 抽取不符")
            for key, expected in expected_quality.items():
                if status.get(key) == expected:
                    quality_hits += 1
                else:
                    differences.append(f"{case['name']} / turn{turn_index + 1}: {key} 质量{status.get(key)} != {expected}")
            for field_path, expected in turn["expect"].get("final_contains", {}).items():
                if at(result["structured"], field_path) != expected:
                    protection_failures.append(f"{case['name']} / turn{turn_index + 1}: {field_path} 来源保护/合并不符")
            form, sources = result["structured"], result["fieldSources"]
            previous_elements = [ElementStatus.model_validate(e) for e in result["elements"]]
            asked_target, previous_form = result["askedTarget"], result["structured"]
            history += [messages[-1], {"role": "assistant", "content": result["reply"]}]
    field_accuracy = field_hits / field_total if field_total else 0
    quality_accuracy = quality_hits / quality_total if quality_total else 0
    p50, p95 = percentile(timings, .5), percentile(timings, .95)
    REPORT_PATH.write_text("\n".join(["# 方舟真实模型评测", f"endpoint: {real_ark.settings.llm_chat_model}", f"抽取命中率: {field_accuracy:.1%} ({field_hits}/{field_total})", f"判质一致率: {quality_accuracy:.1%} ({quality_hits}/{quality_total})", f"模型抽取与格式/字段校验耗时 P50: {p50}s；P95: {p95}s", "本报告不含保存/SSE，服务可用答复与整轮延迟见latency_report.md。", *differences, *protection_failures]), encoding="utf-8")
    assert field_accuracy >= .8 and quality_accuracy >= .8 and not protection_failures


async def test_real_guide_end_to_end_latency(real_ark, session_factory, user):
    usable, completed, failures = [], [], []
    # 直接运行生产编排和MySQL保存；processing事件不能算首个可用答复。
    for index in range(5):
        async with session_factory() as db:
            async with db.begin():
                demand = await demand_service.create_draft(db, user, {"clientRequestId": f"latency-{index}", "demandTypeCode": "TECH", "fieldSources": {"demandTypeCode": "default"}})
                session = await session_service.create(db, user, "SUBMIT_GUIDE", demand.id)
                req = GuideChatRequest(demandId=demand.id, sessionId=session.id, requestId=f"latency-{index}", revision=demand.revision, message="机构业务部客户经理每天晨会前需要查看各机构持仓的数据报表，8:30前与核心系统对账误差为0，支持导出Excel，20名客户经理每天节省40分钟。")
            started = time.monotonic()
            try:
                async for event in GuideService(db, user, real_ark).stream(req):
                    if event.startswith("event: message"):
                        usable.append(time.monotonic() - started)
                    elif event.startswith("event: done"):
                        completed.append(time.monotonic() - started)
                    elif event.startswith("event: error"):
                        failures.append(f"样本{index}: {event.strip()}")
            except Exception as error:
                failures.append(f"样本{index}: {type(error).__name__}")
    p50, p95 = percentile(usable, .5), percentile(usable, .95)
    total50, total95 = percentile(completed, .5), percentile(completed, .95)
    risk = "延迟需评估endpoint" if (p95 is not None and p95 > 5) or (total95 is not None and total95 > 20) else "按实际样本记录；5样本不足代表生产分布"
    LATENCY_PATH.write_text("\n".join(["# GuideService完整保存/SSE延迟", f"endpoint: {real_ark.settings.llm_chat_model}", f"成功样本: {len(completed)}/5", f"首个可用答复（commit后message）P50/P95: {p50}/{p95}s", f"整轮（completed done）P50/P95: {total50}/{total95}s", risk, *failures]), encoding="utf-8")
    assert len(completed) == 5
