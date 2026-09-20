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
 * 需求日统计预聚合（demand_stat_daily，架构 4.6：定时任务增量刷新）
 */
@Data
@TableName("demand_stat_daily")
public class DemandStatDailyEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private LocalDate statDate;

    private String demandTypeCode;

    private Long assigneeOrgId;

    private Long reporterOrgId;

    private String status;

    private Integer cnt;

    private BigDecimal avgCycleHours;

    private LocalDateTime updatedAt;
}
