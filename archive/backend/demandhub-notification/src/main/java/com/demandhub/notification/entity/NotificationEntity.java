package com.demandhub.notification.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 通知消息（notification）：一条接收人 × 渠道一行。
 * IN_APP 写入即送达（send_status=SENT）；WECOM 由 MQ 消费者推送后回写状态与 retry_count。
 */
@Data
@TableName("notification")
public class NotificationEntity implements Serializable {

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

    private LocalDateTime readAt;

    /** PENDING / SENT / FAILED */
    private String sendStatus;

    private Integer retryCount;

    private LocalDateTime createdAt;

    private LocalDateTime sentAt;
}
