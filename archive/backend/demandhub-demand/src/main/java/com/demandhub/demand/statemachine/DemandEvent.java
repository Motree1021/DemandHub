package com.demandhub.demand.statemachine;

/**
 * 状态机事件枚举（SRS 5.2 合法流转表）。
 */
public enum DemandEvent {

    SUBMIT("提交需求"),
    WITHDRAW("提报人撤销"),
    ACCEPT("经理受理"),
    RETURN("退回补充"),
    CLOSE("关闭"),
    ASSIGN("经理分派"),
    CLAIM("处理人领取"),
    CHANGE_TYPE("类型修正"),
    SUBMIT_REVIEW("提交方案评审"),
    REVIEW_PASS("评审通过"),
    REVIEW_REJECT("评审打回"),
    START("开始处理"),
    SUBMIT_ACCEPTANCE("提交验收"),
    ACCEPT_PASS("验收通过"),
    ACCEPT_REJECT("验收打回"),
    HOLD("挂起"),
    RESUME("恢复");

    private final String label;

    DemandEvent(String label) {
        this.label = label;
    }

    public String getLabel() {
        return label;
    }
}
