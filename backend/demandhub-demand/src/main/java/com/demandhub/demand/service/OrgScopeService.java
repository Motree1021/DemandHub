package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.OrgSnapshotView;
import com.demandhub.demand.entity.RoleGrantView;
import com.demandhub.demand.entity.UserSnapshotView;
import com.demandhub.demand.mapper.OrgSnapshotViewMapper;
import com.demandhub.demand.mapper.RoleGrantViewMapper;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 组织维度业务权限校验（写入侧补充：数据权限拦截器只拦 SELECT，写操作自行校验归属）。
 * 角色族三维（角色族 × 组织子树 × 类型集合）：受理/分派/评审等动作须 组织子树 与 类型范围 双重命中。
 * - 经理管事：MANAGER 授权（类型集合含需求类型 且 组织子树覆盖承接组织）
 * - 处理人领活：HANDLER 授权（类型集合含需求类型 且 组织子树覆盖承接组织）
 */
@Service
public class OrgScopeService {

    private final DataScopeService dataScopeService;
    private final RoleGrantViewMapper roleGrantMapper;
    private final OrgSnapshotViewMapper orgSnapshotMapper;
    private final UserLookupService userLookupService;

    public OrgScopeService(DataScopeService dataScopeService,
                           RoleGrantViewMapper roleGrantMapper,
                           OrgSnapshotViewMapper orgSnapshotMapper,
                           UserLookupService userLookupService) {
        this.dataScopeService = dataScopeService;
        this.roleGrantMapper = roleGrantMapper;
        this.orgSnapshotMapper = orgSnapshotMapper;
        this.userLookupService = userLookupService;
    }

    /**
     * 当前用户是否可管理指定承接组织、指定类型需求（经理受理/退回/关闭/分派/评审等动作）。
     * 双重命中：MANAGER 授权的类型集合含 typeCode 且组织子树覆盖 assigneeOrgId。
     */
    public boolean canManage(CurrentUser user, Long assigneeOrgId, String typeCode) {
        if (user == null || !user.hasRole("MANAGER")) {
            return false;
        }
        DataScope scope = dataScopeService.currentScope(user);
        Set<Long> orgIds = typeCode == null ? null : scope.getOrgIdsByType().get(typeCode);
        return assigneeOrgId != null && orgIds != null && orgIds.contains(assigneeOrgId);
    }

    public void requireManage(CurrentUser user, Long assigneeOrgId, String typeCode) {
        if (!canManage(user, assigneeOrgId, typeCode)) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅本类型本承接组织的需求经理可操作");
        }
    }

    /**
     * 当前用户是否可作为处理人领取指定承接组织、指定类型需求（HANDLER 授权双重命中）。
     */
    public boolean canHandle(CurrentUser user, Long assigneeOrgId, String typeCode) {
        if (user == null || !user.hasRole("HANDLER") || assigneeOrgId == null || typeCode == null) {
            return false;
        }
        DataScope scope = dataScopeService.currentScope(user);
        Set<Long> orgIds = scope.getOrgIdsByType().get(typeCode);
        return orgIds != null && orgIds.contains(assigneeOrgId);
    }

    /**
     * 校验某用户（数值 ID）是否具备指定角色，且授权 类型集合含 typeCode、组织子树覆盖 targetOrgId
     * （分派校验被分派人用：被分派人必须是本类型本承接组织的处理人）。
     */
    public boolean userHasRoleInOrg(Long targetUserId, String roleCode, Long targetOrgId, String typeCode) {
        if (targetUserId == null || targetOrgId == null) {
            return false;
        }
        UserSnapshotView snapshot = userLookupService.getById(targetUserId);
        if (snapshot == null) {
            return false;
        }
        LocalDateTime now = LocalDateTime.now();
        List<RoleGrantView> grants = roleGrantMapper.selectList(new LambdaQueryWrapper<RoleGrantView>()
                .eq(RoleGrantView::getDemandUserId, snapshot.getId())
                .eq(RoleGrantView::getRoleCode, roleCode)
                .and(w -> w.isNull(RoleGrantView::getEffectiveFrom).or().le(RoleGrantView::getEffectiveFrom, now))
                .and(w -> w.isNull(RoleGrantView::getEffectiveTo).or().ge(RoleGrantView::getEffectiveTo, now)));
        // 类型命中：scope 为空（跟随默认=全部类型）或显式包含该类型
        grants = grants.stream().filter(g -> scopeCoversType(g.getDemandTypeScope(), typeCode)).toList();
        if (grants.isEmpty()) {
            return false;
        }
        Set<Long> grantOrgIds = grants.stream().map(RoleGrantView::getOrgId)
                .filter(java.util.Objects::nonNull).collect(Collectors.toSet());
        if (grantOrgIds.isEmpty()) {
            return false;
        }
        OrgSnapshotView target = orgSnapshotMapper.selectOne(new LambdaQueryWrapper<OrgSnapshotView>()
                .eq(OrgSnapshotView::getId, targetOrgId));
        if (target == null || target.getPath() == null) {
            return false;
        }
        // 授权组织物化路径是目标组织路径的前缀即覆盖（含自身与子树）
        List<OrgSnapshotView> grantOrgs = orgSnapshotMapper.selectList(new LambdaQueryWrapper<OrgSnapshotView>()
                .in(OrgSnapshotView::getId, grantOrgIds));
        return grantOrgs.stream().anyMatch(o -> o.getPath() != null && target.getPath().startsWith(o.getPath()));
    }

    /** 授权类型集合是否覆盖类型：NULL/空 = 全部类型；否则显式包含 */
    private boolean scopeCoversType(String demandTypeScope, String typeCode) {
        if (!StringUtils.hasText(demandTypeScope) || typeCode == null) {
            return true;
        }
        for (String t : demandTypeScope.split(",")) {
            if (typeCode.equals(t.trim())) {
                return true;
            }
        }
        return false;
    }
}
