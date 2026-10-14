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

    /** 登录渠道（WEB/CHUANGJIN_LS），以服务端判定为准，不信任前端传值 */
    private String channel;

    /** 是否需要强制改密（PC 账密且 password_updated_at 为 NULL） */
    private Boolean mustChangePassword;

    private UserInfoVO user;
}
