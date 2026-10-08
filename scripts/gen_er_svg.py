# -*- coding: utf-8 -*-
"""生成《科技需求收集智能体 · E-R 实体图》SVG（宽扁横幅布局，一屏完整显示）。
与设计文档 §3.3 Mermaid 一致；字段精简、行高压缩，总宽 1180、总高约 470。"""
import xml.etree.ElementTree as ET

W, H = 1180, 470
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

def link(x1, y1, x2, y2, label, dashed=False, lx=None, ly=None, color="#64748b"):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    out = [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.3"{dash}/>']
    if lx is not None and ly is not None:
        out.append(text(lx, ly, label, 11.5, 600, "#334155", "middle"))
    return "\n".join(out)

def arrow_marker(uid, color):
    return (f'<marker id="{uid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M0,1 L9,5 L0,9 z" fill="{color}"/></marker>')

svg = []
svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">')
svg.append(arrow_marker("arw", "#475569"))

# ---------- 实体定义（字段精简，行高 18） ----------
# 左列 x=30 ｜ 中列 x=430 ｜ 右列 x=850 ｜ 框宽 300 / 350 / 300
entity("dh_user · 提报人", 30, 26, 300, [
    ("PK", "id", ""),
    ("UK", "wecom_userid", "企微唯一"),
    ("", "channel / dept_name", ""),
], "#dcfce7", "#16a34a", "#f0fdf4")

entity("prompt_version · 标准快照", 30, 132, 300, [
    ("PK", "id", ""),
    ("", "code / version", "标准编码/版本"),
    ("UK", "content_hash", "快照指纹"),
    ("", "snapshot JSON", "标准快照"),
], "#dbeafe", "#2563eb", "#eff6ff")

entity("demand_no_seq · 编号流水", 30, 258, 300, [
    ("PK", "biz_date / type_code", "日期+类型"),
    ("", "seq", "当日序号"),
], "#e2e8f0", "#64748b", "#f8fafc")

entity("demand · 需求/草稿（核心）", 430, 26, 350, [
    ("PK", "id", ""),
    ("UK", "demand_no", "TECH-…-NNN"),
    ("", "title / type / subtype", "A1/A2/A3"),
    ("", "content TEXT", "A8 原文保真"),
    ("", "urgency / expect_delivery_at", "A6/A7"),
    ("NEW", "elements JSON", "A/B/C/D 区"),
    ("", "quality / field_sources JSON", "E1/E5"),
    ("", "revision INT", "E6 乐观锁"),
    ("FK", "submitter_id / channel", ""),
    ("FK", "session_id · standard_version_id", "会话/标准"),
    ("NEW", "split_from_id FK · split_group_id", "实例切分"),
], "#bfdbfe", "#1d4ed8", "#ffffff")

entity("demand_change_log · 变更留痕（新增）", 430, 290, 350, [
    ("PK", "id", ""),
    ("FK", "demand_id", "归属需求"),
    ("", "field_key", "要素 key B1/D8"),
    ("", "old / new_value JSON", "修改前后"),
    ("", "source · changed_by FK", "来源/操作人"),
], "#fef3c7", "#d97706", "#fffbeb")

entity("agent_session · 启发会话", 850, 26, 300, [
    ("PK", "id", ""),
    ("UK", "session_no", "会话号"),
    ("FK", "demand_id", "每草稿唯一"),
    ("", "scene / asked_target", "场景/追问目标"),
], "#f1f5f9", "#64748b", "#ffffff")

entity("agent_message · 对话消息", 850, 152, 300, [
    ("PK", "id", ""),
    ("FK", "session_id", "所属会话"),
    ("", "role / content", "角色/内容"),
    ("", "structured_payload JSON", "模型结构化输出"),
    ("", "request_id", "幂等键"),
], "#f1f5f9", "#64748b", "#ffffff")

# ---------- 关系连线 ----------
ln = []
ln.append(link(330, 68, 430, 66, "1 — N 提报（submitter_id）", lx=380, ly=56))
ln.append(link(330, 168, 430, 150, "1 — N 判质快照（standard_version_id）", lx=380, ly=178))
ln.append(link(330, 284, 430, 226, "逻辑：发放编号（无外键）", dashed=True, lx=380, ly=262, color="#94a3b8"))
ln.append(link(780, 66, 850, 58, "1 — 1 唯一会话（session_id）", lx=815, ly=48))
ln.append(link(1000, 128, 1000, 152, "1 — N 对话与追问（session_id）", lx=1040, ly=142))
ln.append(link(605, 244, 605, 290, "1 — N 变更留痕（demand_id）", lx=685, ly=270))
svg.append(f'<path d="M 780 190 C 910 200, 900 232, 780 224" fill="none" stroke="#7c3aed" stroke-width="1.3" marker-end="url(#arw)"/>')
svg.append(text(880, 216, "实例切分 split_from_id（自引用）", 11.5, 600, "#7c3aed", "middle"))
for line in ln:
    svg.append(line)

# ---------- 图例与注脚 ----------
svg.append(rect(930, 330, 224, 116, "#ffffff", "#cbd5e1", 1))
svg.append(text(944, 350, "图例", 12, 700))
svg.append(text(944, 371, "─ 实线：外键关联", 11.5))
svg.append(text(944, 391, "┄ 虚线：逻辑关系（无外键）", 11.5, 400, "#334155"))
svg.append(text(944, 411, "▸ 紫线：自引用（实例切分）", 11.5, 400, "#7c3aed"))
svg.append(text(944, 431, "NEW：本期新增列/表", 11.5, 400, "#1d4ed8"))

svg.append(text(30, H - 14, "示意：与设计文档 §3.3 Mermaid 图一致；字段级定义见 §4–§5。", 11, 400, "#94a3b8"))

svg.append("</svg>")
out = "\n".join(svg)
ET.fromstring(out)
with open(r"C:\Users\liuqu\Desktop\Projects\DemandHub\DemandHub_科技需求收集智能体_ER图.svg", "w", encoding="utf-8") as f:
    f.write(out)
print("SVG 生成并校验通过，尺寸 %dx%d" % (W, H))
