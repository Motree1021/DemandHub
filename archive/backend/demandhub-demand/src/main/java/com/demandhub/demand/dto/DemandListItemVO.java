package com.demandhub.demand.dto;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 需求列表项（带姓名/组织名拼装）
 */
@Data
public class DemandListItemVO {

    private Long id;

    private String demandNo;

    private String title;

    private String demandTypeCode;

    private String typeName;

    private String subtypeCode;

    private String urgency;

    private String status;

    private Integer onHold;

    private Long submitterId;

    private String submitterName;

    private Long actualDemanderId;

    /** 提报渠道（WEB/CHUANGJIN_LS 等） */
    private String channel;

    private Long submitterOrgId;

    private Long assigneeOrgId;

    private String assigneeOrgName;

    private Long assigneeUserId;

    private String assigneeUserName;

    private LocalDateTime expectDeliveryAt;

    private LocalDateTime submittedAt;

    private LocalDateTime closedAt;

    private String closeReason;

    private Integer qualityScore;

    private Integer satisfactionScore;

    private LocalDateTime createdAt;
}
