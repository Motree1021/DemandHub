package com.demandhub.system.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 认证配置：JWT 密钥与会话时长（access 2h / refresh 8h，续期无感）、账密登录锁定策略。
 */
@Data
@Component
@ConfigurationProperties(prefix = "demandhub.auth")
public class AuthProperties {

    /** HS256 密钥，至少 32 字节；生产环境走配置中心/KMS */
    private String jwtSecret = "demandhub-dev-secret-key-0123456789abcdef";

    /** 访问令牌有效期（小时） */
    private long accessTtlHours = 2;

    /** 刷新令牌有效期（小时） */
    private long refreshTtlHours = 8;

    /** 账密登录连续失败锁定阈值（次） */
    private int loginMaxFailures = 5;

    /** 账密登录锁定时长（分钟） */
    private long loginLockMinutes = 15;
}
