package com.demandhub.system.sso;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.entity.Channel;
import com.demandhub.system.mapper.ChannelMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * ChannelSsoTicketVerifier 双轨配置裁决单测（P7 任务 7.1，P6 核心逻辑）：
 * CHANNEL_LS_BASE_URL/APP_KEY/APP_SECRET 三项齐备 → env 覆盖优先于 demand_channel.config_json；
 * 缺项回落 DB；落库 ENC 密文解密后传给适配器；配置缺失/无适配器降级 1102。
 */
@ExtendWith(MockitoExtension.class)
class ChannelSsoTicketVerifierTest {

    @Mock
    private ChannelMapper channelMapper;
    @Mock
    private SecretCrypto secretCrypto;
    @Mock
    private ChannelSsoClient client;

    private ChannelSsoTicketVerifier newVerifier() {
        lenient().when(client.channelCode()).thenReturn(ChuangjinLsSsoClient.CHANNEL_CODE);
        return new ChannelSsoTicketVerifier(channelMapper, secretCrypto, List.of(client));
    }

    private static SsoProfile profile() {
        SsoProfile p = new SsoProfile();
        p.setUserId("wq_u_001");
        p.setName("张三");
        return p;
    }

    @Test
    void envTripletComplete_envOverrideWins_dbNeverQueried() {
        ChannelSsoTicketVerifier verifier = newVerifier();
        ReflectionTestUtils.setField(verifier, "envBaseUrl", "http://env-verify:9000");
        ReflectionTestUtils.setField(verifier, "envAppKey", "env-key");
        ReflectionTestUtils.setField(verifier, "envAppSecret", "env-secret");
        ReflectionTestUtils.setField(verifier, "envTicketTtl", 30);
        ReflectionTestUtils.setField(verifier, "envTimeoutMs", 1500);
        when(secretCrypto.decryptIfMarked("env-secret")).thenReturn("env-secret");
        SsoProfile expected = profile();
        when(client.verify(any(), eq("T-1"))).thenReturn(expected);

        SsoProfile actual = verifier.verify(ChuangjinLsSsoClient.CHANNEL_CODE, "T-1");

        assertSame(expected, actual);
        ArgumentCaptor<ChannelSsoConfig> captor = ArgumentCaptor.forClass(ChannelSsoConfig.class);
        verify(client).verify(captor.capture(), eq("T-1"));
        ChannelSsoConfig used = captor.getValue();
        assertEquals("http://env-verify:9000", used.getSsoVerifyBaseUrl());
        assertEquals("env-key", used.getAppKey());
        assertEquals("env-secret", used.getAppSecret());
        assertEquals(30, used.getTicketTtlSeconds());
        assertEquals(1500, used.getTimeoutMs());
        // env 生效时不得查库
        verifyNoInteractions(channelMapper);
    }

    @Test
    void envPartial_fallsBackToDbConfig_andDecryptsEncSecret() {
        ChannelSsoTicketVerifier verifier = newVerifier();
        // 仅设置 base_url，三件套不齐备 → env 不生效，回落 DB
        ReflectionTestUtils.setField(verifier, "envBaseUrl", "http://env-verify:9000");
        Channel ch = new Channel();
        ch.setChannelCode(ChuangjinLsSsoClient.CHANNEL_CODE);
        ch.setConfigJson("{\"sso_verify_base_url\":\"http://db-verify:8080\","
                + "\"app_key\":\"db-key\",\"app_secret\":\"ENC:cipher-text\",\"timeout_ms\":2000}");
        when(channelMapper.selectOne(any())).thenReturn(ch);
        when(secretCrypto.decryptIfMarked("ENC:cipher-text")).thenReturn("plain-secret");
        SsoProfile expected = profile();
        when(client.verify(any(), eq("T-2"))).thenReturn(expected);

        SsoProfile actual = verifier.verify(ChuangjinLsSsoClient.CHANNEL_CODE, "T-2");

        assertSame(expected, actual);
        ArgumentCaptor<ChannelSsoConfig> captor = ArgumentCaptor.forClass(ChannelSsoConfig.class);
        verify(client).verify(captor.capture(), eq("T-2"));
        ChannelSsoConfig used = captor.getValue();
        assertEquals("http://db-verify:8080", used.getSsoVerifyBaseUrl());
        assertEquals("db-key", used.getAppKey());
        // 落库 ENC 密文解密后传给适配器
        assertEquals("plain-secret", used.getAppSecret());
        assertEquals(2000, used.getTimeoutMs());
    }

    @Test
    void noEnv_dbConfigUsed_plainSecretPassThrough() {
        ChannelSsoTicketVerifier verifier = newVerifier();
        Channel ch = new Channel();
        ch.setChannelCode(ChuangjinLsSsoClient.CHANNEL_CODE);
        ch.setConfigJson("{\"sso_verify_base_url\":\"http://db-verify:8080\","
                + "\"app_key\":\"db-key\",\"app_secret\":\"plain-secret\"}");
        when(channelMapper.selectOne(any())).thenReturn(ch);
        when(secretCrypto.decryptIfMarked("plain-secret")).thenReturn("plain-secret");
        when(client.verify(any(), anyString())).thenReturn(profile());

        verifier.verify(ChuangjinLsSsoClient.CHANNEL_CODE, "T-3");

        ArgumentCaptor<ChannelSsoConfig> captor = ArgumentCaptor.forClass(ChannelSsoConfig.class);
        verify(client).verify(captor.capture(), anyString());
        assertEquals("plain-secret", captor.getValue().getAppSecret());
        // 默认超时/票据 TTL
        assertEquals(ChannelSsoConfig.DEFAULT_TIMEOUT_MS, captor.getValue().getTimeoutMs());
        assertEquals(60, captor.getValue().getTicketTtlSeconds());
    }

    @Test
    void channelNotConfigured_degradesToServiceUnavailable() {
        ChannelSsoTicketVerifier verifier = newVerifier();
        when(channelMapper.selectOne(any())).thenReturn(null);

        BizException ex = assertThrows(BizException.class,
                () -> verifier.verify(ChuangjinLsSsoClient.CHANNEL_CODE, "T-4"));
        assertEquals(ErrorCode.AUTH_SERVICE_UNAVAILABLE.getCode(), ex.getCode());
    }

    @Test
    void incompleteDbConfig_degradesToServiceUnavailable() {
        ChannelSsoTicketVerifier verifier = newVerifier();
        Channel ch = new Channel();
        ch.setChannelCode(ChuangjinLsSsoClient.CHANNEL_CODE);
        ch.setConfigJson("{\"sso_verify_base_url\":\"http://db-verify:8080\",\"app_key\":\"db-key\"}");
        when(channelMapper.selectOne(any())).thenReturn(ch);

        BizException ex = assertThrows(BizException.class,
                () -> verifier.verify(ChuangjinLsSsoClient.CHANNEL_CODE, "T-5"));
        assertEquals(ErrorCode.AUTH_SERVICE_UNAVAILABLE.getCode(), ex.getCode());
    }

    @Test
    void unknownChannel_noAdapter_degradesToServiceUnavailable() {
        // 注册表为空：该渠道无适配器实现
        ChannelSsoTicketVerifier verifier = new ChannelSsoTicketVerifier(channelMapper, secretCrypto, List.of());

        BizException ex = assertThrows(BizException.class,
                () -> verifier.verify("UNKNOWN_CHANNEL", "T-6"));
        assertEquals(ErrorCode.AUTH_SERVICE_UNAVAILABLE.getCode(), ex.getCode());
        verifyNoInteractions(channelMapper);
    }
}
