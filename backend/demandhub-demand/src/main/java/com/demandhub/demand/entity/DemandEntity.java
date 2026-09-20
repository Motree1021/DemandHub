package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import com.demandhub.common.entity.BaseEntity;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

/**
 * 需求基表（demand）
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("demand")
public class DemandEntity extends BaseEntity {

    /** 业务编号 TECH-20260919-001 */
    private String demandNo;

    private String title;

    private String demandTypeCode;

    private String subtypeCode;

    private String content;

    /** NORMAL / URGENT / CRITICAL */
    private String urgency;

    /** 主状态，见 DemandStatus（ON_HOLD 为叠加态不入此列） */
    private String status;

    /** 挂起叠加态：0 正常 1 已挂起 */
    private Integer onHold;

    private String holdReason;

    /** 挂起前主状态，恢复时回填 */
    private String holdSnapshotStatus;

    /** 提报人（代办人）用户数值 ID */
    private Long submitterId;

    /** 实际需求人（代办提报时非空） */
    private Long actualDemanderId;

    private Long submitterOrgId;

    private String submitterOrgSnapshot;

    /** WEB / WECOM_H5 / WECOM_BOT / VOICE */
    private String channel;

    /** 承接组织 */
    private Long assigneeOrgId;

    /** 当前处理人 */
    private Long assigneeUserId;

    private Long projectId;

    private LocalDateTime expectDeliveryAt;

    private LocalDateTime actualDeliveryAt;

    private LocalDateTime submittedAt;

    private LocalDateTime closedAt;

    private String closeReason;

    private Integer qualityScore;

    private Integer satisfactionScore;
}
