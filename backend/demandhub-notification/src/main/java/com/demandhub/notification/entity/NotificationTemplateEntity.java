package com.demandhub.notification.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 通知模板（notification_template，M8：标题/正文支持 ${var} 占位）
 */
@Data
@TableName("notification_template")
public class NotificationTemplateEntity implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 模板编码（按事件），如 SUBMIT/ASSIGN/SLA_ALERT */
    private String templateCode;

    private String templateName;

    private String titleTemplate;

    private String contentTemplate;

    private String status;

    private String remark;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
