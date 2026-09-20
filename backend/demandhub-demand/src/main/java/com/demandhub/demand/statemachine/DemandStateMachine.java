package com.demandhub.demand.statemachine;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandTransitionLogEntity;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.entity.UserSnapshotView;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandTransitionLogMapper;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.mapper.UserSnapshotViewMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

/**
 * 状态机引擎统一入口（架构 4.1）：
 * transition(demandId, event, operator, context) → 校验合法流转 → 应用状态与领域字段
 * → 乐观锁落库 → 写 demand_transition_log → 发布 Spring 领域事件。
 * 非法流转抛 {@link ErrorCode#ILLEGAL_STATE_TRANSITION} 业务异常。
 */
@Service
public class DemandStateMachine {

    private final StateMachineConfig stateMachineConfig;
    private final DemandMapper demandMapper;
    private final DemandTransitionLogMapper transitionLogMapper;
    private final DemandTypeMapper demandTypeMapper;
    private final UserSnapshotViewMapper userSnapshotMapper;
    private final ApplicationEventPublisher eventPublisher;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public DemandStateMachine(StateMachineConfig stateMachineConfig,
                              DemandMapper demandMapper,
                              DemandTransitionLogMapper transitionLogMapper,
                              DemandTypeMapper demandTypeMapper,
                              UserSnapshotViewMapper userSnapshotMapper,
                              ApplicationEventPublisher eventPublisher) {
        this.stateMachineConfig = stateMachineConfig;
        this.demandMapper = demandMapper;
        this.transitionLogMapper = transitionLogMapper;
        this.demandTypeMapper = demandTypeMapper;
        this.userSnapshotMapper = userSnapshotMapper;
        this.eventPublisher = eventPublisher;
    }

