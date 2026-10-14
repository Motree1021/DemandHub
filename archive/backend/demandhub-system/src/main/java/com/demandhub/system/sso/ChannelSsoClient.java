package com.demandhub.system.sso;

/**
 * 渠道 SSO 客户端（任务 3.1：渠道适配器框架）。
 * 每个外部渠道一个实现类，经 {@link #channelCode()} 注册进适配器注册表；
 * 新渠道接入 = demand_channel 加配置（config_json）+ 新增一个实现类，主链路零改动。
 *
 * 实现要求：
 * - verify 服务端回源校验一次性票据，失败抛 BizException（不放行任何未核验身份）；
 * - 日志脱敏（ticket/phone/app_secret 不入原文）。
 */
public interface ChannelSsoClient {

    /** 渠道码（与 demand_channel.channel_code 一致），如 CHUANGJIN_LS */
    String channelCode();

    /**
     * 回源校验票据，返回经渠道服务端确认的身份。
     *
     * @param config 渠道配置（demand_channel.config_json 解析结果，含 base_url/app_key/app_secret/timeout）
     * @param ticket 一次性登录票据
     * @throws com.demandhub.common.exception.BizException 票据无效(1107)/账号不可用(1113)/服务不可用(1102)
     */
    SsoProfile verify(ChannelSsoConfig config, String ticket);
}
