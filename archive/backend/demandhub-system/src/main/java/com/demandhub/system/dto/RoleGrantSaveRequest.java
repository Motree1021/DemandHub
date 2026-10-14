package com.demandhub.system.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 角色授权保存请求（FR-M1-03，角色族版）
 */
@Data
public class RoleGrantSaveRequest implements Serializable {

    private Long id;

    /** 被授权用户（demand_user.id，OneID） */
    @NotNull(message = "用户不能为空")
    private Long demandUserId;

    /** 角色族：ADMIN/EXECUTIVE/MANAGER/HANDLER */
    @NotBlank(message = "角色不能为空")
    @Pattern(regexp = "ADMIN|EXECUTIVE|MANAGER|HANDLER", message = "非法业务角色")
    private String roleCode;

    /** 授权组织范围（demand_org.id，默认覆盖子树）；NULL 表示不限组织 */
    private Long orgId;

    /** 需求类型集合（逗号多选），可覆盖角色默认值 */
    private String demandTypeScope;

    private LocalDateTime effectiveFrom;

    private LocalDateTime effectiveTo;
}
