package com.demandhub.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.context.CurrentUser;
import com.demandhub.common.context.UserContext;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.config.AuthProperties;
import com.demandhub.system.dto.LoginResponse;
import com.demandhub.system.dto.UserInfoVO;
import com.demandhub.system.entity.Channel;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.RoleGrant;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.ChannelMapper;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.sso.SsoProfile;
import com.demandhub.system.sso.TicketVerifier;
import io.jsonwebtoken.Claims;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCrypt;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.stream.Collectors;

/**
 * 认证主流程（渠道接入版 P2）：
 * - channel-sso：渠道一次性票据回源校验（P2 Mock，P3 接创金零售真实 verify）→ 匹配引擎 → 自有会话；
 * - login：PC 账密登录（BCrypt + 连续失败 5 次锁 15 分钟 + password_updated_at=NULL 强制改密）；
 * - refresh（旋转）/logout/me。
 * 渠道以后端校验结果为准（SSO=渠道码，账密=WEB），不信任前端传值。
 */
@Slf4j
@Service
public class AuthService {

    public static final String CHANNEL_WEB = "WEB";

    private static final String LOGIN_FAIL_KEY = "auth:login:fail:";
    private static final String LOGIN_LOCK_KEY = "auth:login:lock:";

    private final TicketVerifier ticketVerifier;
    private final ChannelUserMatcher channelUserMatcher;
    private final RoleGrantService roleGrantService;
    private final JwtService jwtService;
    private final SessionService sessionService;
    private final UserService userService;
    private final ChannelMapper channelMapper;
    private final OrgSnapshotMapper orgMapper;
    private final AuthProperties authProperties;
    private final StringRedisTemplate redis;

    public AuthService(TicketVerifier ticketVerifier,
                       ChannelUserMatcher channelUserMatcher,
                       RoleGrantService roleGrantService,
                       JwtService jwtService,
                       SessionService sessionService,
                       UserService userService,
                       ChannelMapper channelMapper,
                       OrgSnapshotMapper orgMapper,
                       AuthProperties authProperties,
                       StringRedisTemplate redis) {
        this.ticketVerifier = ticketVerifier;
        this.channelUserMatcher = channelUserMatcher;
        this.roleGrantService = roleGrantService;
        this.jwtService = jwtService;
        this.sessionService = sessionService;
        this.userService = userService;
        this.channelMapper = channelMapper;
        this.orgMapper = orgMapper;
        this.authProperties = authProperties;
        this.redis = redis;
    }

    /**
     * 渠道 SSO 票据登录（FR-M1-01 / AC-03）：票据一次性、TTL 校验、只信服务端回源身份。
     *
     * @param channel 渠道码（入口 URL from=chuangjinls → CHUANGJIN_LS，大小写不敏感）
     * @param ticket  一次性登录票据
     * @param state   入口方带入的随机串（链路追踪用，可空）
     */
    public LoginResponse channelSso(String channel, String ticket, String state) {
        String channelCode = normalizeChannelCode(channel);
        Channel ch = channelMapper.selectOne(new LambdaQueryWrapper<Channel>()
                .eq(Channel::getChannelCode, channelCode));
        if (ch == null || CHANNEL_WEB.equals(ch.getChannelCode())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "该渠道不支持票据登录");
        }
        if (!"ACTIVE".equals(ch.getStatus())) {
            throw new BizException(ErrorCode.CHANNEL_DISABLED);
        }

