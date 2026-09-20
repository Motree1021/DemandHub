package com.demandhub.system.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 角色授权保存请求（FR-M1-03）
 */
@Data
public class RoleGrantSaveRequest implements Serializable {

    private Long id;

    /** 权限中心用户唯一 ID */
    @NotBlank(message = "用户不能为空")
    private String userId;

    /** ADMIN/EXECUTIVE/DEMAND_MANAGER/HANDLER/REPORTER */
    @NotBlank(message = "角色不能为空")
    @Pattern(regexp = "ADMIN|EXECUTIVE|DEMAND_MANAGER|HANDLER|REPORTER", message = "非法业务角色")
    private String roleCode;

    /** 授权组织范围（权限中心 org_id，默认覆盖子树）；NULL 表示不限组织 */
    private Long orgId;

    /** 需求类型范围（逗号分隔），可覆盖角色默认值 */
    private String demandTypeScope;

    private LocalDateTime effectiveFrom;

    private LocalDateTime effectiveTo;
}
