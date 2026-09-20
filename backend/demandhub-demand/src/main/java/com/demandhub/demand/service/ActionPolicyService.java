package com.demandhub.demand.service;

import com.demandhub.common.context.CurrentUser;
import com.demandhub.demand.entity.DemandEntity;
import com.demandhub.demand.statemachine.DemandEvent;
import com.demandhub.demand.statemachine.DemandStateMachine;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * 详情页“可用操作列表”策略：由状态机规则（canTransit）+ 归属/组织校验推导，前后端按钮显隐一致。
 */
@Service
public class ActionPolicyService {

    private final DemandStateMachine stateMachine;
    private final OrgScopeService orgScopeService;

    public ActionPolicyService(DemandStateMachine stateMachine, OrgScopeService orgScopeService) {
        this.stateMachine = stateMachine;
        this.orgScopeService = orgScopeService;
    }

    public List<String> availableActions(DemandEntity d, CurrentUser u) {
        List<String> actions = new ArrayList<>();
        if (d == null || u == null) {
            return actions;
        }
        boolean mine = u.getId().equals(d.getSubmitterId()) || Objects.equals(u.getId(), d.getActualDemanderId());
        boolean assignee = Objects.equals(u.getId(), d.getAssigneeUserId());
        boolean manager = orgScopeService.canManage(u, d.getAssigneeOrgId());
        boolean handlerInOrg = orgScopeService.canHandle(u, d.getAssigneeOrgId());
        boolean terminal = "DONE".equals(d.getStatus()) || "CLOSED".equals(d.getStatus());

        if (mine && can(d, DemandEvent.WITHDRAW, u)) {
            actions.add("WITHDRAW");
        }
        if (mine && "NEED_INFO".equals(d.getStatus()) && can(d, DemandEvent.SUBMIT, u)) {
            actions.add("RESUBMIT");
        }
        if (manager) {
            if (can(d, DemandEvent.ACCEPT, u)) {
                actions.add("ACCEPT");
            }
            if (can(d, DemandEvent.RETURN, u)) {
                actions.add("RETURN");
            }
            if (can(d, DemandEvent.CLOSE, u)) {
                actions.add("CLOSE");
            }
            if (can(d, DemandEvent.ASSIGN, u)) {
                actions.add("ASSIGN");
            }
            if (can(d, DemandEvent.REVIEW_PASS, u)) {
                actions.add("REVIEW");
            }
        }
        if (handlerInOrg && can(d, DemandEvent.CLAIM, u)) {
            actions.add("CLAIM");
        }
        if (can(d, DemandEvent.CHANGE_TYPE, u)) {
            actions.add("CHANGE_TYPE");
        }
        if ((assignee || manager) && can(d, DemandEvent.SUBMIT_REVIEW, u)) {
            actions.add("SUBMIT_SOLUTION");
        }
        if (assignee && can(d, DemandEvent.START, u)) {
            actions.add("START");
        }
        if ((assignee || manager) && can(d, DemandEvent.HOLD, u)) {
            actions.add("HOLD");
        }
        if ((assignee || manager) && can(d, DemandEvent.RESUME, u)) {
            actions.add("RESUME");
        }
        if (assignee && can(d, DemandEvent.SUBMIT_ACCEPTANCE, u)) {
            actions.add("SUBMIT_ACCEPTANCE");
        }
        if (mine && can(d, DemandEvent.ACCEPT_PASS, u)) {
            actions.add("ACCEPTANCE_REVIEW");
        }
        // 协作类动作（终态前可用）
        if (!terminal) {
            actions.add("COMMENT");
            actions.add("RELATE");
            if (assignee || manager) {
                actions.add("SPLIT");
            }
            if (assignee) {
                actions.add("EFFORT");
            }
        }
        return actions;
    }

    private boolean can(DemandEntity d, DemandEvent event, CurrentUser u) {
        return stateMachine.canTransit(d, event, u);
    }
}
