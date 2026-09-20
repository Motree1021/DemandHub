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

    /** 全部业务角色（提报人/处理人/经理/需求管理者） */
    public static final Set<String> BIZ_ALL = Set.of("REPORTER", "HANDLER", "DEMAND_MANAGER", "EXECUTIVE");
    /** 需求经理 + 需求管理者 */
    public static final Set<String> MANAGER = Set.of("DEMAND_MANAGER", "EXECUTIVE");
    /** 处理人（经理可代办处理动作的场景由业务层另行放行） */
    public static final Set<String> HANDLER = Set.of("HANDLER");

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
        rules.add(new TransitionRule(DemandStatus.DRAFT, DemandEvent.SUBMIT, DemandStatus.SUBMITTED, BIZ_ALL, "提报人提交"));
        rules.add(new TransitionRule(DemandStatus.SUBMITTED, DemandEvent.WITHDRAW, DemandStatus.CLOSED, BIZ_ALL, "提报人撤销（仅 SUBMITTED）"));
        rules.add(new TransitionRule(DemandStatus.SUBMITTED, DemandEvent.ACCEPT, DemandStatus.TRIAGE, MANAGER, "经理受理通过入需求池"));
        rules.add(new TransitionRule(DemandStatus.SUBMITTED, DemandEvent.RETURN, DemandStatus.NEED_INFO, MANAGER, "退回补充"));
        rules.add(new TransitionRule(DemandStatus.SUBMITTED, DemandEvent.CLOSE, DemandStatus.CLOSED, MANAGER, "不受理/重复关闭"));
        rules.add(new TransitionRule(DemandStatus.NEED_INFO, DemandEvent.SUBMIT, DemandStatus.SUBMITTED, BIZ_ALL, "提报人补充后重新提交"));
        rules.add(new TransitionRule(DemandStatus.TRIAGE, DemandEvent.ASSIGN, DemandStatus.ANALYZING, MANAGER, "经理分派"));
        rules.add(new TransitionRule(DemandStatus.TRIAGE, DemandEvent.CLAIM, DemandStatus.ANALYZING, HANDLER, "处理人领取"));
        rules.add(new TransitionRule(DemandStatus.TRIAGE, DemandEvent.CLOSE, DemandStatus.CLOSED, MANAGER, "需求池关闭"));
        rules.add(new TransitionRule(DemandStatus.ANALYZING, DemandEvent.SUBMIT_REVIEW, DemandStatus.SOLUTION_REVIEW, BIZ_ALL, "提交方案评审"));
        rules.add(new TransitionRule(DemandStatus.SOLUTION_REVIEW, DemandEvent.REVIEW_PASS, DemandStatus.CONFIRMED, MANAGER, "方案评审通过"));
        rules.add(new TransitionRule(DemandStatus.SOLUTION_REVIEW, DemandEvent.REVIEW_REJECT, DemandStatus.ANALYZING, MANAGER, "方案评审打回"));
        rules.add(new TransitionRule(DemandStatus.CONFIRMED, DemandEvent.START, DemandStatus.IN_PROGRESS, HANDLER, "开始处理"));
        rules.add(new TransitionRule(DemandStatus.IN_PROGRESS, DemandEvent.SUBMIT_ACCEPTANCE, DemandStatus.ACCEPTANCE, HANDLER, "提交验收"));
        rules.add(new TransitionRule(DemandStatus.ACCEPTANCE, DemandEvent.ACCEPT_PASS, DemandStatus.DONE, BIZ_ALL, "验收通过（提报人，归属由业务层校验）"));
        rules.add(new TransitionRule(DemandStatus.ACCEPTANCE, DemandEvent.ACCEPT_REJECT, DemandStatus.IN_PROGRESS, BIZ_ALL, "验收打回（提报人，归属由业务层校验）"));
        // 类型修正：主状态不变，仅 EXECUTIVE，修正后重新路由
        for (DemandStatus s : List.of(DemandStatus.SUBMITTED, DemandStatus.NEED_INFO, DemandStatus.TRIAGE,
                DemandStatus.ANALYZING, DemandStatus.SOLUTION_REVIEW, DemandStatus.CONFIRMED,
                DemandStatus.IN_PROGRESS, DemandStatus.ACCEPTANCE)) {
            rules.add(new TransitionRule(s, DemandEvent.CHANGE_TYPE, null, Set.of("EXECUTIVE"), "类型修正（状态不变，重新路由）"));
        }
        // 挂起叠加态：任意在途态可挂起；挂起后仅可恢复
        for (DemandStatus s : List.of(DemandStatus.ANALYZING, DemandStatus.SOLUTION_REVIEW,
                DemandStatus.CONFIRMED, DemandStatus.IN_PROGRESS)) {
            rules.add(new TransitionRule(s, DemandEvent.HOLD, DemandStatus.ON_HOLD, BIZ_ALL, "挂起（叠加态）"));
        }
        rules.add(new TransitionRule(DemandStatus.ON_HOLD, DemandEvent.RESUME, null, BIZ_ALL, "恢复到挂起前主状态"));
        return rules;
    }
}
