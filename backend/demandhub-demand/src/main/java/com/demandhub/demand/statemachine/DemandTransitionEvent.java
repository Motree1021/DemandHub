package com.demandhub.demand.statemachine;

import lombok.Getter;

import java.util.Map;

/**
 * 需求流转领域事件（Spring ApplicationEvent）。
 * 流转成功后发布，阶段 4 通知服务以 @TransactionalEventListener 订阅，不阻塞主流程。
 */
@Getter
public class DemandTransitionEvent {

    private final Long demandId;

    private final String demandNo;

    private final String event;

    private final String fromStatus;

    private final String toStatus;

    private final Long operatorId;

    /** 操作意见（退回原因、关闭原因、挂起原因等），供通知模板 ${comment} 变量使用 */
    private final String comment;

    private final Map<String, Object> extra;

    public DemandTransitionEvent(Long demandId, String demandNo, String event,
                                 String fromStatus, String toStatus, Long operatorId,
                                 Map<String, Object> extra) {
        this(demandId, demandNo, event, fromStatus, toStatus, operatorId, null, extra);
    }

    public DemandTransitionEvent(Long demandId, String demandNo, String event,
                                 String fromStatus, String toStatus, Long operatorId,
                                 String comment, Map<String, Object> extra) {
        this.demandId = demandId;
        this.demandNo = demandNo;
        this.event = event;
        this.fromStatus = fromStatus;
        this.toStatus = toStatus;
        this.operatorId = operatorId;
        this.comment = comment;
        this.extra = extra;
    }
}