        SsoProfile profile = ticketVerifier.verify(ch.getChannelCode(), ticket);
        MatchResult match = channelUserMatcher.match(ch.getChannelCode(), profile);
        UserSnapshot user = match.getUser();
        if (user == null) {
            throw new BizException(ErrorCode.USER_NOT_FOUND);
        }
        ensureLoginAllowed(user);
        log.info("渠道 SSO 登录成功: channel={}, userId={}, state={}", channelCode, user.getId(), state);
        user.setDeptPath(userService.buildDeptPath(user.getPrimaryOrgId()));
        return buildLoginResponse(user, ch.getChannelCode());
    }

    /**
     * PC 账密登录（D5）：BCrypt 校验；连续失败 5 次锁定 15 分钟（Redis 计数，审计留痕）；
     * password_updated_at 为 NULL 时返回 mustChangePassword 强制改密。
     */
    public LoginResponse login(String loginName, String password, String clientIp) {
        String lockKey = LOGIN_LOCK_KEY + loginName;
        if (Boolean.TRUE.equals(redis.hasKey(lockKey))) {
            log.warn("账密登录拦截（锁定中）: loginName={}, ip={}", loginName, clientIp);
            throw new BizException(ErrorCode.LOGIN_LOCKED);
        }

        UserSnapshot user = userService.findByLoginName(loginName);
        boolean pass = user != null && user.getPasswordHash() != null
                && BCrypt.checkpw(password, user.getPasswordHash());
        if (!pass) {
            onLoginFailure(loginName, clientIp);
            throw new BizException(ErrorCode.LOGIN_FAILED);
        }
        if (!"ACTIVE".equals(user.getStatus())) {
            log.warn("账密登录拦截（账号不可用 {}）: loginName={}, ip={}", user.getStatus(), loginName, clientIp);
            throw new BizException(ErrorCode.LOGIN_FAILED, "账号不可用，请联系管理员");
        }

        // 成功：清除失败计数与锁定
        redis.delete(LOGIN_FAIL_KEY + loginName);
        redis.delete(lockKey);
        log.info("账密登录成功: loginName={}, userId={}, ip={}", loginName, user.getId(), clientIp);

        userService.touchLastLogin(user.getId(), CHANNEL_WEB);
        user.setDeptPath(userService.buildDeptPath(user.getPrimaryOrgId()));
        return buildLoginResponse(user, CHANNEL_WEB);
    }

    /**
     * 修改密码（强制改密/自助改密）：校验原密码与强度规则；改密后全清会话强制重新登录。
     */
    public void changePassword(String oldPassword, String newPassword) {
        CurrentUser current = UserContext.get();
        if (current == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        UserSnapshot user = userService.findById(current.getId());
        if (user == null || user.getPasswordHash() == null
                || !BCrypt.checkpw(oldPassword, user.getPasswordHash())) {
            throw new BizException(ErrorCode.LOGIN_FAILED, "原密码错误");
        }
        ensurePasswordRule(newPassword);
        userService.updatePassword(user.getId(), BCrypt.hashpw(newPassword, BCrypt.gensalt()));
        sessionService.deleteAllSessionsByUser(String.valueOf(user.getId()));
        log.info("用户改密成功，会话已全清: userId={}", user.getId());
    }

    /**
     * 刷新访问令牌（旋转：旧 refresh 即作废，新 access+refresh 一并签发）
     */
    public LoginResponse refresh(String refreshToken) {
        Claims claims = jwtService.parse(refreshToken);
        if (claims == null || !JwtService.TYPE_REFRESH.equals(claims.get(JwtService.CLAIM_TYPE))) {
            throw new BizException(ErrorCode.REFRESH_TOKEN_INVALID);
        }
        if (!sessionService.refreshExists(claims.getId())) {
            throw new BizException(ErrorCode.REFRESH_TOKEN_INVALID);
        }
        String userId = claims.get(JwtService.CLAIM_USER_ID, String.class);
        UserSnapshot user = userService.findById(Long.parseLong(userId));
        if (user == null) {
            throw new BizException(ErrorCode.USER_NOT_FOUND);
        }
        ensureLoginAllowed(user);
        String channel = claims.get(JwtService.CLAIM_CHANNEL, String.class);
        if (!StringUtils.hasText(channel)) {
            channel = CHANNEL_WEB;
        }
        // 旋转：旧 refresh 立即作废
        sessionService.deleteRefresh(claims.getId());
        user.setDeptPath(userService.buildDeptPath(user.getPrimaryOrgId()));
        return buildLoginResponse(user, channel);
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
     * 当前登录用户信息（含生效授权明细、渠道、类型范围）
     */
    public UserInfoVO me() {
        CurrentUser current = UserContext.get();
        if (current == null) {
            throw new BizException(ErrorCode.UNAUTHORIZED);
        }
        UserSnapshot user = userService.findById(current.getId());
        if (user == null) {
            throw new BizException(ErrorCode.USER_NOT_FOUND);
        }
        user.setDeptPath(userService.buildDeptPath(user.getPrimaryOrgId()));
        return buildUserInfo(user, current.getChannel());
    }

    /** 停用/合并账号不允许建立会话；PENDING（票据字段缺失待完善）不阻塞登录提报（D4） */
    private void ensureLoginAllowed(UserSnapshot user) {
        if ("DISABLED".equals(user.getStatus()) || "MERGED".equals(user.getStatus())) {
            throw new BizException(ErrorCode.USER_NOT_FOUND, "账号不可用（" + user.getStatus() + "），请联系管理员");
        }
    }

    private void onLoginFailure(String loginName, String clientIp) {
        String failKey = LOGIN_FAIL_KEY + loginName;
        Long count = redis.opsForValue().increment(failKey);
        if (count != null && count == 1L) {
            redis.expire(failKey, Duration.ofMinutes(authProperties.getLoginLockMinutes()));
        }
        log.warn("账密登录失败（第 {} 次）: loginName={}, ip={}", count, loginName, clientIp);
        if (count != null && count >= authProperties.getLoginMaxFailures()) {
            redis.opsForValue().set(LOGIN_LOCK_KEY + loginName, "1",
                    Duration.ofMinutes(authProperties.getLoginLockMinutes()));
            redis.delete(failKey);
            log.warn("账密登录锁定 {} 分钟: loginName={}, ip={}", authProperties.getLoginLockMinutes(), loginName, clientIp);
            throw new BizException(ErrorCode.LOGIN_LOCKED);
        }
    }

    /** 密码强度：至少 8 位且包含字母和数字 */
    private void ensurePasswordRule(String password) {
        boolean ok = password != null && password.length() >= 8
                && password.chars().anyMatch(Character::isLetter)
                && password.chars().anyMatch(Character::isDigit);
        if (!ok) {
            throw new BizException(ErrorCode.PASSWORD_RULE_VIOLATION);
        }
    }

    /** from=chuangjinls / channel=chuangjinls 等别名归一到渠道码 */
    private String normalizeChannelCode(String channel) {
        if (!StringUtils.hasText(channel)) {
            throw new BizException(ErrorCode.PARAM_INVALID, "channel 不能为空");
        }
        String code = channel.trim().toUpperCase();
        return "CHUANGJINLS".equals(code) ? "CHUANGJIN_LS" : code;
    }

    private LoginResponse buildLoginResponse(UserSnapshot user, String channel) {
        List<String> roles = roleGrantService.listEffectiveRoleCodes(user.getId());

        String accessToken = jwtService.createAccessToken(user.getId(), user.getUserId(), roles, channel);
        String refreshToken = jwtService.createRefreshToken(user.getId(), user.getUserId(), channel);

        Claims accessClaims = jwtService.parse(accessToken);
        sessionService.saveSession(accessClaims.getId(),
                SessionService.SessionUser.of(user, roles, channel), jwtService.getAccessTtlSeconds());
        Claims refreshClaims = jwtService.parse(refreshToken);
        sessionService.saveRefresh(refreshClaims.getId(), user.getUserId(), jwtService.getRefreshTtlSeconds());

        LoginResponse response = new LoginResponse();
        response.setAccessToken(accessToken);
        response.setRefreshToken(refreshToken);
        response.setExpiresIn(jwtService.getAccessTtlSeconds());
        response.setChannel(channel);
        response.setMustChangePassword(mustChangePassword(user));
        response.setUser(buildUserInfo(user, channel));
        return response;
    }

    /** 有 PC 账号且 password_updated_at 为 NULL → 首次登录强制改密 */
    private boolean mustChangePassword(UserSnapshot user) {
        return user.getLoginName() != null && user.getPasswordUpdatedAt() == null;
    }

    private UserInfoVO buildUserInfo(UserSnapshot user, String channel) {
        List<RoleGrant> grants = roleGrantService.listEffectiveGrants(user.getId());
        Map<Long, String> orgNames = orgMapper.selectList(null).stream()
                .collect(Collectors.toMap(OrgSnapshot::getId, OrgSnapshot::getName, (a, b) -> a));

        UserInfoVO vo = new UserInfoVO();
        vo.setId(user.getId());
        vo.setUserId(user.getUserId());
        vo.setName(user.getName());
        vo.setPrimaryOrgId(user.getPrimaryOrgId());
        vo.setOrgName(orgNames.getOrDefault(user.getPrimaryOrgId(),
                user.getPrimaryOrgId() == null ? null : String.valueOf(user.getPrimaryOrgId())));
        vo.setDeptPath(user.getDeptPath());
        vo.setChannel(channel);
        vo.setRoles(grants.stream().map(RoleGrant::getRoleCode).distinct().toList());
        vo.setTypeScopes(grants.stream()
                .filter(g -> StringUtils.hasText(g.getDemandTypeScope()))
                .flatMap(g -> List.of(g.getDemandTypeScope().split(",")).stream().map(String::trim))
                .collect(Collectors.toCollection(TreeSet::new)).stream().toList());
        vo.setGrants(grants.stream().map(g -> {
            UserInfoVO.GrantVO gvo = new UserInfoVO.GrantVO();
            gvo.setRoleCode(g.getRoleCode());
            gvo.setOrgId(g.getOrgId());
            gvo.setOrgName(g.getOrgId() == null ? "全部组织" : orgNames.getOrDefault(g.getOrgId(), String.valueOf(g.getOrgId())));
            gvo.setDemandTypeScope(g.getDemandTypeScope());
            return gvo;
        }).toList());
        vo.setMustChangePassword(mustChangePassword(user));
        vo.setReadOnly(false);
        return vo;
    }
}
