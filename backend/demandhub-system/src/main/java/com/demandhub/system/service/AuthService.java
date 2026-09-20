package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.dto.LoginResponse;
import com.demandhub.system.dto.MockUserVO;
import com.demandhub.system.dto.UserInfoVO;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.RoleGrant;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.integration.pcenter.PermissionCenterClient;
import com.demandhub.system.integration.pcenter.dto.PcUser;
import com.demandhub.system.integration.wecom.MockWecomClient;
import com.demandhub.system.integration.wecom.WecomClient;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.mapper.UserSnapshotMapper;
import io.jsonwebtoken.Claims;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 认证主流程（FR-M1-01）：企微 OAuth code → 权限中心用户详情 → 本地镜像自动建档 → 签发 JWT + Redis 会话。
 * 权限中心不可用时降级为本地镜像只读会话。
 */
@Slf4j
@Service
public class AuthService {

    private final WecomClient wecomClient;
    private final PermissionCenterClient pcenterClient;
    private final MasterDataSyncService syncService;
    private final RoleGrantService roleGrantService;
    private final JwtService jwtService;
    private final SessionService sessionService;
    private final UserSnapshotMapper userMapper;
    private final OrgSnapshotMapper orgMapper;

    public AuthService(WecomClient wecomClient,
                       PermissionCenterClient pcenterClient,
                       MasterDataSyncService syncService,
                       RoleGrantService roleGrantService,
                       JwtService jwtService,
                       SessionService sessionService,
                       UserSnapshotMapper userMapper,
                       OrgSnapshotMapper orgMapper) {
        this.wecomClient = wecomClient;
        this.pcenterClient = pcenterClient;
        this.syncService = syncService;
        this.roleGrantService = roleGrantService;
        this.jwtService = jwtService;
        this.sessionService = sessionService;
        this.userMapper = userMapper;
        this.orgMapper = orgMapper;
    }

    /**
     * 企微 OAuth 登录（PC 扫码回调 / H5 静默授权共用）
     *
     * @param code 企微授权码；一期 Mock：mock-{userId}
     */
    public LoginResponse loginByCode(String code) {
        String wecomId = wecomClient.exchangeCode(code);

        UserSnapshot snapshot;
        boolean readOnly = false;
        try {
            PcUser pcUser = pcenterClient.getUserByWecomId(wecomId);
            if (pcUser == null) {
                throw new BizException(ErrorCode.USER_NOT_FOUND, "权限中心不存在该用户");
            }
            // 本地无该用户则自动建档（只读镜像）
            snapshot = syncService.upsertUser(pcUser);
        } catch (BizException e) {
            throw e;
        } catch (Exception e) {
            // 权限中心异常 → 本地镜像降级建立只读会话（FR-M1-01 异常流）
            log.warn("权限中心不可用，降级本地镜像登录: {}", e.getMessage());
            snapshot = userMapper.selectOne(
                    new LambdaQueryWrapper<UserSnapshot>().eq(UserSnapshot::getWecomId, wecomId));
            if (snapshot == null) {
                throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE);
            }
            readOnly = true;
        }

