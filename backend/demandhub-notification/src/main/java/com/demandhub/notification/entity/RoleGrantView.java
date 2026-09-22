package com.demandhub.notification.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 业务角色授权只读视图（demand_role_grant，同库只读；接收人解析用）
 */
@Data
@TableName("demand_role_grant")
public class RoleGrantView implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 被授权用户（demand_user.id，OneID） */
    private Long demandUserId;

    /** 角色族：ADMIN/EXECUTIVE/MANAGER/HANDLER */
    private String roleCode;

    private Long orgId;

    private LocalDateTime effectiveFrom;

    private LocalDateTime effectiveTo;

    @TableLogic
    private Integer isDeleted;
}
