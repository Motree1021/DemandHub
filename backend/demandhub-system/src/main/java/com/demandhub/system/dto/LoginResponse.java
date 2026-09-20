package com.demandhub.system.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * 登录/刷新响应
 */
@Data
public class LoginResponse implements Serializable {

    private String accessToken;

    private String refreshToken;

    /** access token 有效期（秒） */
    private Long expiresIn;

    private UserInfoVO user;
}
