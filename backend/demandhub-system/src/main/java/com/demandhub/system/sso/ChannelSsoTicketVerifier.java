package com.demandhub.system.sso;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.entity.Channel;
import com.demandhub.system.mapper.ChannelMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

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
        Channel channel = channelMapper.selectOne(new LambdaQueryWrapper<Channel>()
                .eq(Channel::getChannelCode, channelCode));
        ChannelSsoConfig config = channel == null ? null : ChannelSsoConfig.parse(channel.getConfigJson());
        if (config == null || !config.isComplete()) {
            // 配置缺失/不完整：服务侧配置问题，告警并按服务不可用降级（不暴露细节）
            log.error("渠道 SSO 配置缺失或不完整告警: channel={}", channelCode);
            throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, "登录服务暂时不可用，请稍后重试");
        }
        // 落库密文 → 内存解密（ENC: 前缀；解密结果不出服务端、不入日志）
        config.setAppSecret(secretCrypto.decryptIfMarked(config.getAppSecret()));
        return client.verify(config, ticket);
    }
}
