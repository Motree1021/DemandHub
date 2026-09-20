package com.demandhub.system.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 认证配置：JWT 密钥与会话时长（SRS：会话超时 8 小时，续期无感）
 */
@Data
@Component
@ConfigurationProperties(prefix = "demandhub.auth")
public class AuthProperties {

    /** HS256 密钥，至少 32 字节；生产环境走配置中心/KMS */
    private String jwtSecret = "demandhub-dev-secret-key-0123456789abcdef";

    /** 访问令牌有效期（小时），SRS 会话超时 8 小时 */
    private long accessTtlHours = 8;

    /** 刷新令牌有效期（天） */
    private long refreshTtlDays = 7;
}