    /**
     * 统一流转入口。
     *
     * @param demandId 需求 id
     * @param event    触发事件
     * @param operator 操作人（网关注入的当前用户）
     * @param ctx      流转上下文（意见 / 附加日志 / 领域字段钩子），可为 null
     * @return 流转后的需求实体
     */
    @Transactional(rollbackFor = Exception.class)
    public DemandEntity transition(Long demandId, DemandEvent event, CurrentUser operator, TransitionContext ctx) {
        if (operator == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        if (ctx == null) {
            ctx = TransitionContext.of();
        }
        // 行锁串行化同一需求的并发流转
        DemandEntity demand = demandMapper.selectForUpdate(demandId);
        if (demand == null) {
            throw new BizException(ErrorCode.DEMAND_NOT_FOUND);
        }
        boolean held = demand.getOnHold() != null && demand.getOnHold() == 1;
        DemandStatus from = held ? DemandStatus.ON_HOLD : DemandStatus.valueOf(demand.getStatus());

        TransitionRule rule = findRule(demand, from, event);
        checkRole(rule, operator, event);

        // 应用状态变化（挂起/恢复特殊处理）
        String toStatusForLog;
        if (event == DemandEvent.HOLD) {
            demand.setHoldSnapshotStatus(demand.getStatus());
            demand.setOnHold(1);
            demand.setHoldReason(ctx.getComment());
            toStatusForLog = DemandStatus.ON_HOLD.name();
        } else if (event == DemandEvent.RESUME) {
            toStatusForLog = demand.getHoldSnapshotStatus();
            demand.setOnHold(0);
            demand.setHoldReason(null);
            demand.setHoldSnapshotStatus(null);
        } else {
            if (rule.to() != null) {
                demand.setStatus(rule.to().name());
            }
            toStatusForLog = demand.getStatus();
        }
        // 领域字段钩子（分派人、时间、评分、类型修正等）
        if (ctx.getFieldUpdater() != null) {
            ctx.getFieldUpdater().accept(demand);
        }

        persistWithVersionGuard(demand);
        writeLog(demand, event, from.name(), toStatusForLog, operator, ctx);
        eventPublisher.publishEvent(new DemandTransitionEvent(
                demand.getId(), demand.getDemandNo(), event.name(),
                from.name(), toStatusForLog, operator.getId(), ctx.getComment(), Map.copyOf(ctx.getExtra())));
        return demand;
    }

    /**
     * 查询当前状态下某事件是否合法（供“可用操作列表”使用，不加锁不落库）。
     */
    public boolean canTransit(DemandEntity demand, DemandEvent event, CurrentUser operator) {
        if (demand == null || operator == null) {
            return false;
        }
        boolean held = demand.getOnHold() != null && demand.getOnHold() == 1;
        DemandStatus from = held ? DemandStatus.ON_HOLD : DemandStatus.valueOf(demand.getStatus());
        try {
            TransitionRule rule = findRule(demand, from, event);
            return rule.roles().isEmpty() || operator.getRoles().stream().anyMatch(rule.roles()::contains);
        } catch (BizException e) {
            return false;
        }
    }

    private TransitionRule findRule(DemandEntity demand, DemandStatus from, DemandEvent event) {
        String key = StateMachineConfig.DEFAULT_KEY;
        DemandTypeEntity type = demandTypeMapper.selectOne(new LambdaQueryWrapper<DemandTypeEntity>()
                .eq(DemandTypeEntity::getTypeCode, demand.getDemandTypeCode()));
        if (type != null && type.getStateMachineKey() != null) {
            key = type.getStateMachineKey();
        }
        List<TransitionRule> rules = stateMachineConfig.rules(key);
        return rules.stream()
                .filter(r -> r.from() == from && r.event() == event)
                .findFirst()
                .orElseThrow(() -> new BizException(ErrorCode.ILLEGAL_STATE_TRANSITION,
                        String.format("当前状态[%s]不允许执行[%s]", from.getLabel(), event.getLabel())));
    }

    private void checkRole(TransitionRule rule, CurrentUser operator, DemandEvent event) {
        if (rule.roles().isEmpty()) {
            return;
        }
        boolean ok = operator.getRoles() != null && operator.getRoles().stream().anyMatch(rule.roles()::contains);
        if (!ok) {
            throw new BizException(ErrorCode.FORBIDDEN, "当前角色无权执行[" + event.getLabel() + "]");
        }
    }

    /** 乐观锁落库：显式 set 全部可变列（含置空场景），version + 1，更新 0 行即并发冲突 */
    private void persistWithVersionGuard(DemandEntity d) {
        LocalDateTime now = LocalDateTime.now();
        int rows = demandMapper.update(null, new LambdaUpdateWrapper<DemandEntity>()
                .eq(DemandEntity::getId, d.getId())
                .eq(DemandEntity::getVersion, d.getVersion())
                .set(DemandEntity::getTitle, d.getTitle())
                .set(DemandEntity::getDemandTypeCode, d.getDemandTypeCode())
                .set(DemandEntity::getSubtypeCode, d.getSubtypeCode())
                .set(DemandEntity::getContent, d.getContent())
                .set(DemandEntity::getUrgency, d.getUrgency())
                .set(DemandEntity::getStatus, d.getStatus())
                .set(DemandEntity::getOnHold, d.getOnHold())
                .set(DemandEntity::getHoldReason, d.getHoldReason())
                .set(DemandEntity::getHoldSnapshotStatus, d.getHoldSnapshotStatus())
                .set(DemandEntity::getActualDemanderId, d.getActualDemanderId())
                .set(DemandEntity::getChannel, d.getChannel())
                .set(DemandEntity::getAssigneeOrgId, d.getAssigneeOrgId())
                .set(DemandEntity::getAssigneeUserId, d.getAssigneeUserId())
                .set(DemandEntity::getProjectId, d.getProjectId())
                .set(DemandEntity::getExpectDeliveryAt, d.getExpectDeliveryAt())
                .set(DemandEntity::getActualDeliveryAt, d.getActualDeliveryAt())
                .set(DemandEntity::getSubmittedAt, d.getSubmittedAt())
                .set(DemandEntity::getClosedAt, d.getClosedAt())
                .set(DemandEntity::getCloseReason, d.getCloseReason())
                .set(DemandEntity::getQualityScore, d.getQualityScore())
                .set(DemandEntity::getSatisfactionScore, d.getSatisfactionScore())
                .set(DemandEntity::getVersion, d.getVersion() + 1)
                .set(DemandEntity::getUpdatedAt, now)
                .set(DemandEntity::getUpdatedBy, com.demandhub.common.context.UserContext.currentUserId()));
        if (rows == 0) {
            throw new BizException(ErrorCode.CONCURRENT_CONFLICT);
        }
        d.setVersion(d.getVersion() + 1);
        d.setUpdatedAt(now);
    }

    private void writeLog(DemandEntity demand, DemandEvent event, String fromStatus, String toStatus,
                          CurrentUser operator, TransitionContext ctx) {
        DemandTransitionLogEntity log = new DemandTransitionLogEntity();
        log.setDemandId(demand.getId());
        log.setFromStatus(fromStatus);
        log.setToStatus(toStatus);
        log.setAction(event.name());
        log.setOperatorId(operator.getId());
        log.setOperatorSnapshot(resolveOperatorName(operator));
        log.setComment(ctx.getComment());
        if (!ctx.getExtra().isEmpty()) {
            try {
                log.setExtra(objectMapper.writeValueAsString(ctx.getExtra()));
            } catch (Exception ignored) {
                // extra 序列化失败不阻断流转
            }
        }
        transitionLogMapper.insert(log);
    }

    private String resolveOperatorName(CurrentUser operator) {
        UserSnapshotView user = userSnapshotMapper.selectById(operator.getId());
        if (user != null && user.getName() != null) {
            return user.getName();
        }
        return operator.getUserId();
    }
}
