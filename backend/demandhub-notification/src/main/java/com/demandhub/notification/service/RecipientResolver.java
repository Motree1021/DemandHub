package com.demandhub.notification.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.notification.entity.OrgSnapshotView;
import com.demandhub.notification.entity.RoleGrantView;
import com.demandhub.notification.entity.UserSnapshotView;
import com.demandhub.notification.mapper.OrgSnapshotViewMapper;
import com.demandhub.notification.mapper.RoleGrantViewMapper;
import com.demandhub.notification.mapper.UserSnapshotViewMapper;
import com.demandhub.notification.mq.DemandEventMessage;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 通知接收人解析（架构 4.5：按事件类型确定相关方）。
 * - 提交/评审/SLA → 承接组织经理（授权子树覆盖），无人覆盖时兜底需求管理者；
 * - 分派/打回 → 处理人；受理/退回/关闭/验收 → 提报人；状态变更 → 提报人 + 处理人。
 * 操作人本人不重复接收（SLA 系统事件除外）。
 */
@Service
public class RecipientResolver {

    private final RoleGrantViewMapper roleGrantMapper;
    private final OrgSnapshotViewMapper orgSnapshotMapper;
    private final UserSnapshotViewMapper userSnapshotMapper;

    public RecipientResolver(RoleGrantViewMapper roleGrantMapper, OrgSnapshotViewMapper orgSnapshotMapper,
                             UserSnapshotViewMapper userSnapshotMapper) {
        this.roleGrantMapper = roleGrantMapper;
        this.orgSnapshotMapper = orgSnapshotMapper;
        this.userSnapshotMapper = userSnapshotMapper;
    }

    /** 事件接收人（数值用户 ID，去重，不含操作人本人） */
    public Set<Long> resolve(DemandEventMessage msg) {
        Set<Long> receivers = new LinkedHashSet<>();
        switch (msg.getEvent()) {
            case "SUBMIT" -> receivers.addAll(managersOrExecutives(msg.getAssigneeOrgId()));
            case "WITHDRAW" -> receivers.addAll(managersOfOrg(msg.getAssigneeOrgId()));
            case "ACCEPT", "RETURN", "CLOSE", "CLAIM", "START", "SUBMIT_ACCEPTANCE" ->
                    addIfNotNull(receivers, msg.getSubmitterId());
            case "ASSIGN" -> addIfNotNull(receivers, extraLong(msg, "assigneeId"));
            case "SUBMIT_REVIEW" -> receivers.addAll(managersOrExecutives(msg.getAssigneeOrgId()));
            case "REVIEW_PASS", "REVIEW_REJECT", "ACCEPT_REJECT" -> addIfNotNull(receivers, msg.getAssigneeUserId());
            case "ACCEPT_PASS" -> {
                addIfNotNull(receivers, msg.getAssigneeUserId());
                receivers.addAll(managersOfOrg(msg.getAssigneeOrgId()));
            }
            case "CHANGE_TYPE" -> {
                addIfNotNull(receivers, msg.getSubmitterId());
                receivers.addAll(managersOrExecutives(msg.getAssigneeOrgId()));
            }
            case "HOLD", "RESUME" -> {
                addIfNotNull(receivers, msg.getSubmitterId());
                addIfNotNull(receivers, msg.getAssigneeUserId());
            }
            case "SLA_ALERT" -> {
                receivers.addAll(managersOrExecutives(msg.getAssigneeOrgId()));
                receivers.addAll(executives());
                addIfNotNull(receivers, msg.getAssigneeUserId());
            }
            default -> {
                // 未知事件不通知
            }
        }
        // 操作人本人不重复接收（SLA 为系统事件 operatorId=0，不影响）
        if (msg.getOperatorId() != null && msg.getOperatorId() > 0) {
            receivers.remove(msg.getOperatorId());
        }
        return receivers;
    }

    /** 承接组织经理（授权子树覆盖）；无人覆盖时兜底需求管理者（EXECUTIVE 全线可管） */
    public Set<Long> managersOrExecutives(Long assigneeOrgId) {
        Set<Long> managers = managersOfOrg(assigneeOrgId);
        return managers.isEmpty() ? executives() : managers;
    }

    /** 承接组织的需求经理：DEMAND_MANAGER 有效授权且授权组织物化路径是承接组织路径前缀 */
    public Set<Long> managersOfOrg(Long assigneeOrgId) {
        if (assigneeOrgId == null) {
            return Set.of();
        }
        OrgSnapshotView target = orgSnapshotMapper.selectOne(new LambdaQueryWrapper<OrgSnapshotView>()
                .eq(OrgSnapshotView::getOrgId, assigneeOrgId));
        if (target == null || target.getPath() == null) {
            return Set.of();
        }
        List<RoleGrantView> grants = effectiveGrants("DEMAND_MANAGER");
        Set<Long> grantOrgIds = grants.stream().map(RoleGrantView::getOrgId)
                .filter(Objects::nonNull).collect(Collectors.toSet());
        if (grantOrgIds.isEmpty()) {
            return Set.of();
        }
        Set<Long> coveredOrgIds = orgSnapshotMapper.selectList(new LambdaQueryWrapper<OrgSnapshotView>()
                        .in(OrgSnapshotView::getOrgId, grantOrgIds)).stream()
                .filter(o -> o.getPath() != null && target.getPath().startsWith(o.getPath()))
                .map(OrgSnapshotView::getOrgId).collect(Collectors.toSet());
        Set<String> userIds = grants.stream()
                .filter(g -> g.getOrgId() != null && coveredOrgIds.contains(g.getOrgId()))
                .map(RoleGrantView::getUserId).collect(Collectors.toSet());
        return toNumericIds(userIds);
    }

    /** 需求管理者（EXECUTIVE 全线） */
    public Set<Long> executives() {
        Set<String> userIds = effectiveGrants("EXECUTIVE").stream()
                .map(RoleGrantView::getUserId).collect(Collectors.toSet());
        return toNumericIds(userIds);
    }

    private List<RoleGrantView> effectiveGrants(String roleCode) {
        LocalDateTime now = LocalDateTime.now();
        return roleGrantMapper.selectList(new LambdaQueryWrapper<RoleGrantView>()
                .eq(RoleGrantView::getRoleCode, roleCode)
                .and(w -> w.isNull(RoleGrantView::getEffectiveFrom).or().le(RoleGrantView::getEffectiveFrom, now))
                .and(w -> w.isNull(RoleGrantView::getEffectiveTo).or().ge(RoleGrantView::getEffectiveTo, now)));
    }

    /** 权限中心字符串用户 ID → 数值快照 ID */
    private Set<Long> toNumericIds(Set<String> userIds) {
        if (userIds.isEmpty()) {
            return Set.of();
        }
        return userSnapshotMapper.selectList(new LambdaQueryWrapper<UserSnapshotView>()
                        .in(UserSnapshotView::getUserId, userIds)).stream()
                .map(UserSnapshotView::getId).collect(Collectors.toSet());
    }

    private void addIfNotNull(Set<Long> receivers, Long userId) {
        if (userId != null) {
            receivers.add(userId);
        }
    }

    private Long extraLong(DemandEventMessage msg, String key) {
        Map<String, Object> extra = msg.getExtra();
        if (extra == null || extra.get(key) == null) {
            return null;
        }
        Object value = extra.get(key);
        return value instanceof Number number ? number.longValue() : Long.parseLong(String.valueOf(value));
    }
}
