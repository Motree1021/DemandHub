# -*- coding: utf-8 -*-
"""阶段8 性能压测（检查点3 / NFR-01/02）：1 万条数据量下
- 列表页 P95 ≤ 2s（EXECUTIVE 全线口径最宽、HANDLER 本组织、带筛选/排序）
- 详情页 P95 ≤ 1.5s
"""
import json
import statistics
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8080/api"
PASS, FAIL = [], []


def report(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def login(user_id):
    r = urllib.request.Request(BASE + f"/system/auth/callback?code=mock-{user_id}")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())["data"]["accessToken"]


def timed_get(path, token):
    r = urllib.request.Request(BASE + path)
    r.add_header("Authorization", f"Bearer {token}")
    t0 = time.perf_counter()
    with urllib.request.urlopen(r, timeout=60) as resp:
        body = json.loads(resp.read().decode())
    return (time.perf_counter() - t0) * 1000, body


def bench(name, path, token, n=30, warm=3):
    for _ in range(warm):
        timed_get(path, token)
    lat = []
    for _ in range(n):
        ms, _ = timed_get(path, token)
        lat.append(ms)
    lat.sort()
    p50 = lat[len(lat) // 2]
    p95 = lat[int(len(lat) * 0.95) - 1]
    p99 = lat[-1]
    return p50, p95, p99


def main():
    exec_t = login("u_exec_001")
    handler_t = login("u_handler_a1")

    print("== 列表页（EXECUTIVE 全线 1 万+ 行）==")
    p50, p95, p99 = bench("list", "/demand/demand/page?current=1&size=20", exec_t)
    report("列表页 P95 ≤ 2000ms", p95 <= 2000, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")

    p50, p95, p99 = bench("list-filter", "/demand/demand/page?current=1&size=20&demandTypeCode=TECH&status=IN_PROGRESS", exec_t)
    report("列表页(类型+状态筛选) P95 ≤ 2000ms", p95 <= 2000, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")

    p50, p95, p99 = bench("list-sort", "/demand/demand/page?current=1&size=20&submittedOrder=asc", exec_t)
    report("列表页(提交时间排序) P95 ≤ 2000ms", p95 <= 2000, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")

    p50, p95, p99 = bench("list-deep", "/demand/demand/page?current=250&size=20", exec_t)
    report("列表页(深分页第250页) P95 ≤ 2000ms", p95 <= 2000, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")

    print("\n== 列表页（HANDLER 本组织）==")
    p50, p95, p99 = bench("list-handler", "/demand/demand/page?current=1&size=20", handler_t)
    report("处理人列表页 P95 ≤ 2000ms", p95 <= 2000, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")

    print("\n== 待受理队列 / 需求池 ==")
    p50, p95, p99 = bench("queue", "/demand/triage/queue?current=1&size=20", exec_t)
    report("待受理队列 P95 ≤ 2000ms", p95 <= 2000, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")
    p50, p95, p99 = bench("pool", "/demand/triage/pool?current=1&size=20", handler_t)
    report("需求池 P95 ≤ 2000ms", p95 <= 2000, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")

    print("\n== 详情页 ==")
    # 取一个真实 id
    _, page = timed_get("/demand/demand/page?current=1&size=1", exec_t)
    did = page["data"]["records"][0]["id"]
    p50, p95, p99 = bench("detail", f"/demand/demand/{did}", exec_t)
    report("详情页 P95 ≤ 1500ms", p95 <= 1500, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")
    p50, p95, p99 = bench("transitions", f"/demand/demand/{did}/transitions", exec_t)
    report("流转日志 P95 ≤ 1500ms", p95 <= 1500, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")

    print("\n== 看板（预聚合口径）==")
    p50, p95, p99 = bench("dashboard", "/demand/dashboard/manager?range=month", exec_t)
    report("管理者看板 P95 ≤ 2000ms", p95 <= 2000, f"P50={p50:.0f} P95={p95:.0f} P99={p99:.0f}")

    print("\n" + "=" * 50)
    print(f"压测结果: PASS={len(PASS)} FAIL={len(FAIL)}")
    for f in FAIL:
        print(" -", f)
    raise SystemExit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
