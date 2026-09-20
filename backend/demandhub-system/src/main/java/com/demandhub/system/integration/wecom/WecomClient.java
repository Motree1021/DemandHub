package com.demandhub.system.integration.wecom;

/**
 * 企业微信客户端（IR-01）。
 * 一期外部依赖 Mock：由 {@link MockWecomClient} 按约定规则换号；二期切换真实企微 API。
 */
public interface WecomClient {

    /**
     * OAuth 授权码换企微 userid。
     *
     * @param code 企微回调授权码；Mock 规则：{@code mock-{userId}}，如 mock-u_admin_001
     * @return 企微 userid（对应权限中心 wecom_id）
     */
    String exchangeCode(String code);

    /**
     * 构造企微 OAuth 授权链接（PC 扫码 / H5 静默共用）。
     * Mock 实现返回指向本地登录页的说明性链接。
     */
    String buildOAuthUrl(String redirectUri, String state);
}
