package com.demandhub.demand.mq;

import lombok.Data;

import java.io.Serializable;
import java.util.Map;

/**
 * 需求领域事件 MQ 报文（topic: demandhub-demand-event）。
 * 由状态机 Spring 事件在事务提交后转发，通知服务消费。
 * 字段为消费侧解析接收人/渲染模板所需的最小快照。
 */
@Data
public class DemandEventMessage implements Serializable {

    private Long demandId;

    private String demandNo;

    /** 状态机事件名（SUBMIT/ASSIGN/...）或 SLA_ALERT */
    private String event;

    private String fromStatus;

    private String toStatus;

    private Long operatorId;

    private String comment;

    private Map<String, Object> extra;

    // ---- 需求快照（转发时补充，避免消费侧回查） ----

    private String title;

    private String demandTypeCode;

    private Long submitterId;

    private Long actualDemanderId;

    private Long assigneeOrgId;

    private Long assigneeUserId;
}
