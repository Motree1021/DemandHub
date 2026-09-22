package com.demandhub.notification.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.notification.entity.OrgSnapshotView;
import com.demandhub.notification.entity.RoleGrantView;
import com.demandhub.notification.mapper.OrgSnapshotViewMapper;
import com.demandhub.notification.mapper.RoleGrantViewMapper;
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

    public RecipientResolver(RoleGrantViewMapper roleGrantMapper, OrgSnapshotViewMapper orgSnapshotMapper) {
        this.roleGrantMapper = roleGrantMapper;
        this.orgSnapshotMapper = orgSnapshotMapper;
    }

    /** 事件接收人（数值用户 ID，去重，不含操作人本人） */
    public Set<Long> resolve(DemandEventMessage msg) {
        String typeCode = msg.getDemandTypeCode();
        Set<Long> receivers = new LinkedHashSet<>();
        switch (msg.getEvent()) {
            case "SUBMIT" -> receivers.addAll(managersOrExecutives(msg.getAssigneeOrgId(), typeCode));
            case "WITHDRAW" -> receivers.addAll(managersOfOrg(msg.getAssigneeOrgId(), typeCode));
            case "ACCEPT", "RETURN", "CLOSE", "CLAIM", "START", "SUBMIT_ACCEPTANCE" ->
                    addIfNotNull(receivers, msg.getSubmitterId());
            case "ASSIGN" -> addIfNotNull(receivers, extraLong(msg, "assigneeId"));
            case "SUBMIT_REVIEW" -> receivers.addAll(managersOrExecutives(msg.getAssigneeOrgId(), typeCode));
            case "REVIEW_PASS", "REVIEW_REJECT", "ACCEPT_REJECT" -> addIfNotNull(receivers, msg.getAssigneeUserId());
            case "ACCEPT_PASS" -> {
                addIfNotNull(receivers, msg.getAssigneeUserId());
                receivers.addAll(managersOfOrg(msg.getAssigneeOrgId(), typeCode));
            }
            case "CHANGE_TYPE" -> {
                addIfNotNull(receivers, msg.getSubmitterId());
                receivers.addAll(managersOrExecutives(msg.getAssigneeOrgId(), typeCode));
            }
            case "HOLD", "RESUME" -> {
                addIfNotNull(receivers, msg.getSubmitterId());
                addIfNotNull(receivers, msg.getAssigneeUserId());
            }
            case "SLA_ALERT" -> {
                receivers.addAll(managersOrExecutives(msg.getAssigneeOrgId(), typeCode));
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

    /** 承接组织经理（授权子树+类型双覆盖）；无人覆盖时兜底需求管理者（EXECUTIVE 全线可管） */
    public Set<Long> managersOrExecutives(Long assigneeOrgId, String typeCode) {
        Set<Long> managers = managersOfOrg(assigneeOrgId, typeCode);
        return managers.isEmpty() ? executives() : managers;
    }

    /** 承接组织的需求经理：MANAGER 有效授权、类型集合覆盖本需求类型，且授权组织物化路径是承接组织路径前缀 */
    public Set<Long> managersOfOrg(Long assigneeOrgId, String typeCode) {
        if (assigneeOrgId == null) {
            return Set.of();
        }
        OrgSnapshotView target = orgSnapshotMapper.selectOne(new LambdaQueryWrapper<OrgSnapshotView>()
                .eq(OrgSnapshotView::getId, assigneeOrgId));
        if (target == null || target.getPath() == null) {
            return Set.of();
        }
        List<RoleGrantView> grants = effectiveGrants("MANAGER").stream()
                .filter(g -> scopeCoversType(g.getDemandTypeScope(), typeCode))
                .collect(Collectors.toList());
        Set<Long> grantOrgIds = grants.stream().map(RoleGrantView::getOrgId)
                .filter(Objects::nonNull).collect(Collectors.toSet());
        if (grantOrgIds.isEmpty()) {
            return Set.of();
        }
        Set<Long> coveredOrgIds = orgSnapshotMapper.selectList(new LambdaQueryWrapper<OrgSnapshotView>()
                        .in(OrgSnapshotView::getId, grantOrgIds)).stream()
                .filter(o -> o.getPath() != null && target.getPath().startsWith(o.getPath()))
                .map(OrgSnapshotView::getId).collect(Collectors.toSet());
        return grants.stream()
                .filter(g -> g.getOrgId() != null && coveredOrgIds.contains(g.getOrgId()))
                .map(RoleGrantView::getDemandUserId).collect(Collectors.toSet());
    }

    /** 需求管理者（EXECUTIVE 全线） */
    public Set<Long> executives() {
        return effectiveGrants("EXECUTIVE").stream()
                .map(RoleGrantView::getDemandUserId).collect(Collectors.toSet());
    }

    private List<RoleGrantView> effectiveGrants(String roleCode) {
        LocalDateTime now = LocalDateTime.now();
        return roleGrantMapper.selectList(new LambdaQueryWrapper<RoleGrantView>()
                .eq(RoleGrantView::getRoleCode, roleCode)
                .and(w -> w.isNull(RoleGrantView::getEffectiveFrom).or().le(RoleGrantView::getEffectiveFrom, now))
                .and(w -> w.isNull(RoleGrantView::getEffectiveTo).or().ge(RoleGrantView::getEffectiveTo, now)));
    }

    /** 授权类型集合是否覆盖目标类型：NULL/空 = 全部类型；typeCode 为空则不过滤 */
    private boolean scopeCoversType(String scope, String typeCode) {
        if (typeCode == null || typeCode.isBlank() || scope == null || scope.isBlank()) {
            return true;
        }
        for (String t : scope.split(",")) {
            if (typeCode.equals(t.trim())) {
                return true;
            }
        }
        return false;
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
