package com.demandhub.demand.statemachine;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 状态机配置（架构 4.1：配置化而非 if-else 硬编码）。
 * - 代码内置 DEFAULT 流转表（SRS 5.2）作为兜底；
 * - M8 状态机配置管理可把 DB 配置热加载进来（{@link #refreshDbTables}），不重启即时生效；
 * - DB 中同 key 配置覆盖代码默认，未配置的 key 回落 DEFAULT。
 */
@Component
public class StateMachineConfig {

    public static final String DEFAULT_KEY = "DEFAULT";

    /**
     * 提报人动作（提交/撤销/验收）：不设角色限制——角色族模型不设提报人角色，
     * 任何登录用户可提报，归属（提报人本人/实际需求人）由业务层校验（SRS 5.2）。
     */
    public static final Set<String> ANY_AUTHENTICATED = Set.of();
    /** 需求经理（受理/退回/关闭/分派/评审；类型与组织双重命中由业务层 OrgScopeService 校验） */
    public static final Set<String> MANAGER = Set.of("MANAGER");
    /** 处理人（领取/开始处理/提交验收；处理人本人归属由业务层校验） */
    public static final Set<String> HANDLER = Set.of("HANDLER");
    /** 处理人或经理（提交方案评审、挂起/恢复——经理可代办处理动作的场景由业务层放行） */
    public static final Set<String> HANDLER_OR_MANAGER = Set.of("HANDLER", "MANAGER");
    /** 需求管理者（类型修正，SRS 权限矩阵：仅 EXECUTIVE） */
    public static final Set<String> EXECUTIVE_ONLY = Set.of("EXECUTIVE");

    private final List<TransitionRule> defaultTable;

    /** DB 热加载的流转表（key → 规则列表），整体不可变替换，读写无锁 */
    private volatile Map<String, List<TransitionRule>> dbTables = Map.of();

    public StateMachineConfig() {
        this.defaultTable = buildDefault();
    }

    public List<TransitionRule> rules(String stateMachineKey) {
        List<TransitionRule> rules = dbTables.get(stateMachineKey);
        if (rules != null) {
            return rules;
        }
        return DEFAULT_KEY.equals(stateMachineKey) ? defaultTable
                : dbTables.getOrDefault(DEFAULT_KEY, defaultTable);
    }

    /** 整体替换 DB 配置（由 StateMachineConfigService 定时/变更后触发） */
    public void refreshDbTables(Map<String, List<TransitionRule>> tables) {
        this.dbTables = tables == null ? Map.of() : Map.copyOf(tables);
    }

    private static List<TransitionRule> buildDefault() {
        List<TransitionRule> rules = new ArrayList<>();
        // 主流程
        rules.add(new TransitionRule(DemandStatus.DRAFT, DemandEvent.SUBMIT, DemandStatus.SUBMITTED, ANY_AUTHENTICATED, "提报人提交"));
        rules.add(new TransitionRule(DemandStatus.SUBMITTED, DemandEvent.WITHDRAW, DemandStatus.CLOSED, ANY_AUTHENTICATED, "提报人撤销（仅 SUBMITTED）"));
        rules.add(new TransitionRule(DemandStatus.SUBMITTED, DemandEvent.ACCEPT, DemandStatus.TRIAGE, MANAGER, "经理受理通过入需求池"));
        rules.add(new TransitionRule(DemandStatus.SUBMITTED, DemandEvent.RETURN, DemandStatus.NEED_INFO, MANAGER, "退回补充"));
        rules.add(new TransitionRule(DemandStatus.SUBMITTED, DemandEvent.CLOSE, DemandStatus.CLOSED, MANAGER, "不受理/重复关闭"));
        rules.add(new TransitionRule(DemandStatus.NEED_INFO, DemandEvent.SUBMIT, DemandStatus.SUBMITTED, ANY_AUTHENTICATED, "提报人补充后重新提交"));
        rules.add(new TransitionRule(DemandStatus.TRIAGE, DemandEvent.ASSIGN, DemandStatus.ANALYZING, MANAGER, "经理分派"));
        rules.add(new TransitionRule(DemandStatus.TRIAGE, DemandEvent.CLAIM, DemandStatus.ANALYZING, HANDLER, "处理人领取"));
        rules.add(new TransitionRule(DemandStatus.TRIAGE, DemandEvent.CLOSE, DemandStatus.CLOSED, MANAGER, "需求池关闭"));
        rules.add(new TransitionRule(DemandStatus.ANALYZING, DemandEvent.SUBMIT_REVIEW, DemandStatus.SOLUTION_REVIEW, HANDLER_OR_MANAGER, "提交方案评审"));
        rules.add(new TransitionRule(DemandStatus.SOLUTION_REVIEW, DemandEvent.REVIEW_PASS, DemandStatus.CONFIRMED, MANAGER, "方案评审通过"));
        rules.add(new TransitionRule(DemandStatus.SOLUTION_REVIEW, DemandEvent.REVIEW_REJECT, DemandStatus.ANALYZING, MANAGER, "方案评审打回"));
        rules.add(new TransitionRule(DemandStatus.CONFIRMED, DemandEvent.START, DemandStatus.IN_PROGRESS, HANDLER, "开始处理"));
        rules.add(new TransitionRule(DemandStatus.IN_PROGRESS, DemandEvent.SUBMIT_ACCEPTANCE, DemandStatus.ACCEPTANCE, HANDLER, "提交验收"));
        rules.add(new TransitionRule(DemandStatus.ACCEPTANCE, DemandEvent.ACCEPT_PASS, DemandStatus.DONE, ANY_AUTHENTICATED, "验收通过（提报人，归属由业务层校验）"));
        rules.add(new TransitionRule(DemandStatus.ACCEPTANCE, DemandEvent.ACCEPT_REJECT, DemandStatus.IN_PROGRESS, ANY_AUTHENTICATED, "验收打回（提报人，归属由业务层校验）"));
        // 类型修正：主状态不变，仅 EXECUTIVE，修正后重新路由
        for (DemandStatus s : List.of(DemandStatus.SUBMITTED, DemandStatus.NEED_INFO, DemandStatus.TRIAGE,
                DemandStatus.ANALYZING, DemandStatus.SOLUTION_REVIEW, DemandStatus.CONFIRMED,
                DemandStatus.IN_PROGRESS, DemandStatus.ACCEPTANCE)) {
            rules.add(new TransitionRule(s, DemandEvent.CHANGE_TYPE, null, EXECUTIVE_ONLY, "类型修正（状态不变，重新路由）"));
        }
        // 挂起叠加态：任意在途态可挂起；挂起后仅可恢复
        for (DemandStatus s : List.of(DemandStatus.ANALYZING, DemandStatus.SOLUTION_REVIEW,
                DemandStatus.CONFIRMED, DemandStatus.IN_PROGRESS)) {
            rules.add(new TransitionRule(s, DemandEvent.HOLD, DemandStatus.ON_HOLD, HANDLER_OR_MANAGER, "挂起（叠加态）"));
        }
        rules.add(new TransitionRule(DemandStatus.ON_HOLD, DemandEvent.RESUME, null, HANDLER_OR_MANAGER, "恢复到挂起前主状态"));
        return rules;
    }
}
