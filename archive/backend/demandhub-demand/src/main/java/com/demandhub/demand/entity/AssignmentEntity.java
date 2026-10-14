package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 处理任务分派（assignment）
 */
@Data
@TableName("assignment")
public class AssignmentEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    /** 承接组织 */
    private Long orgId;

    /** 处理人（空 = 待领取池） */
    private Long assigneeId;

    /** 分发人 */
    private Long dispatcherId;

    /** DISPATCH / CLAIM */
    private String assignMode;

    /** OPEN / PROCESSING / DONE */
    private String status;

    private LocalDateTime assignedAt;

    private LocalDateTime claimedAt;

    private LocalDateTime finishedAt;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
