package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 需求评论（comment，不可删除，仅可追加补充）
 */
@Data
@TableName("comment")
public class CommentEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private Long authorId;

    private String content;

    /** @人列表，逗号分隔用户数值 ID */
    private String mentionedUserIds;

    private LocalDateTime createdAt;
}
