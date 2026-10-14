"""P5 组织树单测（蓝本 OrgAdminService 口径 + demand 两列回填）。

- 树：新增占位插入→回填 path（尾斜杠）；移动整树前缀替换 + 防环；平铺/嵌套查询
- 删除五校验：根/900 虚拟/子组织/授权引用/需求引用（用户主组织未建列，用户引用不做）
- 回填（蓝本口径）：提报 submitter_org_id=dept_id 映射未命中挂 900；
  assignee_org_id=类型 default_org_id；类型修正随新类型重路由；拆分继承父承接组织
- API 守卫：非 ADMIN 403
"""
import pytest

from app.core.errors import BizError
from app.db.models import Demand, DemandOrg, DemandRoleGrant, DemandType, User, now
from app.services import demand_service, flow_service, org_service, triage_service

TECH_FORM = {"clientRequestId": "org-key", "title": "需求记录", "demandTypeCode": "TECH",
             "content": "整理需求并记录完整业务信息", "urgency": "NORMAL",
             "elements": {"A": {"techSubtype": "DATA_RPT"},
                          "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各机构持仓汇总",
                                "useScenario": "客户经理每天晨会前查看各机构持仓", "painPoint": "手工汇总每次近1小时"},
                          "D": {"functionDescription": "按机构汇总持仓并展示", "inputOutput": "输入流水输出报表",
                                "acceptanceCriteria": "连续7天对账误差为0"}}}


def _user(**kw):
    defaults = {"name": "小权", "wecom_userid": "p5-org-u1", "channel": "CHUANGJIN_LS"}
    return User(**(defaults | kw))


async def _seed_tree(factory):
    """造 100 业务线 → 110 部门 → 111 小组 + 120 部门 + 900 虚拟，返回 id 字典。"""
    async with factory() as db:
        async with db.begin():
            db.add_all([
                DemandOrg(id=100, name="业务线", level="LINE", parent_id=0, path="/100/",
                          org_kind="BOTH", status="ACTIVE"),
                DemandOrg(id=110, name="科技产品部", level="DEPT", parent_id=100, path="/100/110/",
                          org_kind="ASSIGNER", status="ACTIVE"),
                DemandOrg(id=111, name="科技产品一组", level="GROUP", parent_id=110,
                          path="/100/110/111/", org_kind="ASSIGNER", status="ACTIVE",
                          external_dept_id="DEPT-TECH-1"),
                DemandOrg(id=120, name="客户陪伴部", level="DEPT", parent_id=100, path="/100/120/",
                          org_kind="ASSIGNER", status="ACTIVE"),
                DemandOrg(id=900, name="外部虚拟组织", level="GROUP", parent_id=100, path="/100/900/",
                          org_kind="REPORTER", status="ACTIVE", external_flag=1),
            ])
    return {100: 100, 110: 110, 111: 111, 120: 120, 900: 900}


@pytest.mark.asyncio
async def test_create_path_backfill_and_tree(session_factory):
    await _seed_tree(session_factory)
    async with session_factory() as db:
        async with db.begin():
            row = await org_service.create_org(db, name="科技产品二组", level="GROUP",
                                               parent_id=110, org_kind="ASSIGNER",
                                               external_dept_id="DEPT-TECH-2")
            assert row.path == f"/100/110/{row.id}/"  # 占位插入→回填
            with pytest.raises(BizError):  # 父不存在
                await org_service.create_org(db, name="无根", level="GROUP",
                                             parent_id=999, org_kind="ASSIGNER")
            with pytest.raises(BizError):  # 层级枚举
                await org_service.create_org(db, name="坏", level="BAD",
                                             parent_id=110, org_kind="ASSIGNER")
            with pytest.raises(BizError):  # orgKind 枚举
                await org_service.create_org(db, name="坏", level="GROUP",
                                             parent_id=110, org_kind="BAD")
            new_id = row.id
        tree = await org_service.tree(db)
    line = next(n for n in tree if n["orgId"] == 100)
    dept = next(n for n in line["children"] if n["orgId"] == 110)
    assert {n["orgId"] for n in dept["children"]} == {111, new_id}
    assert dept["children"][0]["externalDeptId"] == "DEPT-TECH-1"


