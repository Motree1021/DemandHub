package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 附件（attachment，通用挂接 DEMAND/SOLUTION/COMMENT/DRAFT）
 */
@Data
@TableName("attachment")
public class AttachmentEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** DEMAND / SOLUTION / COMMENT / DRAFT */
    private String bizType;

    private Long bizId;

    private String fileName;

    /** 对象存储路径 */
    private String filePath;

    private Long fileSize;

    private String mimeType;

    private String ext;

    /** 语音转写文本 */
    private String transcript;

    private Long uploadedBy;

    private LocalDateTime createdAt;
}
