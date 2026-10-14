package com.demandhub.system.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * 渠道 SSO 配置更新请求（管理端渠道管理）。
 * appSecret 明文入参、落库前 AES-GCM 加密（ENC: 前缀）；留空表示保持原密钥不变。
 */
@Data
public class ChannelConfigRequest implements Serializable {

    /** 渠道侧应用ID（创金零售 SSO 渠道留空） */
    private String appId;

    private String ssoVerifyBaseUrl;

    private String appKey;

    /** 新密钥（明文；留空=不更换） */
    private String appSecret;

    private Integer ticketTtlSeconds;

    private Integer timeoutMs;
}
