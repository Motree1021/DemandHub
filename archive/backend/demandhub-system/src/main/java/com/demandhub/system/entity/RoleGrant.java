package com.demandhub.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 业务角色本地授权（demand_role_grant）：角色族 × 组织子树 × 需求类型集合。
 * 角色码：ADMIN/EXECUTIVE/MANAGER/HANDLER；"管哪类"由 demandTypeScope 表达，"管哪片"由 orgId 子树表达。
 */
@Data
@TableName("demand_role_grant")
public class RoleGrant implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 被授权用户（demand_user.id，OneID） */
    private Long demandUserId;

    /** 角色族：ADMIN/EXECUTIVE/MANAGER/HANDLER */
    private String roleCode;

    /** 授权组织范围（demand_org.id），默认覆盖该组织子树；NULL 表示不限组织 */
    private Long orgId;

    /** 需求类型集合（逗号多选），可覆盖角色默认值；NULL 表示角色默认 */
    private String demandTypeScope;

    private LocalDateTime effectiveFrom;

    private LocalDateTime effectiveTo;

    /** 授予人（demand_user.id） */
    private Long grantedBy;

    @TableLogic
    private Integer isDeleted;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
