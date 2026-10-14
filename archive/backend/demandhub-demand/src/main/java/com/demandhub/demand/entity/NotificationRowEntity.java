package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 通知表直写实体（notification，M6 报表就绪通知）。
 * 跨服务同库场景下由 demand 模块直接落 IN_APP 行（写入即送达），
 * 与 notification 服务写入的行结构保持一致。
 */
@Data
@TableName("notification")
public class NotificationRowEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long demandId;

    private Long receiverId;

    /** IN_APP / WECOM */
    private String channel;

    private String templateCode;

    private String title;

    private String content;

    private String link;

    private Integer isRead;

    private java.time.LocalDateTime readAt;

    /** PENDING / SENT / FAILED */
    private String sendStatus;

    private Integer retryCount;

    private LocalDateTime createdAt;

    private LocalDateTime sentAt;
}
