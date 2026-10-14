package com.demandhub.system.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.io.Serializable;

/**
 * 管理员重置密码请求（管理端用户管理）。
 * 重置后 password_updated_at 置 NULL，用户下次登录强制改密。
 */
@Data
public class ResetPasswordRequest implements Serializable {

    @NotBlank(message = "新密码不能为空")
    private String newPassword;
}
