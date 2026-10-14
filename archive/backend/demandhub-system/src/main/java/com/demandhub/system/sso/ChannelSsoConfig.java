package com.demandhub.system.sso;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.Data;
import org.springframework.util.StringUtils;

import java.io.Serializable;

/**
 * 渠道 SSO 校验配置（demand_channel.config_json 解析结果，任务 3.1）。
 * 配置项：sso_verify_base_url / app_key / app_secret / ticket_ttl_seconds / timeout_ms；
 * 新渠道接入 = demand_channel 加一行配置 + 一个 ChannelSsoClient 实现类。
 * app_secret 仅服务端使用：不入日志、不经接口回显（toString 已脱敏）。
 */
@Data
public class ChannelSsoConfig implements Serializable {

    public static final int DEFAULT_TIMEOUT_MS = 3000;

    /** verify 接口 base（完整 URL = ssoVerifyBaseUrl + SsoSignUtil.VERIFY_PATH），沙箱/生产经此切换 */
    private String ssoVerifyBaseUrl;

    private String appKey;

    /** 密钥（解密后仅在内存使用；日志/接口一律脱敏） */
    private String appSecret;

    private Integer ticketTtlSeconds = 60;

    /** verify 调用超时（毫秒），默认 3000（对接标准：3s 快速失败，不重试） */
    private Integer timeoutMs = DEFAULT_TIMEOUT_MS;

    private static final ObjectMapper MAPPER = new ObjectMapper();

    public static ChannelSsoConfig parse(String configJson) {
        if (!StringUtils.hasText(configJson)) {
            return null;
        }
        try {
            JsonNode node = MAPPER.readTree(configJson);
            ChannelSsoConfig config = new ChannelSsoConfig();
            config.setSsoVerifyBaseUrl(text(node, "sso_verify_base_url"));
            config.setAppKey(text(node, "app_key"));
            config.setAppSecret(text(node, "app_secret"));
            if (node.hasNonNull("ticket_ttl_seconds")) {
                config.setTicketTtlSeconds(node.get("ticket_ttl_seconds").asInt(60));
            }
            if (node.hasNonNull("timeout_ms")) {
                config.setTimeoutMs(node.get("timeout_ms").asInt(DEFAULT_TIMEOUT_MS));
            }
            return config;
        } catch (Exception e) {
            return null;
        }
    }

    /** 配置完整可用（base_url/app_key/app_secret 三者齐备） */
    public boolean isComplete() {
        return StringUtils.hasText(ssoVerifyBaseUrl) && StringUtils.hasText(appKey) && StringUtils.hasText(appSecret);
    }

    private static String text(JsonNode node, String field) {
        JsonNode v = node.get(field);
        return v == null || v.isNull() ? null : v.asText();
    }

    /** 脱敏（防 toString 泄露密钥） */
    @Override
    public String toString() {
        return "ChannelSsoConfig(ssoVerifyBaseUrl=" + ssoVerifyBaseUrl + ", appKey=" + appKey
                + ", appSecret=***, ticketTtlSeconds=" + ticketTtlSeconds + ", timeoutMs=" + timeoutMs + ")";
    }
}