        return buildLoginResponse(snapshot, readOnly);
    }

    /**
     * 刷新访问令牌（续期无感）
     */
    public LoginResponse refresh(String refreshToken) {
        Claims claims = jwtService.parse(refreshToken);
        if (claims == null || !JwtService.TYPE_REFRESH.equals(claims.get(JwtService.CLAIM_TYPE))) {
            throw new BizException(ErrorCode.REFRESH_TOKEN_INVALID);
        }
        if (!sessionService.refreshExists(claims.getId())) {
            throw new BizException(ErrorCode.REFRESH_TOKEN_INVALID);
        }
        UserSnapshot snapshot = userMapper.selectOne(new LambdaQueryWrapper<UserSnapshot>()
                .eq(UserSnapshot::getUserId, claims.get(JwtService.CLAIM_USER_ID, String.class)));
        if (snapshot == null) {
            throw new BizException(ErrorCode.USER_NOT_FOUND);
        }
        return buildLoginResponse(snapshot, false);
    }

    /**
     * 登出：删除 access 会话与 refresh 会话
     */
    public void logout(String accessToken, String refreshToken) {
        if (accessToken != null) {
            Claims claims = jwtService.parse(accessToken);
            if (claims != null) {
                sessionService.deleteSession(claims.getId());
            }
        }
        if (refreshToken != null) {
            Claims claims = jwtService.parse(refreshToken);
            if (claims != null) {
                sessionService.deleteRefresh(claims.getId());
            }
        }
    }

    /**
     * 当前登录用户信息（含生效授权明细）
     */
    public UserInfoVO me() {
        CurrentUser current = UserContext.get();
        if (current == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        UserSnapshot snapshot = userMapper.selectById(current.getId());
        if (snapshot == null) {
            throw new BizException(ErrorCode.USER_NOT_FOUND);
        }
        return buildUserInfo(snapshot, false);
    }

    /**
     * 一期 Mock：登录页可选用户列表
     */
    public List<MockUserVO> listMockUsers() {
        Map<Long, String> orgNames = orgMapper.selectList(null).stream()
                .collect(Collectors.toMap(OrgSnapshot::getOrgId, OrgSnapshot::getName, (a, b) -> a));
        return pcenterClient.listAllUsers().stream().map(u -> {
            MockUserVO vo = new MockUserVO();
            vo.setUserId(u.getUserId());
            vo.setName(u.getName());
            vo.setOrgName(orgNames.getOrDefault(u.getPrimaryOrgId(), String.valueOf(u.getPrimaryOrgId())));
            vo.setMockCode(MockWecomClient.MOCK_CODE_PREFIX + u.getUserId());
            return vo;
        }).toList();
    }

    private LoginResponse buildLoginResponse(UserSnapshot snapshot, boolean readOnly) {
        List<String> roles = roleGrantService.listEffectiveRoleCodes(snapshot.getUserId());

        String accessToken = jwtService.createAccessToken(snapshot.getId(), snapshot.getUserId(), roles);
        String refreshToken = jwtService.createRefreshToken(snapshot.getId(), snapshot.getUserId());

        Claims accessClaims = jwtService.parse(accessToken);
        sessionService.saveSession(accessClaims.getId(),
                SessionService.SessionUser.of(snapshot, roles), jwtService.getAccessTtlSeconds());
        Claims refreshClaims = jwtService.parse(refreshToken);
        sessionService.saveRefresh(refreshClaims.getId(), snapshot.getUserId(), jwtService.getRefreshTtlSeconds());

        LoginResponse response = new LoginResponse();
        response.setAccessToken(accessToken);
        response.setRefreshToken(refreshToken);
        response.setExpiresIn(jwtService.getAccessTtlSeconds());
        response.setUser(buildUserInfo(snapshot, readOnly));
        return response;
    }

    private UserInfoVO buildUserInfo(UserSnapshot snapshot, boolean readOnly) {
        List<RoleGrant> grants = roleGrantService.listEffectiveGrants(snapshot.getUserId());
        Map<Long, String> orgNames = orgMapper.selectList(null).stream()
                .collect(Collectors.toMap(OrgSnapshot::getOrgId, OrgSnapshot::getName, (a, b) -> a));

        UserInfoVO vo = new UserInfoVO();
        vo.setId(snapshot.getId());
        vo.setUserId(snapshot.getUserId());
        vo.setName(snapshot.getName());
        vo.setPrimaryOrgId(snapshot.getPrimaryOrgId());
        vo.setOrgName(orgNames.getOrDefault(snapshot.getPrimaryOrgId(),
                snapshot.getPrimaryOrgId() == null ? null : String.valueOf(snapshot.getPrimaryOrgId())));
        vo.setDeptPath(snapshot.getDeptPath());
        vo.setRoles(grants.stream().map(RoleGrant::getRoleCode).distinct().toList());
        vo.setGrants(grants.stream().map(g -> {
            UserInfoVO.GrantVO gvo = new UserInfoVO.GrantVO();
            gvo.setRoleCode(g.getRoleCode());
            gvo.setOrgId(g.getOrgId());
            gvo.setOrgName(g.getOrgId() == null ? "全部组织" : orgNames.getOrDefault(g.getOrgId(), String.valueOf(g.getOrgId())));
            gvo.setDemandTypeScope(g.getDemandTypeScope());
            return gvo;
        }).toList());
        vo.setReadOnly(readOnly);
        return vo;
    }
}
