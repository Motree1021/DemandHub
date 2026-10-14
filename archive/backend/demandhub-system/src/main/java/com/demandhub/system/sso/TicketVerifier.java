package com.demandhub.system.sso;

/**
 * 渠道 SSO 票据校验器（P2 定义接缝，P3 接创金零售真实 verify 实现）。
 * 实现要求：一次性消费、TTL 校验、失败抛出 BizException(CHANNEL_TICKET_INVALID / AUTH_SERVICE_UNAVAILABLE)。
 */
public interface TicketVerifier {

    /**
     * 回源校验一次性票据。
     *
     * @param channelCode 渠道码（如 CHUANGJIN_LS）
     * @param ticket      一次性登录票据
     * @return 校验通过的身份信息
     */
    SsoProfile verify(String channelCode, String ticket);
}
