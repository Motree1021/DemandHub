package com.demandhub.notification.mq;

import lombok.Data;

import java.io.Serializable;
import java.util.Map;

/**
 * 需求领域事件 MQ 报文（与 demand 服务 DemandEventMessage 同构）。
 */
@Data
public class DemandEventMessage implements Serializable {

    private Long demandId;

    private String demandNo;

    private String event;

    private String fromStatus;

    private String toStatus;

    private Long operatorId;

    private String comment;

    private Map<String, Object> extra;

    private String title;

    private String demandTypeCode;

    private Long submitterId;

    private Long actualDemanderId;

    private Long assigneeOrgId;

    private Long assigneeUserId;
}
