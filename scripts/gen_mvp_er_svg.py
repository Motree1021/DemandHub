# -*- coding: utf-8 -*-
"""生成《科技需求收集智能体 · MVP 现状 ER 图》SVG（宽扁横幅，一屏完整显示）。
依据 server/app/db/models.py 现行 6 表：dh_user / prompt_version / demand /
demand_no_seq / agent_session / agent_message。现状：demand 尚无 elements、split_* 等设计列。"""
import sys
import xml.etree.ElementTree as ET

W, H = 1180, 610
FONT = "'Microsoft YaHei','PingFang SC',sans-serif"

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def rect(x, y, w, h, fill, stroke, sw=1.5, rx=9):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'

def text(x, y, s, size=12.5, weight=400, fill="#0f172a", anchor="start"):
    return f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{esc(s)}</text>'

def entity(name, x, y, w, fields, head_fill, head_stroke, body_fill):
    line_h, head_h = 18, 29
    h = head_h + len(fields) * line_h + 7
    out = [rect(x, y, w, h, body_fill, head_stroke, 1.5)]
    out.append(rect(x, y, w, head_h, head_fill, head_stroke, 1.5))
    out.append(text(x + 11, y + 20, name, 13, 700))
    yy = y + head_h + 13
    for ftype, fname, note in fields:
        tag = f'<tspan fill="#1d4ed8" font-weight="700">{esc(ftype)}</tspan>'
        nm = f'<tspan fill="#0f172a">{esc(fname)}</tspan>'
        nt = f'<tspan fill="#64748b" font-size="10.5">{esc("  " + note) if note else ""}</tspan>'
        out.append(f'<text x="{x + 11}" y="{yy}" font-family="{FONT}" font-size="11.5">{tag}{nm}{nt}</text>')
        yy += line_h
    return "\n".join(out), (x, y, w, h)

def link(x1, y1, x2, y2, label, dashed=False, lx=None, ly=None, color="#64748b", color2=None):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    out = [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color2 or color}" stroke-width="1.3"{dash}/>']
    if lx is not None and ly is not None:
        out.append(text(lx, ly, label, 11.5, 600, "#334155", "middle"))
    return "\n".join(out)

svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">')

# ---------- 实体（字段忠实 models.py，精简展示） ----------
# 左列 x=30 w=300 ｜ 中列 x=370 w=360 ｜ 右列 x=790 w=350
entity("dh_user · 渠道回源用户", 30, 26, 300, [
    ("PK", "id", ""),
    ("UK", "wecom_userid", "企微唯一"),
    ("", "name", ""),
    ("", "phone / email", ""),
    ("", "employee_no", ""),
    ("", "dept_id / dept_name", ""),
    ("", "dept_path", ""),
    ("", "channel", "CHUANGJIN_LS"),
    ("", "status / last_login_at", ""),
], "#dcfce7", "#16a34a", "#f0fdf4")

entity("demand_no_seq · 编号流水", 30, 260, 300, [
    ("PK", "biz_date", "业务日期"),
    ("PK", "type_code", "类型"),
    ("", "seq", "当日序号"),
], "#e2e8f0", "#64748b", "#f8fafc")

entity("demand · 草稿与正式需求（核心）", 370, 26, 360, [
    ("PK", "id", ""),
    ("UK", "demand_no", "TECH-YYYYMMDD-NNN"),
    ("", "title", ""),
    ("", "demand_type_code / subtype_code", "需求/子类型"),
    ("", "content TEXT", "A8 原始提报文本"),
    ("", "urgency / expect_delivery_at", ""),
    ("", "ext JSON", "扩展位（现空）"),
    ("", "quality JSON / field_sources JSON", "判质/来源留痕"),
    ("", "revision INT", "乐观锁"),
    ("", "client_request_id / create_request_hash", "幂等"),
    ("FK", "standard_version_id → prompt_version", ""),
    ("", "quality_content_hash", ""),
    ("", "status", "DRAFT/SUBMITTED…"),
    ("FK", "submitter_id → dh_user", ""),
    ("", "submitter_name / submitter_dept", ""),
    ("", "channel / session_id", "session 逻辑 1:1"),
    ("", "submitted_at / closed_at / close_reason", ""),
], "#bfdbfe", "#1d4ed8", "#ffffff")

