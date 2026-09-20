package com.demandhub.system.integration.pcenter;

import com.demandhub.system.integration.pcenter.dto.MasterDataChanges;
import com.demandhub.system.integration.pcenter.dto.PcOrg;
import com.demandhub.system.integration.pcenter.dto.PcUser;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 权限中心 Mock 实现：内存主数据源 + 变更日志。
 * 组织树含"平台/双中心"结构：平台=财管科技产品部(110)，双中心=客户陪伴服务部(120)/培训开发部(130)。
 */
@Component
public class MockPermissionCenterClient implements PermissionCenterClient {

    private final Map<String, PcUser> users = new LinkedHashMap<>();
    private final Map<Long, PcOrg> orgs = new LinkedHashMap<>();
    /** 变更日志：watermark -> 变更后的用户/组织快照 */
    private final List<ChangeEntry> changeLog = new ArrayList<>();

    private record ChangeEntry(LocalDateTime changedAt, PcUser user, PcOrg org) {
    }

    public MockPermissionCenterClient() {
        initOrgs();
        initUsers();
    }

    private void initOrgs() {
        addOrg(100L, "创金合信零售业务线", "LINE", 0L, "/100", "BOTH");
        addOrg(110L, "财管科技产品部", "DEPT", 100L, "/100/110", "BOTH");
        addOrg(111L, "科技产品一组", "GROUP", 110L, "/100/110/111", "ASSIGNER");
        addOrg(112L, "科技产品二组", "GROUP", 110L, "/100/110/112", "ASSIGNER");
        addOrg(120L, "客户陪伴服务部", "DEPT", 100L, "/100/120", "BOTH");
        addOrg(121L, "客户陪伴一组", "GROUP", 120L, "/100/120/121", "ASSIGNER");
        addOrg(130L, "培训开发部", "DEPT", 100L, "/100/130", "BOTH");
        addOrg(131L, "培训开发一组", "GROUP", 130L, "/100/130/131", "ASSIGNER");
        addOrg(140L, "零售一线营业部", "DEPT", 100L, "/100/140", "REPORTER");
        addOrg(141L, "营业部一组", "GROUP", 140L, "/100/140/141", "REPORTER");
    }

    private void initUsers() {
        addUser(1001L, "u_admin_001", "张管理", 110L, "系统管理员");
        addUser(1002L, "u_exec_001", "李总", 100L, "需求管理者");
        addUser(1003L, "u_mgr_tech", "王经理", 110L, "科技需求经理");
        addUser(1004L, "u_handler_a1", "陈陪伴", 121L, "客户陪伴处理人");
        addUser(1005L, "u_handler_b1", "刘培训", 131L, "培训开发处理人");
        addUser(1006L, "u_reporter_1", "赵一线", 141L, "一线提报人");
        addUser(1007L, "u_reporter_2", "钱一线", 141L, "一线提报人");
    }

    private void addOrg(Long orgId, String name, String level, Long parentId, String path, String orgKind) {
        PcOrg org = new PcOrg();
        org.setOrgId(orgId);
        org.setName(name);
        org.setLevel(level);
        org.setParentId(parentId);
        org.setPath(path);
        org.setOrgKind(orgKind);
        org.setStatus("ACTIVE");
        orgs.put(orgId, org);
    }

    private void addUser(Long id, String userId, String name, Long primaryOrgId, String remark) {
        PcUser u = new PcUser();
        u.setId(id);
        u.setUserId(userId);
        u.setName(name);
        u.setWecomId("wq_" + userId);
        u.setEmployeeNo("E" + id);
        u.setPrimaryOrgId(primaryOrgId);
        u.setDeptPath(buildDeptPath(primaryOrgId));
        u.setPhone("138" + String.format("%08d", id));
        u.setEmail(userId + "@demandhub.local");
        u.setStatus("ACTIVE");
        users.put(userId, u);
    }

    private String buildDeptPath(Long orgId) {
        PcOrg org = orgs.get(orgId);
        if (org == null) {
            return "";
        }
        String[] ids = org.getPath().substring(1).split("/");
        StringBuilder sb = new StringBuilder();
        for (String id : ids) {
            PcOrg node = orgs.get(Long.parseLong(id));
            if (node != null) {
                if (sb.length() > 0) {
                    sb.append("/");
                }
                sb.append(node.getName());
            }
        }
        return sb.toString();
    }

    @Override
    public PcUser getUserByWecomId(String wecomId) {
        return users.values().stream()
                .filter(u -> u.getWecomId().equals(wecomId))
                .findFirst()
                .orElse(null);
    }

    @Override
    public PcUser getUserByUserId(String userId) {
        return users.get(userId);
    }

    @Override
    public List<PcUser> listAllUsers() {
        return new ArrayList<>(users.values());
    }

    @Override
    public List<PcOrg> listAllOrgs() {
        return new ArrayList<>(orgs.values());
    }

    @Override
    public synchronized MasterDataChanges listChanges(LocalDateTime watermark) {
        MasterDataChanges changes = new MasterDataChanges();
        for (ChangeEntry entry : changeLog) {
            if (entry.changedAt().isAfter(watermark)) {
                if (entry.user() != null) {
                    changes.getUsers().add(entry.user());
                }
                if (entry.org() != null) {
                    changes.getOrgs().add(entry.org());
                }
            }
        }
        return changes;
    }

    @Override
    public synchronized void simulateUserMove(String userId, Long newOrgId) {
        PcUser u = users.get(userId);
        if (u == null) {
            return;
        }
        u.setPrimaryOrgId(newOrgId);
        u.setDeptPath(buildDeptPath(newOrgId));
        changeLog.add(new ChangeEntry(LocalDateTime.now(), u, null));
    }
}
