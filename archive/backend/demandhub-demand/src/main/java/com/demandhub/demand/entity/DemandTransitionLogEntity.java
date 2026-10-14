package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 需求流转日志（demand_transition_log，只增不改）
 */
@Data
@TableName("demand_transition_log")
public class DemandTransitionLogEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private String fromStatus;

    private String toStatus;

    /** 事件（DemandEvent），如 SUBMIT/ACCEPT/HOLD */
    private String action;

    private Long operatorId;

    private String operatorSnapshot;

    private String comment;

    /** 扩展信息（JSON），如类型修正前后、分派人 */
    private String extra;

    private LocalDateTime createdAt;
}
