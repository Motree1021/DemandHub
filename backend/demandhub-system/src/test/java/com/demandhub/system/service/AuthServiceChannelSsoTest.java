package com.demandhub.system.service;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.config.AuthProperties;
import com.demandhub.system.dto.LoginResponse;
import com.demandhub.system.entity.Channel;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.ChannelMapper;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.sso.SsoProfile;
import com.demandhub.system.sso.TicketVerifier;
import io.jsonwebtoken.Claims;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 渠道 SSO 登录关键链路集成单测（P7 任务 7.1，FR-M1-01 / AC-03）：
 * 渠道码归一 → 渠道启停校验 → 票据回源（TicketVerifier）→ OneID 匹配 → 账号可用性
 * → JWT/refresh 签发 → 会话写入。全链路 mock 链集成，真实联调覆盖由 phase3/6 e2e 承担。
 */
@ExtendWith(MockitoExtension.class)
class AuthServiceChannelSsoTest {

    @Mock
    private TicketVerifier ticketVerifier;
    @Mock
    private ChannelUserMatcher channelUserMatcher;
    @Mock
    private RoleGrantService roleGrantService;
    @Mock
    private JwtService jwtService;
    @Mock
    private SessionService sessionService;
    @Mock
    private UserService userService;
    @Mock
    private ChannelMapper channelMapper;
    @Mock
    private OrgSnapshotMapper orgMapper;
    @Mock
    private AuthProperties authProperties;
    @Mock
    private StringRedisTemplate redis;
    @InjectMocks
    private AuthService authService;

    private static Channel activeChannel(String code) {
        Channel ch = new Channel();
        ch.setChannelCode(code);
        ch.setStatus("ACTIVE");
        return ch;
    }

    private static UserSnapshot activeUser() {
        UserSnapshot u = new UserSnapshot();
        u.setId(1006L);
        u.setUserId("1006");
        u.setName("提报人");
        u.setStatus("ACTIVE");
        u.setPrimaryOrgId(900L);
        return u;
    }

    private void stubTokenChain(UserSnapshot user, List<String> roles) {
        when(roleGrantService.listEffectiveRoleCodes(user.getId())).thenReturn(roles);
        when(jwtService.createAccessToken(user.getId(), user.getUserId(), roles, "CHUANGJIN_LS"))
                .thenReturn("access-token");
        when(jwtService.createRefreshToken(user.getId(), user.getUserId(), "CHUANGJIN_LS"))
                .thenReturn("refresh-token");
        Claims accessClaims = mock(Claims.class);
        when(accessClaims.getId()).thenReturn("access-jti");
        Claims refreshClaims = mock(Claims.class);
        when(refreshClaims.getId()).thenReturn("refresh-jti");
        when(jwtService.parse("access-token")).thenReturn(accessClaims);
        when(jwtService.parse("refresh-token")).thenReturn(refreshClaims);
        when(jwtService.getAccessTtlSeconds()).thenReturn(7200L);
        when(jwtService.getRefreshTtlSeconds()).thenReturn(28800L);
        when(roleGrantService.listEffectiveGrants(user.getId())).thenReturn(List.of());
        when(orgMapper.selectList(null)).thenReturn(List.of());
    }

    @Test
    void channelSso_happyPath_aliasNormalizedAndTokenChainIssued() {
        when(channelMapper.selectOne(any())).thenReturn(activeChannel("CHUANGJIN_LS"));
        SsoProfile profile = new SsoProfile();
        profile.setUserId("wq_u_006");
        profile.setName("提报人");
        when(ticketVerifier.verify("CHUANGJIN_LS", "T-1")).thenReturn(profile);
        UserSnapshot user = activeUser();
        MatchResult match = new MatchResult();
        match.setUser(user);
        match.setMatchType("WECOMID");
        when(channelUserMatcher.match("CHUANGJIN_LS", profile)).thenReturn(match);
        when(userService.buildDeptPath(900L)).thenReturn("外部组织");
        stubTokenChain(user, List.of());

        // 入口别名 from=chuangjinls 应归一为 CHUANGJIN_LS
        LoginResponse resp = authService.channelSso("chuangjinls", "T-1", "state-1");

        assertEquals("access-token", resp.getAccessToken());
        assertEquals("refresh-token", resp.getRefreshToken());
        assertEquals("CHUANGJIN_LS", resp.getChannel());
        assertEquals(7200L, resp.getExpiresIn());
        assertFalse(resp.getMustChangePassword());
        assertEquals(1006L, resp.getUser().getId());
        // 会话双写（access + refresh）
        verify(sessionService).saveSession(eq("access-jti"), any(), eq(7200L));
        verify(sessionService).saveRefresh("refresh-jti", "1006", 28800L);
    }

    @Test
    void channelSso_channelDisabled_rejected() {
        Channel ch = activeChannel("CHUANGJIN_LS");
        ch.setStatus("DISABLED");
        when(channelMapper.selectOne(any())).thenReturn(ch);

        BizException ex = assertThrows(BizException.class,
                () -> authService.channelSso("CHUANGJIN_LS", "T-1", null));
        assertEquals(ErrorCode.CHANNEL_DISABLED.getCode(), ex.getCode());
    }

    @Test
    void channelSso_webChannel_rejectedAsNotTicketLogin() {
        when(channelMapper.selectOne(any())).thenReturn(activeChannel("WEB"));

        BizException ex = assertThrows(BizException.class,
                () -> authService.channelSso("WEB", "T-1", null));
        assertEquals(ErrorCode.PARAM_INVALID.getCode(), ex.getCode());
    }

    @Test
    void channelSso_unknownChannel_rejected() {
        when(channelMapper.selectOne(any())).thenReturn(null);

        BizException ex = assertThrows(BizException.class,
                () -> authService.channelSso("NO_SUCH", "T-1", null));
        assertEquals(ErrorCode.PARAM_INVALID.getCode(), ex.getCode());
    }

    @Test
    void channelSso_blankChannel_rejected() {
        BizException ex = assertThrows(BizException.class,
                () -> authService.channelSso(" ", "T-1", null));
        assertEquals(ErrorCode.PARAM_INVALID.getCode(), ex.getCode());
    }

    @Test
    void channelSso_disabledUser_rejectedAsUserNotFound() {
        when(channelMapper.selectOne(any())).thenReturn(activeChannel("CHUANGJIN_LS"));
        when(ticketVerifier.verify(anyString(), anyString())).thenReturn(new SsoProfile());
        UserSnapshot disabled = activeUser();
        disabled.setStatus("DISABLED");
        MatchResult match = new MatchResult();
        match.setUser(disabled);
        when(channelUserMatcher.match(anyString(), any())).thenReturn(match);

        BizException ex = assertThrows(BizException.class,
                () -> authService.channelSso("CHUANGJIN_LS", "T-1", null));
        // 停用/合并账号不暴露存在性，按用户不存在拒绝
        assertEquals(ErrorCode.USER_NOT_FOUND.getCode(), ex.getCode());
    }

    @Test
    void channelSso_matchedNullUser_rejectedAsUserNotFound() {
        when(channelMapper.selectOne(any())).thenReturn(activeChannel("CHUANGJIN_LS"));
        when(ticketVerifier.verify(anyString(), anyString())).thenReturn(new SsoProfile());
        when(channelUserMatcher.match(anyString(), any())).thenReturn(new MatchResult());

        BizException ex = assertThrows(BizException.class,
                () -> authService.channelSso("CHUANGJIN_LS", "T-1", null));
        assertEquals(ErrorCode.USER_NOT_FOUND.getCode(), ex.getCode());
    }
}
