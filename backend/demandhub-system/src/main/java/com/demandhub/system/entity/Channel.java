package com.demandhub.system.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 提报渠道注册表（demand_channel）。
 * 渠道码：WEB/CHUANGJIN_LS/WECOM_BOT/FEISHU_BOT/DOUBAO_WORK/WORKBUDDY/VOICE（WECOM_APP 预留）。
 * config_json 存 SSO 校验接口 base_url/app_key/加密 app_secret/票据 TTL（接口脱敏返回，P3 适配器消费）。
 */
@Data
@TableName("demand_channel")
public class Channel implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 渠道码（唯一） */
    private String channelCode;

    private String channelName;

    /** 渠道侧应用ID（创金零售 SSO 渠道留空） */
    private String appId;

    private Integer callbackEnabled;

    /** ACTIVE/DISABLED */
    private String status;

    /** SSO 校验配置（JSON 原文；出参必须脱敏） */
    private String configJson;

    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;
}
