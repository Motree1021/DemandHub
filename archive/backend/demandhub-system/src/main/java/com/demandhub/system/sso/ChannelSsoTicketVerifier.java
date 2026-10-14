package com.demandhub.system.sso;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.entity.Channel;
import com.demandhub.system.mapper.ChannelMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 统一渠道 SSO 校验器（任务 3.1：适配器框架与既有 TicketVerifier 接缝整合）。
 * 全链路单轨：dev 走 Mock verify（config_json base_url 指向内置 Mock 端点），
 * test/prod 同一代码路径指向创金零售真实 verify——Mock/真实仅差一行配置，无双轨实现。
 *
 * 流程：按 channelCode 读 demand_channel.config_json → 解析 ChannelSsoConfig
 * → 适配器注册表按 channelCode 路由到 ChannelSsoClient 实现 → 回源校验。
 */
@Slf4j
@Component
public class ChannelSsoTicketVerifier implements TicketVerifier {

    private final ChannelMapper channelMapper;
    private final SecretCrypto secretCrypto;
    /** 适配器注册表：channelCode → ChannelSsoClient（Spring 自动收集实现类） */
    private final Map<String, ChannelSsoClient> clients;

    /**
     * 环境变量覆盖（开发计划 §7 配置清单：test/prod 的创金零售 verify 地址与签名凭证经环境注入，
     * 不落库、不入仓库）。三项齐备才对 CHUANGJIN_LS 生效并优先于 DB config_json；
     * dev 缺省不设置 → 走 DB 配置（指向内置 Mock）。
     */
    @Value("${CHANNEL_LS_BASE_URL:}")
    private String envBaseUrl;
    @Value("${CHANNEL_LS_APP_KEY:}")
    private String envAppKey;
    @Value("${CHANNEL_LS_APP_SECRET:}")
    private String envAppSecret;
    @Value("${CHANNEL_LS_TICKET_TTL:0}")
    private int envTicketTtl;
    @Value("${CHANNEL_LS_TIMEOUT_MS:0}")
    private int envTimeoutMs;

    public ChannelSsoTicketVerifier(ChannelMapper channelMapper, SecretCrypto secretCrypto,
                                    List<ChannelSsoClient> clientList) {
        this.channelMapper = channelMapper;
        this.secretCrypto = secretCrypto;
        this.clients = clientList.stream()
                .collect(Collectors.toMap(ChannelSsoClient::channelCode, Function.identity()));
        log.info("渠道 SSO 适配器注册表: {}", clients.keySet());
    }

    @Override
    public SsoProfile verify(String channelCode, String ticket) {
        ChannelSsoClient client = clients.get(channelCode);
        if (client == null) {
            log.error("渠道无 SSO 适配器实现: channel={}", channelCode);
            throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, "登录服务暂时不可用，请稍后重试");
        }
        ChannelSsoConfig config = resolveConfig(channelCode);
        if (config == null || !config.isComplete()) {
            // 配置缺失/不完整：服务侧配置问题，告警并按服务不可用降级（不暴露细节）
            log.error("渠道 SSO 配置缺失或不完整告警: channel={}", channelCode);
            throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, "登录服务暂时不可用，请稍后重试");
        }
        // 落库密文 → 内存解密（ENC: 前缀；env 注入明文无前缀原样通过；解密结果不出服务端、不入日志）
        config.setAppSecret(secretCrypto.decryptIfMarked(config.getAppSecret()));
        return client.verify(config, ticket);
    }

    /** env 覆盖优先于 DB config_json（仅 CHUANGJIN_LS；base_url/app_key/app_secret 三项齐备才生效） */
    private ChannelSsoConfig resolveConfig(String channelCode) {
        if (ChuangjinLsSsoClient.CHANNEL_CODE.equals(channelCode)
                && StringUtils.hasText(envBaseUrl) && StringUtils.hasText(envAppKey) && StringUtils.hasText(envAppSecret)) {
            ChannelSsoConfig config = new ChannelSsoConfig();
            config.setSsoVerifyBaseUrl(envBaseUrl);
            config.setAppKey(envAppKey);
            config.setAppSecret(envAppSecret);
            if (envTicketTtl > 0) {
                config.setTicketTtlSeconds(envTicketTtl);
            }
            if (envTimeoutMs > 0) {
                config.setTimeoutMs(envTimeoutMs);
            }
            return config;
        }
        Channel channel = channelMapper.selectOne(new LambdaQueryWrapper<Channel>()
                .eq(Channel::getChannelCode, channelCode));
        return channel == null ? null : ChannelSsoConfig.parse(channel.getConfigJson());
    }
}
