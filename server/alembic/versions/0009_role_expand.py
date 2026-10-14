"""P4 角色扩展：存量状态机配置角色重映射（对齐蓝本 StateMachineConfig + 代码 DEFAULT_RULES）。

- 受理族 ACCEPT/RETURN/CLOSE/ASSIGN/REVIEW_PASS/REVIEW_REJECT：["ADMIN"] → ["MANAGER"]
- 类型修正 CHANGE_TYPE：["ADMIN"] → ["EXECUTIVE"]
- 提交方案评审 SUBMIT_REVIEW：["HANDLER"] → ["HANDLER", "MANAGER"]
- 可代办族 RETURN_POOL/HOLD/RESUME：["HANDLER", "ADMIN"] → ["HANDLER", "MANAGER"]
- 只改 rules[].roles，其余字段（from/to/remark/自定义规则）原样保留；ADMIN 由引擎直通兜底
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_MANAGER_EVENTS = {"ACCEPT", "RETURN", "CLOSE", "ASSIGN", "REVIEW_PASS", "REVIEW_REJECT"}
_DELEGABLE_EVENTS = {"RETURN_POOL", "HOLD", "RESUME"}


def _remap(rule: dict, reverse: bool = False) -> None:
    roles = rule.get("roles") or []
    event = rule.get("event")
    if not reverse:
        if roles == ["ADMIN"] and event in _MANAGER_EVENTS:
            rule["roles"] = ["MANAGER"]
        elif roles == ["ADMIN"] and event == "CHANGE_TYPE":
            rule["roles"] = ["EXECUTIVE"]
        elif roles == ["HANDLER"] and event == "SUBMIT_REVIEW":
            rule["roles"] = ["HANDLER", "MANAGER"]
        elif set(roles) == {"HANDLER", "ADMIN"} and event in _DELEGABLE_EVENTS:
            rule["roles"] = ["HANDLER", "MANAGER"]
    else:
        if roles == ["MANAGER"] and event in _MANAGER_EVENTS:
            rule["roles"] = ["ADMIN"]
        elif roles == ["EXECUTIVE"] and event == "CHANGE_TYPE":
            rule["roles"] = ["ADMIN"]
        elif set(roles) == {"HANDLER", "MANAGER"} and event == "SUBMIT_REVIEW":
            rule["roles"] = ["HANDLER"]
        elif set(roles) == {"HANDLER", "MANAGER"} and event in _DELEGABLE_EVENTS:
            rule["roles"] = ["HANDLER", "ADMIN"]


def _transform_all(reverse: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM state_machine_config")).all()
    for row_id, config_json in rows:
        try:
            data = json.loads(config_json)
        except (TypeError, json.JSONDecodeError):
            continue  # 坏配置跳过（与引擎热加载口径一致：不整体回滚）
        rules = data.get("rules")
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if isinstance(rule, dict):
                _remap(rule, reverse)
        bind.execute(
            sa.text("UPDATE state_machine_config SET config_json = :cfg WHERE id = :id"),
            {"cfg": json.dumps(data, ensure_ascii=False), "id": row_id})


def upgrade():
    _transform_all(reverse=False)


def downgrade():
    _transform_all(reverse=True)