entity("agent_session · 启发会话", 370, 402, 360, [
    ("PK", "id", ""),
    ("UK", "session_no", "会话号"),
    ("FK", "user_id → dh_user", ""),
    ("", "scene", "SUBMIT_GUIDE"),
    ("FK", "demand_id → demand", "每草稿唯一"),
    ("", "title / status / asked_target", ""),
], "#f1f5f9", "#64748b", "#ffffff")

entity("prompt_version · 标准快照", 790, 26, 350, [
    ("PK", "id", ""),
    ("", "code / version", "标准编码/版本"),
    ("UK", "content_hash", "快照指纹"),
    ("", "snapshot JSON", "不可变快照"),
    ("", "created_at", ""),
], "#dbeafe", "#2563eb", "#eff6ff")

entity("agent_message · Agent 消息", 790, 402, 350, [
    ("PK", "id", ""),
    ("FK", "session_id → agent_session", ""),
    ("", "role / content TEXT", "角色/内容"),
    ("", "structured_payload JSON", "模型结构化输出"),
    ("", "request_id / request_hash", "幂等键"),
    ("FK", "prompt_version_id → prompt_version", ""),
    ("", "model / tokens / latency_ms", "调用元信息"),
], "#f1f5f9", "#64748b", "#ffffff")

# ---------- 关系连线 ----------
ln = []
ln.append(link(330, 66, 370, 76, "1 — N 提报（submitter_id）", lx=350, ly=54))
ln.append(link(330, 132, 370, 292, "1 — N 会话（user_id）", lx=350, ly=210))
ln.append(link(330, 282, 370, 330, "逻辑：发放编号（无外键）", dashed=True, lx=350, ly=312, color="#94a3b8"))
ln.append(link(730, 62, 790, 62, "N — 1 判质快照（standard_version_id）", lx=760, ly=50))
ln.append(link(1000, 170, 1000, 402, "N — 1 快照（prompt_version_id）", lx=1040, ly=286))
ln.append(link(550, 368, 550, 402, "1 — 1 唯一会话（demand_id UNIQUE）", lx=620, ly=388))
ln.append(link(730, 486, 790, 486, "1 — N 对话消息（session_id）", lx=760, ly=476))
ln.append(link(730, 130, 790, 130, "逻辑 1:1（session_id 无外键）", dashed=True, lx=760, ly=118, color="#94a3b8"))
for line in ln:
    svg.append(line)

# ---------- 图例与注脚 ----------
svg.append(rect(930, 210, 224, 118, "#ffffff", "#cbd5e1", 1))
svg.append(text(944, 230, "图例", 12, 700))
svg.append(text(944, 251, "─ 实线：外键关联", 11.5))
svg.append(text(944, 271, "┄ 虚线：逻辑关系（无外键）", 11.5, 400, "#334155"))
svg.append(text(944, 291, "UK：唯一约束", 11.5, 400, "#334155"))
svg.append(text(944, 311, "现状 6 表：无 elements / split_*", 11.5, 400, "#d97706"))

svg.append(text(30, H - 14, "依据 server/app/db/models.py（SQLAlchemy 现行模型）；未包含设计文档 V1.1 新增列（elements、split_from_id、demand_change_log 等）。", 11, 400, "#94a3b8"))

svg.append("</svg>")
out = "\n".join(svg)
ET.fromstring(out)
svg_path = r"C:\Users\liuqu\Desktop\Projects\DemandHub\DemandHub_科技需求收集智能体_MVP现状ER图.svg"
with open(svg_path, "w", encoding="utf-8") as f:
    f.write(out)
print("SVG 生成并校验通过，尺寸 %dx%d" % (W, H))
