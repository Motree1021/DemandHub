import json
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font

from app.services.demand_service import serialize_demand
from app.standards.schema import Standard


def as_standard(value):
    return value if isinstance(value, Standard) or value is None else Standard.model_validate(value)


def as_demand(value):
    return value if isinstance(value, dict) else serialize_demand(value)


def display(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def cell_escape(value):
    return display(value).replace("|", "\|").replace("\n", "<br>")


def to_markdown(demand, standard, messages) -> str:
    d, std = as_demand(demand), as_standard(standard)
    lines = [f"# {d.get('title') or '未命名草稿'}", "", "## 基本信息", "", "| 字段 | 内容 |", "|---|---|"]
    labels = {"id": "ID", "demandNo": "编号", "demandTypeCode": "类型", "subtypeCode": "子类", "status": "状态",
              "urgency": "紧急度", "expectDeliveryAt": "期望交付日期", "submitterName": "提报人",
              "submitterDept": "提报部门", "channel": "渠道", "createdAt": "创建时间", "submittedAt": "提交时间",
              "closedAt": "撤销时间", "closeReason": "撤销原因", "standardVersionId": "标准快照ID", "qualityContentHash": "内容哈希"}
    for key, label in labels.items():
        lines.append(f"| {label} | {cell_escape(d.get(key))} |")
    lines.extend(["", "## 需求描述", "", d.get("content") or "", "", "## 标准字段", "", "| 字段 | 内容 |", "|---|---|"])
    fields = {f.field_path: f.label for f in std.fields} if std else {}
    for key, value in (d.get("ext") or {}).items():
        lines.append(f"| {cell_escape(fields.get('ext.' + key, key))} | {cell_escape(value)} |")
    lines.extend(["", "## 要素完备度", "", "| 要素 | 状态 | 说明 |", "|---|---|---|"])
    element_labels = {f.key: f.label for f in std.elements} if std else {}
    for item in d.get("quality") or []:
        lines.append(f"| {cell_escape(element_labels.get(item['key'], item['key']))} | {cell_escape(item['status'])} | {cell_escape(item.get('note'))} |")
    lines.extend(["", "## 对话回放", ""])
    for msg in messages:
        lines.extend([f"### {msg['role']} · {msg.get('createdAt', '')}", "", msg["content"], ""])
    return "\n".join(lines) + "\n"


def to_xlsx(demands, standards) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    groups = {}
    for row in demands:
        d = as_demand(row)
        groups.setdefault(d.get("demandTypeCode") or "未分类", []).append(d)
    if not groups:
        groups["需求"] = []
    basic = [("id", "ID"), ("demandNo", "编号"), ("title", "标题"), ("demandTypeCode", "类型"), ("subtypeCode", "子类"),
             ("content", "需求描述"), ("status", "状态"), ("urgency", "紧急度"), ("expectDeliveryAt", "期望交付日期"),
             ("submitterName", "提报人"), ("submitterDept", "提报部门"), ("channel", "渠道"),
             ("submittedAt", "提交时间"), ("closedAt", "撤销时间"), ("closeReason", "撤销原因"),
             ("standardVersionId", "标准快照ID"), ("qualityContentHash", "内容哈希")]
    for type_code, rows in groups.items():
        sheet = workbook.create_sheet(type_code)
        fields, elements = {}, {}
        for row in rows:
            std = as_standard(standards.get(row["id"]) or standards.get(type_code))
            if std:
                for f in std.fields:
                    if f.field_path.startswith("ext."):
                        fields.setdefault(f.field_path, f.label)
                for f in std.elements:
                    elements.setdefault(f.key, f.label)
        sheet.append([label for _, label in basic] + [label + "状态" for label in elements.values()] + list(fields.values()))
        for row in rows:
            quality = {q["key"]: q["status"] for q in row.get("quality") or []}
            values = [row.get(key) for key, _ in basic] + [quality.get(key) for key in elements] + [(row.get("ext") or {}).get(path[4:]) for path in fields]
            sheet.append([display(value) for value in values])
            # 用户文本强制字符串类型，=、+、-、@ 等不会变为 Excel 公式。
            for cell in sheet[sheet.max_row]:
                cell.data_type = "s"
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 22
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
