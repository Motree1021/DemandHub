package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.dto.ChannelConfigRequest;
import com.demandhub.system.dto.ChannelVO;
import com.demandhub.system.entity.Channel;
import com.demandhub.system.entity.ChannelDeptUnmapped;
import com.demandhub.system.mapper.ChannelDeptUnmappedMapper;
import com.demandhub.system.mapper.ChannelMapper;
import com.demandhub.system.sso.ChannelSsoClient;
import com.demandhub.system.sso.ChannelSsoConfig;
import com.demandhub.system.sso.SecretCrypto;
import com.demandhub.system.sso.SsoProfile;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * 渠道管理（FR-M1-04，开发计划任务 4.5）：列表（密钥脱敏）/启停/配置更新（密钥加密落库）/连接测试。
 * 连接测试复用 SSO 适配器框架：以 dummy 票据探活上游 verify——上游返回"票据无效"即链路连通，
 * 传输失败/鉴权失败按连接失败反馈（不放行任何真实身份，无副作用）。
 */
@Slf4j
@Service
public class ChannelService {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final ChannelMapper channelMapper;
    private final ChannelDeptUnmappedMapper unmappedMapper;
    private final SecretCrypto secretCrypto;
    /** 适配器注册表：channelCode → ChannelSsoClient（与 ChannelSsoTicketVerifier 同一组 Bean） */
    private final Map<String, ChannelSsoClient> clients;

    public ChannelService(ChannelMapper channelMapper, ChannelDeptUnmappedMapper unmappedMapper,
                          SecretCrypto secretCrypto, List<ChannelSsoClient> clientList) {
        this.channelMapper = channelMapper;
        this.unmappedMapper = unmappedMapper;
        this.secretCrypto = secretCrypto;
        this.clients = clientList.stream()
                .collect(Collectors.toMap(ChannelSsoClient::channelCode, Function.identity(), (a, b) -> a));
    }

    /** 渠道列表（config_json 拍平 + app_secret 脱敏为 ***） */
    public List<ChannelVO> list() {
        return channelMapper.selectList(new LambdaQueryWrapper<Channel>().orderByAsc(Channel::getId))
                .stream().map(this::toVO).collect(Collectors.toList());
    }

