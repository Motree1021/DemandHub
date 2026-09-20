package com.demandhub.demand.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.dto.AssignRequest;
import com.demandhub.demand.dto.ChangeTypeRequest;
import com.demandhub.demand.dto.CloseRequest;
import com.demandhub.demand.entity.AssignmentEntity;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.entity.DemandRelationEntity;
import com.demandhub.demand.entity.DemandTypeEntity;
import com.demandhub.demand.mapper.AssignmentMapper;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.mapper.DemandRelationMapper;
import com.demandhub.demand.mapper.DemandTypeMapper;
import com.demandhub.demand.statemachine.DemandEvent;
import com.demandhub.demand.statemachine.DemandStateMachine;
import com.demandhub.demand.statemachine.TransitionContext;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;

/**
 * M3 受理与分派：受理/退回/关闭/分派/领取/类型修正。
 * 领取并发：Redis 分布式锁（lock:demand:{id}，10s）+ 状态机乐观锁双保险（架构 4.3）。
 */
@Service
public class TriageService {

    private static final Duration CLAIM_LOCK_TTL = Duration.ofSeconds(10);

    private final DemandMapper demandMapper;
    private final DemandTypeMapper demandTypeMapper;
    private final AssignmentMapper assignmentMapper;
    private final DemandRelationMapper relationMapper;
    private final DemandStateMachine stateMachine;
    private final OrgScopeService orgScopeService;
    private final UserLookupService userLookupService;
    private final StringRedisTemplate redis;

    public TriageService(DemandMapper demandMapper, DemandTypeMapper demandTypeMapper,
                         AssignmentMapper assignmentMapper, DemandRelationMapper relationMapper,
                         DemandStateMachine stateMachine, OrgScopeService orgScopeService,
                         UserLookupService userLookupService, StringRedisTemplate redis) {
        this.demandMapper = demandMapper;
        this.demandTypeMapper = demandTypeMapper;
        this.assignmentMapper = assignmentMapper;
        this.relationMapper = relationMapper;
        this.stateMachine = stateMachine;
        this.orgScopeService = orgScopeService;
        this.userLookupService = userLookupService;
        this.redis = redis;
    }

    /** 受理通过 → TRIAGE（入需求池） */
    @Transactional(rollbackFor = Exception.class)
    public void accept(Long demandId, String comment) {
        CurrentUser user = requireLogin();
        DemandEntity demand = requireVisible(demandId);
        orgScopeService.requireManage(user, demand.getAssigneeOrgId());
        stateMachine.transition(demandId, DemandEvent.ACCEPT, user, TransitionContext.of(comment));
    }

