package com.demandhub.system.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

import java.io.Serializable;

/**
 * 修改密码请求（强制改密 / 自助改密共用）
 */
@Data
public class ChangePasswordRequest implements Serializable {

    @NotBlank(message = "原密码不能为空")
    private String oldPassword;

    @NotBlank(message = "新密码不能为空")
    private String newPassword;
}