    /** 启停（ACTIVE/DISABLED）；停用后该渠道票据登录即拒（AuthService 校验 status） */
    public void updateStatus(Long id, String status) {
        Channel channel = requireChannel(id);
        if (!"ACTIVE".equals(status) && !"DISABLED".equals(status)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "非法渠道状态");
        }
        Channel update = new Channel();
        update.setId(channel.getId());
        update.setStatus(status);
        channelMapper.updateById(update);
        log.info("渠道状态变更: channel={}, status={}", channel.getChannelCode(), status);
    }

    /**
     * 更新 SSO 配置：合并既有 config_json；appSecret 非空才更换（AES-GCM 加密落库），
     * 其余字段按入参覆盖（null 保持不变）。
     */
    public void updateConfig(Long id, ChannelConfigRequest req) {
        Channel channel = requireChannel(id);
        try {
            ObjectNode node = StringUtils.hasText(channel.getConfigJson())
                    ? (ObjectNode) MAPPER.readTree(channel.getConfigJson())
                    : MAPPER.createObjectNode();
            if (req.getSsoVerifyBaseUrl() != null) {
                node.put("sso_verify_base_url", req.getSsoVerifyBaseUrl());
            }
            if (req.getAppKey() != null) {
                node.put("app_key", req.getAppKey());
            }
            if (StringUtils.hasText(req.getAppSecret())) {
                node.put("app_secret", secretCrypto.encrypt(req.getAppSecret()));
            }
            if (req.getTicketTtlSeconds() != null) {
                node.put("ticket_ttl_seconds", req.getTicketTtlSeconds());
            }
            if (req.getTimeoutMs() != null) {
                node.put("timeout_ms", req.getTimeoutMs());
            }
            Channel update = new Channel();
            update.setId(channel.getId());
            update.setConfigJson(MAPPER.writeValueAsString(node));
            if (req.getAppId() != null) {
                update.setAppId(req.getAppId());
            }
            channelMapper.updateById(update);
            log.info("渠道配置更新: channel={}, baseUrl={}, appKey={}, secretRotated={}",
                    channel.getChannelCode(), req.getSsoVerifyBaseUrl(), req.getAppKey(),
                    StringUtils.hasText(req.getAppSecret()));
        } catch (BizException e) {
            throw e;
        } catch (Exception e) {
            throw new BizException(ErrorCode.PARAM_INVALID, "配置序列化失败");
        }
    }

    /**
     * 连接测试：dummy 票据探活上游 verify。
     * 上游返回票据无效(40001/40002→CHANNEL_TICKET_INVALID) = 链路+签名连通；其余异常 = 连接失败。
     */
    public String testConnection(Long id) {
        Channel channel = requireChannel(id);
        ChannelSsoClient client = clients.get(channel.getChannelCode());
        if (client == null) {
            throw new BizException(ErrorCode.PARAM_INVALID, "该渠道无 SSO 适配器，不支持连接测试");
        }
        ChannelSsoConfig config = ChannelSsoConfig.parse(channel.getConfigJson());
        if (config == null || !config.isComplete()) {
            throw new BizException(ErrorCode.PARAM_INVALID, "SSO 配置不完整（需 base_url/app_key/app_secret）");
        }
        config.setAppSecret(secretCrypto.decryptIfMarked(config.getAppSecret()));
        try {
            SsoProfile profile = client.verify(config, "__health_check__");
            return "连接正常（意外通过票据校验，请检查上游）: userId=" + profile.getUserId();
        } catch (BizException e) {
            if (ErrorCode.CHANNEL_TICKET_INVALID.getCode().equals(e.getCode())) {
                return "连接正常（上游可达，票据校验按预期拒绝）";
            }
            throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, "连接失败：" + e.getMessage());
        }
    }

    /** 部门未映射校准清单分页 */
    public Page<ChannelDeptUnmapped> unmappedPage(long current, long size, String channelCode) {
        return unmappedMapper.selectPage(new Page<>(current, size), new LambdaQueryWrapper<ChannelDeptUnmapped>()
                .eq(StringUtils.hasText(channelCode), ChannelDeptUnmapped::getChannelCode, channelCode)
                .orderByDesc(ChannelDeptUnmapped::getLastSeenAt));
    }

    /** 校准完成后删除未映射记录 */
    public void deleteUnmapped(Long id) {
        if (unmappedMapper.selectById(id) == null) {
            throw new BizException(ErrorCode.NOT_FOUND, "校准记录不存在");
        }
        unmappedMapper.deleteById(id);
    }

    private Channel requireChannel(Long id) {
        Channel channel = channelMapper.selectById(id);
        if (channel == null) {
            throw new BizException(ErrorCode.NOT_FOUND, "渠道不存在");
        }
        return channel;
    }

    private ChannelVO toVO(Channel channel) {
        ChannelVO vo = new ChannelVO();
        vo.setId(channel.getId());
        vo.setChannelCode(channel.getChannelCode());
        vo.setChannelName(channel.getChannelName());
        vo.setAppId(channel.getAppId());
        vo.setCallbackEnabled(channel.getCallbackEnabled());
        vo.setStatus(channel.getStatus());
        vo.setUpdatedAt(channel.getUpdatedAt());
        ChannelSsoConfig config = ChannelSsoConfig.parse(channel.getConfigJson());
        if (config != null) {
            vo.setSsoVerifyBaseUrl(config.getSsoVerifyBaseUrl());
            vo.setAppKey(config.getAppKey());
            vo.setAppSecret(StringUtils.hasText(config.getAppSecret()) ? "***" : null);
            vo.setTicketTtlSeconds(config.getTicketTtlSeconds());
            vo.setTimeoutMs(config.getTimeoutMs());
            vo.setSsoConfigured(config.isComplete());
        } else {
            vo.setSsoConfigured(false);
        }
        return vo;
    }
}
