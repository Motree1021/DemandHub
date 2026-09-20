package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.TableName;
import com.demandhub.common.entity.BaseEntity;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

/**
 * 需求基表（demand）：阶段 2 仅用于数据权限过滤与越权用例自测，提报/流转在 M2+ 实现
 */
@Data
@EqualsAndHashCode(callSuper = true)
@TableName("demand")
public class DemandEntity extends BaseEntity {

    private String demandNo;

    private String title;

    private String demandTypeCode;

    private String urgency;

    private String status;

    /** 提报人（用户镜像数值 ID） */
    private Long submitterId;

    private Long submitterOrgId;

    /** 承接组织 */
    private Long assigneeOrgId;

    private Long assigneeUserId;

    private LocalDateTime submittedAt;
}
