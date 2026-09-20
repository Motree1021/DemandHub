package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 需求草稿（demand_draft）
 */
@Data
@TableName("demand_draft")
public class DemandDraftEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private String channel;

    /** Agent 对话记录（JSON） */
    private String conversation;

    private String voiceTranscript;

    /** 已回填的表单字段（JSON） */
    private String formPayload;

    /** 转化后的需求 id（1:1） */
    private Long convertedDemandId;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
