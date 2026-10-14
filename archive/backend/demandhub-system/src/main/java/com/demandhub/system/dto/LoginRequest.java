package com.demandhub.system.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.io.Serializable;

/**
 * PC 账密登录请求（D5）
 */
@Data
public class LoginRequest implements Serializable {

    @NotBlank(message = "登录账号不能为空")
    private String loginName;

    @NotBlank(message = "密码不能为空")
    private String password;
}
