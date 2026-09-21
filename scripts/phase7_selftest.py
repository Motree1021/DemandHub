# -*- coding: utf-8 -*-
"""阶段7端到端自测：M6 看板报表 + M9 AI Agent（8 条检查点）"""
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8080/api"
MYSQL = {"host": "localhost", "port": 3307, "user": "root", "password": "demandhub123", "db": "demandhub"}

PASS, FAIL = [], []


def report(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def req(method, path, token=None, body=None, raw=False):
    url = BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read()
            if raw:
                return resp.status, payload
            return resp.status, json.loads(payload.decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"raw": payload}


def login(user_id):
    status, body = req("GET", f"/system/auth/callback?code=mock-{user_id}")
    assert status == 200 and body["code"] == 0, f"login {user_id} failed: {body}"
    return body["data"]["accessToken"]


def main():
    print("== 登录 ==")
    exec_t = login("u_exec_001")
    mgr_t = login("u_mgr_tech")
    admin_t = login("u_admin_001")
    reporter_t = login("u_reporter_1")
    handler_t = login("u_handler_a1")

    # ---------- 检查点 3：手动触发预聚合，demand_stat_daily 更新 ----------
    print("\n== CP3 预聚合 ==")
    status, body = req("POST", "/demand/dashboard/stat-refresh", exec_t)
    ok = status == 200 and body["code"] == 0 and body["data"]["affectedRows"] > 0
    report("CP3 手动触发预聚合", ok, f"affectedRows={body.get('data', {}).get('affectedRows')}")

    import pymysql
    conn = pymysql.connect(**MYSQL, charset="utf8mb4", autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), MAX(updated_at) FROM demand_stat_daily WHERE stat_date = CURDATE()")
    row = cur.fetchone()
    report("CP3 demand_stat_daily 当日快照存在", row[0] > 0, f"rows={row[0]} updated_at={row[1]}")

    # ---------- 检查点 1：KPI 与列表页对账 ----------
    print("\n== CP1 KPI 对账 ==")
    status, board = req("GET", "/demand/dashboard/manager?range=month", exec_t)
    assert board["code"] == 0, board
    kpi = board["data"]["kpi"]
    status, page = req("GET", "/demand/demand/page?current=1&size=1", exec_t)
    month_new_list = page["data"]["total"]
    # 列表页默认全量；本月新增口径 = submitted_at 在本月。用 SQL 直接对账更准确
    cur.execute(
        "SELECT COUNT(*) FROM demand WHERE is_deleted = 0 "
        "AND submitted_at >= DATE_FORMAT(CURDATE(), '%Y-%m-01')")
    month_new_sql = cur.fetchone()[0]
    report("CP1 本月新增 KPI = SQL 本月提交数", kpi["monthNew"] == month_new_sql,
           f"kpi={kpi['monthNew']} sql={month_new_sql} (EXECUTIVE 全线口径)")
    cur.execute("SELECT COUNT(*) FROM demand WHERE is_deleted = 0 AND status NOT IN ('DONE','CLOSED')")
    inflight_sql = cur.fetchone()[0]
    report("CP1 在途 KPI = SQL 在途数", kpi["inflight"] == inflight_sql, f"kpi={kpi['inflight']} sql={inflight_sql}")

    # ---------- 检查点 2：趋势/分布/积压数据 ----------
    print("\n== CP2 看板数据结构 ==")
    d = board["data"]
    report("CP2 近12周趋势 12 个桶", len(d["trend"]) == 12, f"buckets={len(d['trend'])}")
    report("CP2 类型分布非空", len(d["typeDistribution"]) > 0, f"types={len(d['typeDistribution'])}")
    report("CP2 组织积压 TopN", len(d["orgBacklog"]) > 0, f"orgs={len(d['orgBacklog'])}")
    sla = d["slaHealth"]
    report("CP2 SLA 健康度分档", sla["normal"] + sla["warn"] + sla["over"] >= 0,
           f"normal={sla['normal']} warn={sla['warn']} over={sla['over']}")
    for r in ("week", "quarter"):
        status, b2 = req("GET", f"/demand/dashboard/manager?range={r}", exec_t)
        report(f"CP2 切换{r}数据联动", b2["code"] == 0 and b2["data"]["kpi"] is not None)

    # 经理看板
    status, org = req("GET", "/demand/dashboard/org", mgr_t)
    report("CP2 经理看板（本组织）", org["code"] == 0 and "pendingAccept" in org["data"],
           f"pending={org['data']['pendingAccept']} pool={org['data']['pool']} processing={org['data']['processing']}")

    # ---------- 检查点 4：报表导出全链路 ----------
    print("\n== CP4 报表导出 ==")
    status, task = req("POST", "/demand/report/export", exec_t, {"reportType": "DEMAND_LIST"})
    assert task["code"] == 0, task
    task_id = task["data"]["id"]
    task_no = task["data"]["taskNo"]
    final = None
    for _ in range(20):
        time.sleep(1)
        status, tasks = req("GET", "/demand/report/tasks", exec_t)
        final = next((t for t in tasks["data"] if t["id"] == task_id), None)
        if final and final["status"] in ("SUCCESS", "FAILED"):
            break
    report("CP4 导出任务完成", final and final["status"] == "SUCCESS",
           f"taskNo={task_no} status={final and final['status']} err={final and final.get('errorMsg')}")
    # 站内信（任务 SUCCESS 与通知写入有毫秒级间隔，重试等待）
    notice_ok = False
    for _ in range(6):
        cur.execute("SELECT COUNT(*) FROM notification WHERE receiver_id = "
                    "(SELECT id FROM demand_user_snapshot WHERE user_id = 'u_exec_001') "
                    "AND template_code = 'REPORT_READY'")
        if cur.fetchone()[0] > 0:
            notice_ok = True
            break
        time.sleep(1)
    report("CP4 站内信「报表已就绪」", notice_ok)
    # 下载
    if final and final["status"] == "SUCCESS":
        status, payload = req("GET", f"/demand/report/download/{task_id}", exec_t, raw=True)
        is_xlsx = status == 200 and payload[:2] == b"PK"
        report("CP4 下载 Excel 成功", is_xlsx, f"bytes={len(payload)}")

    # ---------- 检查点 5：提报启发 Agent ----------
    print("\n== CP5 提报启发 ==")
    status, sess = req("POST", "/agent/session", reporter_t, {"scene": "SUBMIT_GUIDE", "firstMessage": "我想要个数据报表"})
    assert sess["code"] == 0, sess
    sid = sess["data"]["id"]
    status, r1 = req("POST", "/agent/guide/chat", reporter_t, {"sessionId": sid, "message": "我想要个数据报表"})
    report("CP5 第一轮对话（识别类型）", r1["code"] == 0 and r1["data"]["structured"].get("demandTypeCode") == "TECH",
           f"structured={r1['data']['structured']}")
    status, r2 = req("POST", "/agent/guide/chat", reporter_t,
                     {"sessionId": sid, "message": "代销看板增加机构持仓维度"})
    s2 = r2["data"]["structured"]
    report("CP5 第二轮标题抽取", r2["code"] == 0 and bool(s2.get("title")), f"title={s2.get('title')}")
    status, r3 = req("POST", "/agent/guide/chat", reporter_t,
                     {"sessionId": sid, "message": "渠道经理每天要看各机构的持仓规模和变动趋势，目前只能导出 Excel 手工拼，希望看板直接展示并支持下钻", "formContext": s2})
    s3 = r3["data"]
    ready = s3["ready"] and s3["structured"].get("title") and s3["structured"].get("content") and s3["structured"].get("demandTypeCode")
    report("CP5 多轮后字段齐备可回填", ready,
           f"missing={s3['missing']} title={s3['structured'].get('title')} ext={s3['structured'].get('ext')}")

    # ---------- 检查点 6：处理辅助 Agent ----------
    print("\n== CP6 处理辅助 ==")
    # 找一个 ANALYZING 且 handler_a1 可处理的需求；没有则现场造一条走完流程
    cur.execute("SELECT id, demand_no, status FROM demand WHERE is_deleted = 0 AND status = 'ANALYZING' LIMIT 1")
    analyzing = cur.fetchone()
    if not analyzing:
        report("CP6 前置（存在 ANALYZING 需求）", False, "无 ANALYZING 需求，需先造数据")
        demand_id = None
    else:
        demand_id = analyzing[0]
        report("CP6 前置（ANALYZING 需求）", True, f"#{demand_id} {analyzing[1]}")
    if demand_id:
        status, sess2 = req("POST", "/agent/session", handler_t,
                            {"scene": "HANDLE_ASSIST", "demandId": demand_id, "firstMessage": "辅助处理"})
        if sess2["code"] != 0:
            report("CP6 处理辅助会话", False, str(sess2))
        else:
            sid2 = sess2["data"]["id"]
            status, dq = req("POST", "/agent/assist/questions", handler_t, {"sessionId": sid2})
            ok_q = dq["code"] == 0 and dq["data"]["status"] == "PENDING" and len(json.loads(dq["data"]["content"])) >= 3
            report("CP6 调研问题清单草稿", ok_q, f"questions={len(json.loads(dq['data']['content'])) if dq['code']==0 else '-'}")
            status, ds = req("POST", "/agent/assist/solution", handler_t, {"sessionId": sid2})
            ok_s = ds["code"] == 0 and ds["data"]["status"] == "PENDING"
            report("CP6 方案初稿草稿（PENDING）", ok_s)
            # 未确认前 solution 表不应新增
            cur.execute("SELECT COUNT(*) FROM solution WHERE demand_id = %s", (demand_id,))
            before_cnt = cur.fetchone()[0]
            draft_id = ds["data"]["id"]
            # 确认入库
            status, cf = req("POST", f"/agent/assist/drafts/{draft_id}/confirm", handler_t, {})
            cur.execute("SELECT COUNT(*) FROM solution WHERE demand_id = %s", (demand_id,))
            after_cnt = cur.fetchone()[0]
            ok_c = cf["code"] == 0 and cf["data"]["status"] == "CONFIRMED" and after_cnt == before_cnt + 1
            report("CP6 确认后才写入 solution 表", ok_c,
                   f"solution {before_cnt}→{after_cnt} target={cf['data'].get('targetSolutionId') if cf['code']==0 else cf}")
            # 重复确认应失败
            status, cf2 = req("POST", f"/agent/assist/drafts/{draft_id}/confirm", handler_t, {})
            report("CP6 重复确认拦截", cf2["code"] == 1404, f"code={cf2['code']}")

    # ---------- 检查点 7：RAG ----------
    print("\n== CP7 RAG 知识库 ==")
    cur.execute("SELECT id, demand_no FROM demand WHERE is_deleted = 0 AND status = 'DONE' ORDER BY id DESC LIMIT 5")
    dones = cur.fetchall()
    report("CP7 前置（DONE 需求样本）", len(dones) > 0, f"{len(dones)} 条")
    for d_id, d_no in dones:
        req("POST", f"/agent/admin/rag/vectorize/{d_id}", admin_t)
    cur.execute("SELECT COUNT(*) FROM knowledge_doc WHERE status = 'ACTIVE'")
    doc_cnt = cur.fetchone()[0]
    report("CP7 DONE 需求向量化入库", doc_cnt > 0, f"knowledge_doc={doc_cnt}")
    # 找一条非 DONE 需求做相似推荐
    cur.execute("SELECT id FROM demand WHERE is_deleted = 0 AND status != 'DONE' LIMIT 1")
    probe = cur.fetchone()
    if probe and doc_cnt > 0:
        status, sim = req("GET", f"/agent/rag/similar?demandId={probe[0]}&topN=5", handler_t)
        hits = sim["data"] if sim["code"] == 0 else []
        report("CP7 相似需求推荐 TopN", sim["code"] == 0 and len(hits) >= 1,
               f"hits={len(hits)} top={hits[0]['demandNo'] if hits else '-'} score={hits[0]['score'] if hits else '-'}")

    # ---------- 检查点 8：降级 ----------
    print("\n== CP8 降级 ==")
    req("POST", "/agent/admin/llm-switch", admin_t, {"available": False})
    status, r9 = req("POST", "/agent/guide/chat", reporter_t, {"sessionId": sid, "message": "测试降级"})
    report("CP8 大模型关闭 → Agent 返回 1401", r9.get("code") == 1401, f"code={r9.get('code')} msg={r9.get('message')}")
    status, r10 = req("POST", "/agent/assist/questions", handler_t, {"sessionId": sid2 if demand_id else -1})
    report("CP8 处理辅助同样降级", r10.get("code") == 1401, f"code={r10.get('code')}")
    # 主流程不受影响：正常提交需求
    status, sub = req("POST", "/demand/demand/submit", reporter_t, {
        "title": "降级自测-主流程不受影响", "demandTypeCode": "TECH",
        "content": "AI 服务关闭期间手动提交需求，验证主流程正常", "urgency": "NORMAL"})
    ok_main = sub["code"] == 0 and sub["data"]["demandNo"]
    report("CP8 主流程（手动提报）不受影响", ok_main, f"demandNo={sub['data'].get('demandNo') if sub['code']==0 else sub}")
    req("POST", "/agent/admin/llm-switch", admin_t, {"available": True})
    status, r11 = req("POST", "/agent/guide/chat", reporter_t, {"sessionId": sid, "message": "恢复了吗"})
    report("CP8 开关恢复后 Agent 可用", r11["code"] == 0)
    # 清理降级自测数据
    if ok_main:
        new_id = sub["data"]["id"]
        req("POST", f"/demand/demand/{new_id}/withdraw", reporter_t, {"reason": "降级自测清理"})
        cur.execute("DELETE FROM demand WHERE id = %s", (new_id,))
        conn.commit()

    conn.close()
    print(f"\n===== 结果：{len(PASS)} PASS / {len(FAIL)} FAIL =====")
    if FAIL:
        print("失败项：", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    main()
