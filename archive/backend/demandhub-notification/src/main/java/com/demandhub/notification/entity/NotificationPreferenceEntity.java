package com.demandhub.notification.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 用户通知偏好（notification_preference）：无记录 = 默认开启；待办提醒 TODO 不可关闭不落库。
 */
@Data
@TableName("notification_preference")
public class NotificationPreferenceEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 用户数值 ID（demand_user_snapshot.id） */
    private Long userId;

    /** STATUS_CHANGE/MENTION/ASSIGN/REVIEW_REQUEST/ACCEPTANCE_REQUEST/SLA_ALERT */
    private String notifyType;

    private Integer enabled;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
