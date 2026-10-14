package com.demandhub.system.dto;

import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 渠道管理视图（FR-M1-04，管理端渠道列表）。
 * config_json 拍平展示且密钥脱敏：appSecret 永远只回 "***"（已配置）或 null（未配置）。
 */
@Data
public class ChannelVO implements Serializable {

    private Long id;

    private String channelCode;

    private String channelName;

    private String appId;

    private Integer callbackEnabled;

    /** ACTIVE/DISABLED */
    private String status;

    private String ssoVerifyBaseUrl;

    private String appKey;

    /** 密钥脱敏标记：已配置=***，未配置=null */
    private String appSecret;

    private Integer ticketTtlSeconds;

    private Integer timeoutMs;

    /** SSO 配置三要素（base_url/app_key/app_secret）是否齐备 */
    private Boolean ssoConfigured;

    private LocalDateTime updatedAt;
}
