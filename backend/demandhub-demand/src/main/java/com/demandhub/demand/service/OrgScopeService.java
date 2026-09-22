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

import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 组织维度业务权限校验（写入侧补充：数据权限拦截器只拦 SELECT，写操作自行校验归属）。
 * - 经理管事：MANAGER 授权组织子树包含需求承接组织，或 EXECUTIVE 全线
 * - 处理人领活：HANDLER 授权组织子树包含需求承接组织
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
     * 当前用户是否可管理指定承接组织的需求（经理受理/退回/关闭/分派/评审等动作）。
     * EXECUTIVE 全线可管；MANAGER 需授权子树覆盖。
     */
    public boolean canManage(CurrentUser user, Long assigneeOrgId) {
        if (user == null) {
            return false;
        }
        if (user.hasRole("EXECUTIVE")) {
            return true;
        }
        if (!user.hasRole("MANAGER")) {
            return false;
        }
        DataScope scope = dataScopeService.currentScope(user);
        return assigneeOrgId != null && scope.getOrgIds().contains(assigneeOrgId);
    }

    public void requireManage(CurrentUser user, Long assigneeOrgId) {
        if (!canManage(user, assigneeOrgId)) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅本承接组织的需求经理可操作");
        }
    }

    /**
     * 当前用户是否可作为处理人领取指定承接组织的需求（HANDLER 授权子树覆盖）。
     */
    public boolean canHandle(CurrentUser user, Long assigneeOrgId) {
        if (user == null || !user.hasRole("HANDLER") || assigneeOrgId == null) {
            return false;
        }
        DataScope scope = dataScopeService.currentScope(user);
        return scope.getOrgIds().contains(assigneeOrgId);
    }

    /**
     * 校验某用户（数值 ID）是否具备指定角色且授权组织子树覆盖目标组织（分派校验被分派人用）。
     */
    public boolean userHasRoleInOrg(Long targetUserId, String roleCode, Long targetOrgId) {
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
}