@pytest.mark.asyncio
async def test_move_subtree_prefix_and_cycle_guard(session_factory):
    await _seed_tree(session_factory)
    async with session_factory() as db:
        async with db.begin():
            # 110 整棵子树移到 120 下：110 与后代 111 的路径都做前缀替换
            moved = await org_service.update_org(db, 110, parent_id=120)
            assert moved.path == "/100/120/110/" and moved.parent_id == 120
            child = (await org_service.list_orgs(db))
            assert next(o for o in child if o["orgId"] == 111)["path"] == "/100/120/110/111/"
            with pytest.raises(BizError) as exc:  # 防环：100 不能移到自己的子树下
                await org_service.update_org(db, 100, parent_id=111)
            assert "子组织" in str(exc.value)
            renamed = await org_service.update_org(db, 111, name="新组名", status="DISABLED",
                                                   external_dept_id="")
            assert renamed.name == "新组名" and renamed.status == "DISABLED"
            assert renamed.external_dept_id is None  # 空串清空
            with pytest.raises(BizError):
                await org_service.update_org(db, 111, status="BAD")


@pytest.mark.asyncio
async def test_delete_five_guards(session_factory):
    await _seed_tree(session_factory)
    async with session_factory() as db:
        async with db.begin():
            manager = _user(wecom_userid="p5-org-mgr", name="经理")
            db.add(manager)
            await db.flush()
            db.add(DemandOrg(id=130, name="空闲组", level="GROUP", parent_id=100,
                             path="/100/130/", org_kind="ASSIGNER", status="ACTIVE"))
            db.add(DemandRoleGrant(user_id=manager.id, role_code="MANAGER", org_id=120))
            db.add(DemandType(type_code="TECH", type_name="科技需求", default_org_id=111))
            db.add(Demand(title="引用需求", demand_type_code="TECH", content="c", urgency="NORMAL",
                          status="SUBMITTED", submitter_id=manager.id, submitter_name=manager.name,
                          channel="CHUANGJIN_LS", client_request_id="org-ref-1",
                          create_request_hash="raw", submitted_at=now(), revision=0,
                          assignee_org_id=111))
            with pytest.raises(BizError, match="根组织"):
                await org_service.delete_org(db, 100)
            with pytest.raises(BizError, match="外部虚拟组织"):
                await org_service.delete_org(db, 900)
            with pytest.raises(BizError, match="子组织"):
                await org_service.delete_org(db, 110)
            with pytest.raises(BizError, match="授权引用"):
                await org_service.delete_org(db, 120)
            with pytest.raises(BizError, match="需求引用"):
                await org_service.delete_org(db, 111)  # 下方 demand.assignee_org_id=111
            # 干净组织可删
            await org_service.delete_org(db, 130)
            assert all(o["orgId"] != 130 for o in await org_service.list_orgs(db))


@pytest.mark.asyncio
async def test_resolve_and_submit_backfill(session_factory):
    await _seed_tree(session_factory)
    async with session_factory() as db:
        async with db.begin():
            db.add(DemandType(type_code="TECH", type_name="科技需求", default_org_id=111))
            hit = _user(wecom_userid="p5-org-hit", dept_id="DEPT-TECH-1")
            miss = _user(wecom_userid="p5-org-miss", dept_id="DEPT-UNKNOWN")
            none_dept = _user(wecom_userid="p5-org-none")
            db.add_all([hit, miss, none_dept])
            await db.flush()
            assert await org_service.resolve_user_org_id(db, hit) == 111
            assert await org_service.resolve_user_org_id(db, miss) == 900  # 未命中挂 900
            assert await org_service.resolve_user_org_id(db, none_dept) == 900
            assert await org_service.resolve_type_org_id(db, "TECH") == 111
            assert await org_service.resolve_type_org_id(db, "NO_SUCH_TYPE") is None
            # 端到端 submit：两列落库
            draft = await demand_service.create_draft(db, hit, TECH_FORM)
            submitted = await demand_service.submit(db, hit, draft.id, 0)
            assert submitted.submitter_org_id == 111 and submitted.assignee_org_id == 111
            # 未命中用户提报：submitter_org_id=900
            TECH_FORM["clientRequestId"] = "org-key-miss"
            draft2 = await demand_service.create_draft(db, miss, TECH_FORM)
            submitted2 = await demand_service.submit(db, miss, draft2.id, 0)
            assert submitted2.submitter_org_id == 900 and submitted2.assignee_org_id == 111