    /** 退回补充 → NEED_INFO（说明必填） */
    @Transactional(rollbackFor = Exception.class)
    public void returnForInfo(Long demandId, String comment) {
        CurrentUser user = requireLogin();
        if (!StringUtils.hasText(comment)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "退回补充说明必填");
        }
        DemandEntity demand = requireVisible(demandId);
        orgScopeService.requireManage(user, demand.getAssigneeOrgId());
        stateMachine.transition(demandId, DemandEvent.RETURN, user, TransitionContext.of(comment.trim()));
    }

    /** 关闭（不受理/重复/其他，原因必填；重复可关联原需求） */
    @Transactional(rollbackFor = Exception.class)
    public void close(Long demandId, CloseRequest request) {
        CurrentUser user = requireLogin();
        if (!StringUtils.hasText(request.reason())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "关闭原因必填");
        }
        DemandEntity demand = requireVisible(demandId);
        orgScopeService.requireManage(user, demand.getAssigneeOrgId());
        stateMachine.transition(demandId, DemandEvent.CLOSE, user,
                TransitionContext.of(request.reason().trim()).withUpdater(d -> {
                    d.setClosedAt(LocalDateTime.now());
                    d.setCloseReason(request.reason().trim());
                }).putExtra("duplicateOfId", request.duplicateOfId()));
        if (request.duplicateOfId() != null) {
            DemandRelationEntity relation = new DemandRelationEntity();
            relation.setDemandId(demandId);
            relation.setRelatedDemandId(request.duplicateOfId());
            relation.setRelationType("DUPLICATE");
            try {
                relationMapper.insert(relation);
            } catch (Exception ignored) {
                // 已存在相同关联则跳过（唯一索引兜底）
            }
        }
    }

    /** 经理分派 → ANALYZING（乐观锁校验状态仍为 TRIAGE） */
    @Transactional(rollbackFor = Exception.class)
    public void assign(Long demandId, AssignRequest request) {
        CurrentUser user = requireLogin();
        if (request.assigneeId() == null) {
            throw new BizException(ErrorCode.PARAM_INVALID, "被分派人不能为空");
        }
        DemandEntity demand = requireVisible(demandId);
        orgScopeService.requireManage(user, demand.getAssigneeOrgId());
        if (!orgScopeService.userHasRoleInOrg(request.assigneeId(), "HANDLER", demand.getAssigneeOrgId())) {
            throw new BizException(ErrorCode.BIZ_ERROR, "被分派人不是本承接组织的处理人");
        }
        String assigneeName = userLookupService.nameOf(request.assigneeId());
        stateMachine.transition(demandId, DemandEvent.ASSIGN, user,
                TransitionContext.of(request.comment())
                        .putExtra("assigneeId", request.assigneeId())
                        .putExtra("assigneeName", assigneeName)
                        .withUpdater(d -> d.setAssigneeUserId(request.assigneeId())));
        AssignmentEntity assignment = new AssignmentEntity();
        assignment.setDemandId(demandId);
        assignment.setOrgId(demand.getAssigneeOrgId());
        assignment.setAssigneeId(request.assigneeId());
        assignment.setDispatcherId(user.getId());
        assignment.setAssignMode("DISPATCH");
        assignment.setStatus("PROCESSING");
        assignment.setAssignedAt(LocalDateTime.now());
        assignmentMapper.insert(assignment);
    }

    /**
     * 处理人领取 → ANALYZING。先抢先得：
     * 1) Redis 锁互斥；2) 状态前置校验；3) 状态机乐观锁落库兜底。
     */
    @Transactional(rollbackFor = Exception.class)
    public void claim(Long demandId) {
        CurrentUser user = requireLogin();
        String lockKey = "lock:demand:" + demandId;
        String lockValue = String.valueOf(user.getId());
        Boolean locked = redis.opsForValue().setIfAbsent(lockKey, lockValue, CLAIM_LOCK_TTL);
        if (!Boolean.TRUE.equals(locked)) {
            throw new BizException(ErrorCode.DEMAND_ALREADY_CLAIMED, "该需求正在被领取，请稍后重试");
        }
        try {
            DemandEntity demand = requireVisible(demandId);
            if (demand.getAssigneeUserId() != null) {
                throw new BizException(ErrorCode.DEMAND_ALREADY_CLAIMED);
            }
            if (!"TRIAGE".equals(demand.getStatus())) {
                throw new BizException(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅待分派状态的需求可领取");
            }
            if (!orgScopeService.canHandle(user, demand.getAssigneeOrgId())) {
                throw new BizException(ErrorCode.FORBIDDEN, "仅本承接组织的处理人可领取");
            }
            stateMachine.transition(demandId, DemandEvent.CLAIM, user,
                    TransitionContext.of("处理人领取")
                            .putExtra("assigneeId", user.getId())
                            .withUpdater(d -> d.setAssigneeUserId(user.getId())));
            AssignmentEntity assignment = new AssignmentEntity();
            assignment.setDemandId(demandId);
            assignment.setOrgId(demand.getAssigneeOrgId());
            assignment.setAssigneeId(user.getId());
            assignment.setAssignMode("CLAIM");
            assignment.setStatus("PROCESSING");
            assignment.setClaimedAt(LocalDateTime.now());
            assignmentMapper.insert(assignment);
        } finally {
            releaseLock(lockKey, lockValue);
        }
    }

    /** 类型修正（FR-M3-04，仅 EXECUTIVE）：修正后按新类型重新路由，全程留痕 */
    @Transactional(rollbackFor = Exception.class)
    public void changeType(Long demandId, ChangeTypeRequest request) {
        CurrentUser user = requireLogin();
        if (!StringUtils.hasText(request.newTypeCode())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "新需求类型不能为空");
        }
        DemandTypeEntity newType = demandTypeMapper.selectOne(new LambdaQueryWrapper<DemandTypeEntity>()
                .eq(DemandTypeEntity::getTypeCode, request.newTypeCode())
                .eq(DemandTypeEntity::getStatus, "ACTIVE"));
        if (newType == null) {
            throw new BizException(ErrorCode.DEMAND_TYPE_INVALID, "需求类型不存在或已停用: " + request.newTypeCode());
        }
        DemandEntity demand = requireVisible(demandId);
        if (newType.getTypeCode().equals(demand.getDemandTypeCode())) {
            throw new BizException(ErrorCode.BIZ_ERROR, "新类型与原类型相同");
        }
        String oldType = demand.getDemandTypeCode();
        Long oldOrg = demand.getAssigneeOrgId();
        stateMachine.transition(demandId, DemandEvent.CHANGE_TYPE, user,
                TransitionContext.of(StringUtils.hasText(request.comment()) ? request.comment() : "类型修正")
                        .putExtra("fromType", oldType)
                        .putExtra("toType", newType.getTypeCode())
                        .putExtra("fromOrgId", oldOrg)
                        .putExtra("toOrgId", newType.getDefaultOrgId())
                        .withUpdater(d -> {
                            d.setDemandTypeCode(newType.getTypeCode());
                            d.setSubtypeCode(null);
                            d.setAssigneeOrgId(newType.getDefaultOrgId());
                        }));
    }

    private void releaseLock(String lockKey, String lockValue) {
        // 仅释放自己的锁（值比对 + 删除原子化）
        String lua = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end";
        redis.execute(new DefaultRedisScript<>(lua, Long.class), List.of(lockKey), lockValue);
    }

    private DemandEntity requireVisible(Long demandId) {
        DemandEntity demand = demandMapper.selectById(demandId);
        if (demand == null) {
            throw new BizException(ErrorCode.DEMAND_NOT_FOUND, "需求不存在或无权限访问");
        }
        return demand;
    }

    private CurrentUser requireLogin() {
        CurrentUser user = UserContext.get();
        if (user == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        return user;
    }
}
