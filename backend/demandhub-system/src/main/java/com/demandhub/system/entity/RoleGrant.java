package com.demandhub.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 业务角色本地授权（demand_role_grant）：身份主数据在外，业务授权在内
 */
@Data
@TableName("demand_role_grant")
public class RoleGrant implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 权限中心用户唯一 ID */
    private String userId;

    /** ADMIN/EXECUTIVE/DEMAND_MANAGER/HANDLER/REPORTER */
    private String roleCode;

    /** 授权组织范围（权限中心 org_id），默认覆盖该组织子树；NULL 表示不限组织 */
    private Long orgId;

    /** 需求类型范围（逗号分隔），可覆盖角色默认值；NULL 表示角色默认 */
    private String demandTypeScope;

    private LocalDateTime effectiveFrom;

    private LocalDateTime effectiveTo;

    private String grantedBy;

    @TableLogic
    private Integer isDeleted;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
