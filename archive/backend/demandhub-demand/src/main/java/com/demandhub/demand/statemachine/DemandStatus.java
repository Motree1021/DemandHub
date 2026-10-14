package com.demandhub.demand.statemachine;

/**
 * 需求主状态枚举（SRS 5.1，全类型共用）。
 * ON_HOLD 为叠加态：不写入 demand.status，由 on_hold/hold_reason/hold_snapshot_status 表达，
 * 仅在流转日志与规则匹配中作为“当前态”出现。
 */
public enum DemandStatus {

    DRAFT("草稿"),
    SUBMITTED("待受理"),
    NEED_INFO("待补充"),
    TRIAGE("待分派/待领取"),
    ANALYZING("分析中"),
    SOLUTION_REVIEW("方案待评审"),
    CONFIRMED("已确认/已排期"),
    IN_PROGRESS("处理中"),
    ACCEPTANCE("待验收"),
    DONE("已完成"),
    CLOSED("已关闭"),
    ON_HOLD("挂起（叠加态）");

    private final String label;

    DemandStatus(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }

    /** 终态不可再流转 */
    public boolean isTerminal() {
        return this == DONE || this == CLOSED;
    }
}
