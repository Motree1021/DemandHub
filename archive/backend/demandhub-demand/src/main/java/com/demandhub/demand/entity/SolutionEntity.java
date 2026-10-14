package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 需求方案（solution，多版本，uk: demand_id + version）
 */
@Data
@TableName("solution")
public class SolutionEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private Integer version;

    private Long authorId;

    /** 需求规约 */
    private String specContent;

    /** 方案内容 */
    private String solutionContent;

    private LocalDateTime planDeliveryAt;

    private LocalDateTime actualDeliveryAt;

    /** DRAFT / REVIEWING / APPROVED / REJECTED */
    private String status;

    private String remark;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
