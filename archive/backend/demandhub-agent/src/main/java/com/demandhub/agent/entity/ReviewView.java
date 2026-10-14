package com.demandhub.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 评审意见只读视图（review 表，RAG 知识库内容拼装用）
 */
@Data
@TableName("review")
public class ReviewView implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private Long solutionId;

    private String reviewType;

    private Long reviewerId;

    private String conclusion;

    private String comment;

    private LocalDateTime reviewedAt;
}
