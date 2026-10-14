package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * 工时记录（effort_log）
 */
@Data
@TableName("effort_log")
public class EffortLogEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private Long userId;

    private BigDecimal hours;

    private LocalDate workDate;

    private String description;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
