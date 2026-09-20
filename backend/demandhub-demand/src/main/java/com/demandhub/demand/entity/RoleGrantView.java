package com.demandhub.demand.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableLogic;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 业务角色授权只读视图（demand_role_grant，同库只读；写入操作在 demandhub-system）
 */
@Data
@TableName("demand_role_grant")
public class RoleGrantView implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    private String userId;

    private String roleCode;

    private Long orgId;

    private String demandTypeScope;

    private LocalDateTime effectiveFrom;

    private LocalDateTime effectiveTo;

    @TableLogic
    private Integer isDeleted;
}
