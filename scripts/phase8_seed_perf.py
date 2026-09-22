# -*- coding: utf-8 -*-
"""阶段8 性能测试数据准备：灌入 1 万条需求（幂等：已有 ≥10000 条 PERF 数据则跳过）。"""
import random
import pymysql

conn = pymysql.connect(host='localhost', port=3307, user='root', password='demandhub123',
                       database='demandhub', charset='utf8mb4', autocommit=True)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM demand WHERE title LIKE 'PERF-%'")
existing = cur.fetchone()[0]
TARGET = 10000
if existing >= TARGET:
    print(f"已有 {existing} 条 PERF 数据，跳过")
    raise SystemExit(0)

TYPES = ["TECH", "MATL", "TRAIN"]
ORG_OF = {"TECH": 111, "MATL": 121, "TRAIN": 131}
STATUSES = ["SUBMITTED", "TRIAGE", "ANALYZING", "SOLUTION_REVIEW", "CONFIRMED",
            "IN_PROGRESS", "ACCEPTANCE", "DONE", "CLOSED", "NEED_INFO"]
URGENCY = ["NORMAL", "NORMAL", "NORMAL", "URGENT", "CRITICAL"]
SUBMITTERS = [1006, 1007]
HANDLERS = {111: 1007, 121: 1004, 131: 1005}

need = TARGET - existing
print(f"灌入 {need} 条 PERF 数据...")
batch = []
base_seq = existing
for i in range(need):
    n = base_seq + i + 1
    t = TYPES[i % 3]
    org = ORG_OF[t]
    status = STATUSES[i % len(STATUSES)]
    submitter = SUBMITTERS[i % 2]
    handler = HANDLERS[org] if status in ("ANALYZING", "SOLUTION_REVIEW", "CONFIRMED",
                                          "IN_PROGRESS", "ACCEPTANCE", "DONE") else None
    day_offset = i % 90
    demand_no = f"{t}-20260{(6 + (day_offset // 90))}-PERF{n:05d}"[:40]
    demand_no = f"{t}-PERF-{n:05d}"
    batch.append((
        demand_no, f"PERF-压测需求-{n}", t, f"性能测试内容 {n}", URGENCY[i % 5], status,
        0, submitter, 141, "创金合信零售业务线/零售一线营业部/营业部一组", "WEB",
        org, handler,
        f"2026-09-{day_offset % 28 + 1:02d} 09:00:00",
        1006, 1006,
    ))
    if len(batch) >= 500:
        cur.executemany(
            "INSERT INTO demand(demand_no,title,demand_type_code,content,urgency,status,on_hold,"
            "submitter_id,submitter_org_id,submitter_org_snapshot,channel,assignee_org_id,assignee_user_id,"
            "submitted_at,created_by,updated_by) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", batch)
        batch.clear()
        print(f"  {n}/{need}")
if batch:
    cur.executemany(
        "INSERT INTO demand(demand_no,title,demand_type_code,content,urgency,status,on_hold,"
        "submitter_id,submitter_org_id,submitter_org_snapshot,channel,assignee_org_id,assignee_user_id,"
        "submitted_at,created_by,updated_by) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", batch)
cur.execute("SELECT COUNT(*) FROM demand")
print("总需求数:", cur.fetchone()[0])
cur.execute("ANALYZE TABLE demand")
print("ANALYZE 完成")
