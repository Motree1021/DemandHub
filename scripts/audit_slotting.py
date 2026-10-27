#!/usr/bin/env python3
"""归槽质量抽检（2026-10-26 拍板）：抽取最近真实会话里模型的槽位归位结果，供人工抽检。

用法（仓库根目录，用 server 虚拟环境运行）：
    server/.venv/Scripts/python scripts/audit_slotting.py                  # 最近 7 天 50 条
    server/.venv/Scripts/python scripts/audit_slotting.py --days 3 --limit 100
    server/.venv/Scripts/python scripts/audit_slotting.py --only-flagged   # 只看筛查提示项
    server/.venv/Scripts/python scripts/audit_slotting.py --demand-id 40   # 只看某条需求

连接取数顺序：--db-url > 环境变量 DEMANDHUB_DATABASE_URL > server/.env 同名配置。只读查询。
「待查」只是筛查提示（建议方案命中组织受益表述时分两种：B1/B3 为空疑似组织价值误入 D9；
B1/B3 已有值疑似一事实两槽），是否误归槽以人工核对原话为准。
确认是踩坑句式后的登记动作：脱敏登记为 server/tests/eval/cases/ 评测用例（pytest -m eval 跑
真实模型回归），并把新一类句式补进 submit_guide.md 对应规则的示范/反例——只改提示词，
不把关键词下沉规则层（模型做语义、规则做决策的主线不变）。
"""
import argparse
import json
import os
import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from app.config import parse_database_url

# 组织受益筛查词：仅用于抽检提示排序，不是业务规则，不参与任何线上判定
ORG_HINTS = ("复用", "赋能", "推广", "全行", "各家银行", "其他银行", "跨机构", "全集团")


def load_database_url(args):
    if args.db_url:
        return args.db_url
    url = os.environ.get("DEMANDHUB_DATABASE_URL")
    if url:
        return url
    env_file = Path(__file__).resolve().parent.parent / "server" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEMANDHUB_DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("缺少数据库连接：请设 DEMANDHUB_DATABASE_URL 或 --db-url")


def fetch_rows(conn, args):
    sql = """
        SELECT m.id, m.created_at, m.session_id, s.demand_id, m.prompt_version_id, m.model,
               u.content AS user_text, m.structured_payload
        FROM agent_message m
        JOIN agent_session s ON s.id = m.session_id
        LEFT JOIN agent_message u
               ON u.session_id = m.session_id AND u.request_id = m.request_id AND u.role = 'USER'
        WHERE m.role = 'ASSISTANT' AND m.structured_payload IS NOT NULL
          AND m.created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
    """
    params = [args.days]
    if args.demand_id:
        sql += " AND s.demand_id = %s"
        params.append(args.demand_id)
    sql += " ORDER BY m.id DESC LIMIT %s"
    params.append(args.limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def clip(value, width=48):
    text = " ".join(str(value).split())
    return text[:width] + ("…" if len(text) > width else "")


def zone_values(elements, zone):
    values = elements.get(zone)
    if not isinstance(values, dict):
        return {}
    return {key: value for key, value in values.items() if value not in (None, "", [])}


def flag_of(slots):
    """筛查提示：建议方案（D9）命中组织受益表述时分两种——B1/B3 为空疑似组织价值误入 D9
    （张征模式）；B1/B3 已有值疑似一事实两槽（组织受益表述同时占 B 区与建议方案）。"""
    d9 = slots.get("D", {}).get("proposedSolution")
    if not d9 or not any(hint in str(d9) for hint in ORG_HINTS):
        return None
    if slots.get("B", {}).get("businessGoal") or slots.get("B", {}).get("businessValue"):
        return "疑似一事实两槽（组织受益表述同时占 B 区与建议方案）"
    return "疑似组织价值误入建议方案"


def main():
    parser = argparse.ArgumentParser(description="归槽质量抽检：真实会话模型输出的槽位归位人工抽检")
    parser.add_argument("--days", type=int, default=7, help="回看天数，默认 7")
    parser.add_argument("--limit", type=int, default=50, help="最多抽取条数，默认 50")
    parser.add_argument("--demand-id", type=int, default=None, help="只看某条需求")
    parser.add_argument("--only-flagged", action="store_true", help="只展示筛查提示项")
    parser.add_argument("--db-url", default=None, help="数据库连接 URL（缺省读环境变量/.env）")
    args = parser.parse_args()

    url = parse_database_url(load_database_url(args), "mysql+pymysql")
    conn = pymysql.connect(host=url.host, port=url.port or 3306, user=url.username,
                           password=url.password, database=url.database, charset="utf8mb4")
    total = flagged = shown = 0
    try:
        rows = fetch_rows(conn, args)
        total = len(rows)
        for row in rows:
            msg_id, created_at, session_id, demand_id, version_id, model, user_text, raw = row
            payload = raw if isinstance(raw, dict) else json.loads(raw)
            structured = payload.get("structured")
            elements = (structured.get("elements") if isinstance(structured, dict) else None) or {}
            slots = {zone: zone_values(elements, zone) for zone in ("A", "B", "C", "D")}
            flag = flag_of(slots)
            flagged += bool(flag)
            if args.only_flagged and not flag:
                continue
            shown += 1
            intent, mode = payload.get("intent"), payload.get("modeSignal")
            intent = intent.get("kind", "-") if isinstance(intent, dict) else (intent or "-")
            level = mode.get("level", "-") if isinstance(mode, dict) else "-"
            print(f"#{msg_id} {created_at} 会话{session_id} 需求{demand_id} "
                  f"prompt版本{version_id or '-'} {model or ''}")
            print(f"  用户: {clip(user_text or '(未配对到用户消息)', 120)}")
            for zone in ("A", "B", "C", "D"):
                for key, value in slots[zone].items():
                    print(f"  {zone}.{key} = {clip(value)}")
            print(f"  意图: {intent}  轻重: {level}" + (f"  [待查] {flag}" if flag else ""))
            print()
    finally:
        conn.close()
    print(f"--- 扫描 {total} 条，展示 {shown} 条，筛查提示 {flagged} 条 ---")


if __name__ == "__main__":
    main()
