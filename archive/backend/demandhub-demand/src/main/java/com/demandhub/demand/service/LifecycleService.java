package com.demandhub.demand.service;

import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.mapper.DemandMapper;
import com.demandhub.demand.statemachine.DemandEvent;
import com.demandhub.demand.statemachine.DemandStateMachine;
import com.demandhub.demand.statemachine.TransitionContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

/**
 * M4 处理生命周期动作：开始处理、挂起/恢复（叠加态，原因必填，恢复回挂起前主状态）。
 */
@Service
public class LifecycleService {

    private final DemandMapper demandMapper;
    private final DemandStateMachine stateMachine;
    private final OrgScopeService orgScopeService;

    public LifecycleService(DemandMapper demandMapper, DemandStateMachine stateMachine,
                            OrgScopeService orgScopeService) {
        this.demandMapper = demandMapper;
        this.stateMachine = stateMachine;
        this.orgScopeService = orgScopeService;
    }

    /** 开始处理：CONFIRMED → IN_PROGRESS（仅当前处理人） */
    @Transactional(rollbackFor = Exception.class)
    public void start(Long demandId) {
        CurrentUser user = requireLogin();
        DemandEntity demand = requireVisible(demandId);
        requireAssignee(user, demand);
        stateMachine.transition(demandId, DemandEvent.START, user, TransitionContext.of("开始处理"));
    }

    /** 挂起（FR-M4-06）：在途态 → 主态+ON_HOLD，原因必填；处理人本人或本组织经理可操作 */
    @Transactional(rollbackFor = Exception.class)
    public void hold(Long demandId, String reason) {
        CurrentUser user = requireLogin();
        if (!StringUtils.hasText(reason)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "挂起原因必填");
        }
        DemandEntity demand = requireVisible(demandId);
        requireAssigneeOrManager(user, demand);
        stateMachine.transition(demandId, DemandEvent.HOLD, user, TransitionContext.of(reason.trim()));
    }

    /** 恢复：ON_HOLD → 挂起前主状态 */
    @Transactional(rollbackFor = Exception.class)
    public void resume(Long demandId) {
        CurrentUser user = requireLogin();
        DemandEntity demand = requireVisible(demandId);
        requireAssigneeOrManager(user, demand);
        stateMachine.transition(demandId, DemandEvent.RESUME, user, TransitionContext.of("恢复处理"));
    }

    private void requireAssignee(CurrentUser user, DemandEntity demand) {
        if (!user.getId().equals(demand.getAssigneeUserId())) {
            throw new BizException(ErrorCode.FORBIDDEN, "仅当前处理人可操作");
        }
    }

    private void requireAssigneeOrManager(CurrentUser user, DemandEntity demand) {
        if (user.getId().equals(demand.getAssigneeUserId())) {
            return;
        }
        if (orgScopeService.canManage(user, demand.getAssigneeOrgId(), demand.getDemandTypeCode())) {
            return;
        }
        throw new BizException(ErrorCode.FORBIDDEN, "仅当前处理人或本类型本组织经理可操作");
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
