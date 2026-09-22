package com.demandhub.system.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

import java.io.Serializable;

/**
 * 设置 PC 登录账号请求（管理端用户管理）。
 */
@Data
public class LoginAccountRequest implements Serializable {

    @NotBlank(message = "登录账号不能为空")
    @Pattern(regexp = "^[a-zA-Z0-9_.-]{3,64}$", message = "登录账号须为 3~64 位字母/数字/_.-")
    private String loginName;
}
