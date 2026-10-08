# -*- coding: utf-8 -*-
"""Mermaid erDiagram 语法本地规则校验（无外部依赖）。
覆盖：实体块配对、属性行 约束标记<=1 + 注释引号配对、关系行基数与 label。"""
import re
import sys
from pathlib import Path

md = Path(r"C:\Users\liuqu\Desktop\Projects\DemandHub\DemandHub_科技需求收集智能体_概念模型与数据库设计_v1.0.md").read_text(encoding="utf-8")
m = re.search(r"```mermaid\n(.*?)\n```", md, re.S)
if not m:
    print("FAIL: 未找到 mermaid 块"); sys.exit(1)
lines = m.group(1).splitlines()

REL = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+(\|\||\|o|o\||o\{|\}\||\}\{|\}o)\s*--\s*(\|\||\|o|o\||o\{|\}\||\}\{|\}o)\s*([A-Za-z_][A-Za-z0-9_]*)(\s*:\s*\"[^\"]*\"\s*)?$")
ATTR = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+(PK|UK|FK))?(?:\s+\"([^\"]*)\")?\s*$")
errors = []
in_entity = False
depth = 0

for i, line in enumerate(lines, 1):
    s = line.strip()
    if not s:
        continue
    if s.startswith("erDiagram"):
        continue
    if s.endswith("{"):
        in_entity, depth = True, depth + 1
        continue
    if s == "}":
        depth -= 1
        if depth == 0:
            in_entity = False
        continue
    if in_entity:
        mm = ATTR.match(s)
        if not mm:
            errors.append(f"L{i}: 属性行无法解析「{s}」")
        else:
            # 注释引号成对检查
            if '"' in s and not re.search(r'"([^"]*)"\s*$', s):
                errors.append(f"L{i}: 注释引号未闭合「{s}」")
        continue
    mm = REL.match(s)
    if not mm:
        errors.append(f"L{i}: 关系行无法解析「{s}」")

# 显式检查不允许的双约束标记
for i, line in enumerate(lines, 1):
    if re.search(r"\b(PK|UK|FK)\b.*\b(PK|UK|FK)\b", line):
        errors.append(f"L{i}: 属性出现多个约束标记（Mermaid 每属性仅允许 PK/UK/FK 之一）「{line.strip()}」")

if errors:
    print("FAIL（%d 处）:" % len(errors))
    for e in errors:
        print(" ", e)
    sys.exit(1)
print("PASS: erDiagram 语法规则校验通过（%d 行）" % len(lines))
