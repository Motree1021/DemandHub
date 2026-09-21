package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 方案表读写视图（solution，agent 模块在草稿确认时写入新版本）。
 * 写入逻辑对齐 demand 模块 SolutionService.create：版本号 = 当前最大 + 1，状态 DRAFT。
 */
@Data
@TableName("solution")
public class SolutionRowEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private Integer version;

    private Long authorId;

    private String specContent;

    private String solutionContent;

    private LocalDateTime planDeliveryAt;

    private LocalDateTime actualDeliveryAt;

    /** DRAFT / REVIEWING / APPROVED / REJECTED */
    private String status;

    private String remark;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