@pytest.mark.asyncio
async def test_change_type_reroutes_and_split_inherits(session_factory):
    await _seed_tree(session_factory)
    async with session_factory() as db:
        async with db.begin():
            db.add_all([
                DemandType(type_code="TECH", type_name="科技需求", default_org_id=111),
                DemandType(type_code="MATL", type_name="物料需求", default_org_id=121),
                DemandOrg(id=121, name="客户陪伴一组", level="GROUP", parent_id=120,
                          path="/100/120/121/", org_kind="ASSIGNER", status="ACTIVE"),
            ])
            admin = _user(wecom_userid="mvp-admin", name="超管")
            db.add(admin)
            await db.flush()
            TECH_FORM["clientRequestId"] = "org-key-ct"
            draft = await demand_service.create_draft(db, admin, TECH_FORM)
            submitted = await demand_service.submit(db, admin, draft.id, 0)
            assert submitted.assignee_org_id == 111
            # 受理进 TRIAGE（拆分要求在途态；ADMIN 直通 ACCEPT 角色校验）
            from app.core.statemachine import engine
            await engine.transition(db, submitted.id, "ACCEPT", admin)
            # 类型修正：TECH → MATL，承接组织 111 → 121
            changed = await triage_service.change_type(db, admin, submitted.id, "MATL", None)
            assert changed.assignee_org_id == 121
            # 拆分：子需求继承父承接组织，提报人组织按操作人（admin 无 dept_id → 900）
            changed.assignee_id = admin.id  # 模拟已领取（仅测试拆分归属校验）
            children = await flow_service.split(db, admin, changed.id, [{"title": "子需求一"}])
            assert children[0].assignee_org_id == 121 and children[0].submitter_org_id == 900


async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_api_guards_and_crud(client, session_factory):
    await _seed_tree(session_factory)
    admin_headers = await _login(client, "超管", "mvp-admin")
    user_headers = await _login(client, "小权", "p5-org-u9")

    assert (await client.get("/demandhub-api/admin/orgs", headers=user_headers)).json()["code"] == 403
    assert (await client.get("/demandhub-api/admin/orgs/tree", headers=user_headers)).json()["code"] == 403
    assert (await client.post("/demandhub-api/admin/orgs", headers=user_headers,
                              json={"name": "越权", "level": "GROUP", "parentId": 110,
                                    "orgKind": "ASSIGNER"})).json()["code"] == 403

    created = await client.post("/demandhub-api/admin/orgs", headers=admin_headers,
                                json={"name": "科技产品二组", "level": "GROUP", "parentId": 110,
                                      "orgKind": "ASSIGNER", "externalDeptId": "DEPT-TECH-2"})
    assert created.json()["code"] == 0
    row = created.json()["data"]
    assert row["path"] == f"/100/110/{row['orgId']}/" and row["status"] == "ACTIVE"

    updated = await client.put(f"/demandhub-api/admin/orgs/{row['orgId']}", headers=admin_headers,
                               json={"parentId": 120, "name": "陪伴二组"})
    assert updated.json()["code"] == 0
    assert updated.json()["data"]["path"] == f"/100/120/{row['orgId']}/"

    tree = await client.get("/demandhub-api/admin/orgs/tree", headers=admin_headers)
    assert tree.json()["code"] == 0

    removed = await client.delete(f"/demandhub-api/admin/orgs/{row['orgId']}", headers=admin_headers)
    assert removed.json()["code"] == 0
    assert (await client.delete(f"/demandhub-api/admin/orgs/{row['orgId']}",
                                headers=admin_headers)).json()["code"] == 404
