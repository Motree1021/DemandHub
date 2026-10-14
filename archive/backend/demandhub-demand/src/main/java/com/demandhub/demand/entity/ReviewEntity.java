package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 评审 / 验收记录（review）
 */
@Data
@TableName("review")
public class ReviewEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    /** 关联方案（验收时为空） */
    private Long solutionId;

    /** SOLUTION / ACCEPTANCE */
    private String reviewType;

    private Long reviewerId;

    /** PASS / REJECT */
    private String conclusion;

    /** 1-5 */
    private Integer qualityScore;

    private String comment;

    private LocalDateTime reviewedAt;
}
