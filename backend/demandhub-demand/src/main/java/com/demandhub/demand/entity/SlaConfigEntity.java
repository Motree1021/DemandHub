package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * SLA 停留时长配置（sla_config，按 类型 × 状态）
 */
@Data
@TableName("sla_config")
public class SlaConfigEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String demandTypeCode;

    /** 停留状态，如 SUBMITTED/TRIAGE/IN_PROGRESS */
    private String status;

    /** 黄色预警阈值（分钟） */
    private Integer warnMinutes;

    /** 红色告警阈值（分钟） */
    private Integer maxMinutes;

    private Integer enabled;

    private String remark;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
