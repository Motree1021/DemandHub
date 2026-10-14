"""排查：刘泉在 dev/test 库的 dh_user 记录（wecom_userid 是否为空、有几条）。"""
import pymysql

for db_name in ("demandhub", "demandhub_test"):
    conn = pymysql.connect(host="127.0.0.1", port=3307, user="root",
                           password="Motree_1021", database=db_name, charset="utf8mb4")
    cur = conn.cursor()
    cur.execute("SELECT id, name, wecom_userid, login_account, channel, status, role, created_at, last_login_at "
                "FROM dh_user WHERE name LIKE %s ORDER BY id", ("%刘泉%",))
    rows = cur.fetchall()
    print(f"[{db_name}] {len(rows)} 条")
    for r in rows:
        print("  id=%s name=%s wecom=%r login_account=%r channel=%s status=%s role=%s created=%s last_login=%s" % r)
    cur.execute("SELECT COUNT(*) FROM dh_user WHERE wecom_userid = ''")
    print(f"  全表 wecom_userid 为空串的共 {cur.fetchone()[0]} 条")
    conn.close()
