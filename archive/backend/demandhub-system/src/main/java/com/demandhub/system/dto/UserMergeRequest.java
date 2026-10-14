package com.demandhub.system.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.io.Serializable;

/**
 * 用户合并请求（FR-M1-01，管理端合并对话框）。
 * 合并前应先调 GET /system/user/merge/preview 做影响预览。
 */
@Data
public class UserMergeRequest implements Serializable {

    /** 被合并（废弃）的用户 */
    @NotNull(message = "源用户不能为空")
    private Long sourceUserId;

    /** 保留的目标用户（须 ACTIVE） */
    @NotNull(message = "目标用户不能为空")
    private Long targetUserId;
}
