package com.demandhub.system.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.io.Serializable;

/**
 * PENDING 用户资料补全请求（FR-M1-01，管理端用户管理）。
 * 渠道自动建号的字段缺失用户（D4 兜 PENDING）由管理员补全后激活。
 */
@Data
public class UserCompleteRequest implements Serializable {

    @NotBlank(message = "姓名不能为空")
    private String name;

    private String phone;

    private String email;

    private String employeeNo;

    /** 主组织（demand_org.id）；缺省保持原挂载点 */
    private Long primaryOrgId;
}
