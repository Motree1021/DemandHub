package com.demandhub.system.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.core.Result;
import com.demandhub.common.exception.BizException;
import com.demandhub.system.dto.MockUserVO;
import com.demandhub.system.entity.Channel;
import com.demandhub.system.entity.ChannelUserMapping;
import com.demandhub.system.entity.OrgSnapshot;
import com.demandhub.system.entity.UserSnapshot;
import com.demandhub.system.mapper.ChannelMapper;
import com.demandhub.system.mapper.ChannelUserMappingMapper;
import com.demandhub.system.mapper.OrgSnapshotMapper;
import com.demandhub.system.mapper.UserSnapshotMapper;
import com.demandhub.system.sso.ChannelSsoConfig;
import com.demandhub.system.sso.SecretCrypto;
import com.demandhub.system.sso.SsoSignUtil;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.Serializable;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Mock 创金零售 SSO 服务（仅 dev：demandhub.channel-sso.mock=true，任务 3.3）。
 * 模拟创金零售侧两个行为：
 * 1) 签发一次性 ticket（Redis 存 60s，模拟其基于自身企微登录态签票）；
 * 2) verify 端点 {@code POST /system/mock-sso/openapi/demandhub/sso/verify} ——
 *    按对接标准 v2.0 §3.3 同一契约实现（X-App-Key/X-Timestamp/X-Nonce/X-Sign 签名校验），
 *    供 ChuangjinLsSsoClient 走真实 HTTP 链路联调；app_key/secret 与 demand_channel.config_json 同源。
 * 场景覆盖（issue 的 scenario 参数）：normal 正常 / expired 票据过期 / 重放(自然消费两次) /
 * no_phone 字段缺失(无手机) / resigned 离职(40004)。
 */
@Slf4j
@Tag(name = "Mock 渠道SSO（仅dev）")
@RestController
@RequestMapping("/system/mock-sso")
@ConditionalOnProperty(name = "demandhub.channel-sso.mock", havingValue = "true", matchIfMissing = true)
public class MockChannelSsoController {

    public static final String TICKET_KEY_PREFIX = "mock:sso:ticket:";
    /** 已消费票据标记（区分 40001 无效/过期 与 40002 重放） */
    private static final String USED_KEY_PREFIX = "mock:sso:used:";
    /** verify 防重放 nonce（5 分钟不重复） */
    private static final String NONCE_KEY_PREFIX = "mock:sso:nonce:";

    private static final long TICKET_TTL_SECONDS = 60;
    private static final long USED_MARK_TTL_SECONDS = 600;
    private static final long NONCE_TTL_SECONDS = 300;
    private static final long TIMESTAMP_TOLERANCE_MS = 5 * 60 * 1000;

    private static final String GETDEL_LUA =
            "local v = redis.call('GET', KEYS[1]); if v then redis.call('DEL', KEYS[1]); end; return v";

    private final ChannelUserMappingMapper mappingMapper;
    private final UserSnapshotMapper userMapper;
    private final OrgSnapshotMapper orgMapper;
    private final ChannelMapper channelMapper;
    private final SecretCrypto secretCrypto;
    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final DefaultRedisScript<String> getdelScript = new DefaultRedisScript<>(GETDEL_LUA, String.class);

    public MockChannelSsoController(ChannelUserMappingMapper mappingMapper,
                                    UserSnapshotMapper userMapper,
                                    OrgSnapshotMapper orgMapper,
                                    ChannelMapper channelMapper,
                                    SecretCrypto secretCrypto,
                                    StringRedisTemplate redis) {
        this.mappingMapper = mappingMapper;
        this.userMapper = userMapper;
        this.orgMapper = orgMapper;
        this.channelMapper = channelMapper;
        this.secretCrypto = secretCrypto;
        this.redis = redis;
    }

    @Operation(summary = "Mock 创金零售入口：可选用户列表（已建 CHUANGJIN_LS 映射的 ACTIVE 用户）")
    @GetMapping("/entry")
    public Result<List<MockUserVO>> entry() {
        List<ChannelUserMapping> mappings = mappingMapper.selectList(new LambdaQueryWrapper<ChannelUserMapping>()
                .eq(ChannelUserMapping::getChannelCode, "CHUANGJIN_LS"));
        Map<Long, UserSnapshot> users = userMapper.selectBatchIds(
                        mappings.stream().map(ChannelUserMapping::getDemandUserId).distinct().toList())
                .stream().collect(Collectors.toMap(UserSnapshot::getId, Function.identity()));
        Map<Long, String> orgNames = orgMapper.selectList(null).stream()
                .collect(Collectors.toMap(OrgSnapshot::getId, OrgSnapshot::getName, (a, b) -> a));
        List<MockUserVO> list = mappings.stream()
                .map(m -> {
                    UserSnapshot u = users.get(m.getDemandUserId());
                    if (u == null || !"ACTIVE".equals(u.getStatus())) {
                        return null;
                    }
                    MockUserVO vo = new MockUserVO();
                    vo.setChannelUserId(m.getChannelUserId());
                    vo.setName(u.getName());
                    vo.setOrgName(u.getPrimaryOrgId() == null ? null : orgNames.get(u.getPrimaryOrgId()));
                    return vo;
                })
                .filter(java.util.Objects::nonNull)
                .toList();
        return Result.ok(list);
    }

    @Operation(summary = "Mock 签发一次性 ticket（60s 有效；scenario: normal/expired/no_phone/resigned）")
    @PostMapping("/ticket")
    public Result<IssuedTicketVO> issue(@RequestBody TicketIssueRequest request) {
        if (!StringUtils.hasText(request.getChannelUserId())) {
            throw new BizException(ErrorCode.PARAM_INVALID, "channelUserId 不能为空");
        }
        String scenario = StringUtils.hasText(request.getScenario()) ? request.getScenario() : "normal";
        Map<String, Object> payload = buildPayload(request, scenario);
        String ticket = UUID.randomUUID().toString().replace("-", "");
        if (!"expired".equals(scenario)) {
            // expired 场景模拟"签出时已过期"：不下发存储，verify 侧取不到 → 40001
            try {
                redis.opsForValue().set(TICKET_KEY_PREFIX + ticket,
                        objectMapper.writeValueAsString(payload), Duration.ofSeconds(TICKET_TTL_SECONDS));
            } catch (Exception e) {
                throw new IllegalStateException("Mock 票据签发失败", e);
            }
        }
        log.info("Mock 签票: scenario={}, channelUserId={}, ticket={}", scenario, request.getChannelUserId(),
                SsoSignUtil.maskTicket(ticket));
        IssuedTicketVO vo = new IssuedTicketVO();
        vo.setTicket(ticket);
        vo.setExpiresIn(TICKET_TTL_SECONDS);
        return Result.ok(vo);
    }

    /**
     * Mock verify 端点（模拟创金零售服务端，对接标准 §3.3 同一契约）。
     * 校验：app_key → 时间戳偏差≤5分钟 → nonce 5分钟不重复 → HMAC 签名 → 票据一次性消费；
     * 响应为契约原文（errcode/errmsg/user/ticket_expire_at），不套 Result 包装。
     */
    @Operation(summary = "Mock verify（契约同 §3.3，供 ChuangjinLsSsoClient 真实 HTTP 联调）")
    @PostMapping(SsoSignUtil.VERIFY_PATH)
    public Map<String, Object> verify(@RequestHeader(value = "X-App-Key", required = false) String appKey,
                                      @RequestHeader(value = "X-Timestamp", required = false) String timestamp,
                                      @RequestHeader(value = "X-Nonce", required = false) String nonce,
                                      @RequestHeader(value = "X-Sign", required = false) String sign,
                                      @RequestBody String rawBody) {
        ChannelSsoConfig config = loadMockSideConfig();
        // 1. 服务间鉴权：app_key / 时间戳 / nonce 防重放 / 签名（任一失败 → 40003）
        if (config == null || !StringUtils.hasText(appKey) || !appKey.equals(config.getAppKey())) {
            log.warn("Mock verify 鉴权失败(app_key): appKey={}", appKey);
            return err(40003, "app_key invalid");
        }
        long ts;
        try {
            ts = Long.parseLong(timestamp == null ? "" : timestamp);
        } catch (NumberFormatException e) {
            ts = -1;
        }
        if (ts <= 0 || Math.abs(System.currentTimeMillis() - ts) > TIMESTAMP_TOLERANCE_MS) {
            log.warn("Mock verify 鉴权失败(timestamp 偏差>5分钟): timestamp={}", timestamp);
            return err(40003, "timestamp expired");
        }
        if (!StringUtils.hasText(nonce)
                || !Boolean.TRUE.equals(redis.opsForValue().setIfAbsent(NONCE_KEY_PREFIX + nonce, "1",
                        Duration.ofSeconds(NONCE_TTL_SECONDS)))) {
            log.warn("Mock verify 鉴权失败(nonce 重复): nonce={}", nonce);
            return err(40003, "nonce replayed");
        }
        String expected = SsoSignUtil.hmacSha256Hex(config.getAppSecret(),
                SsoSignUtil.stringToSign(SsoSignUtil.VERIFY_PATH, appKey, timestamp, nonce, rawBody));
        if (!StringUtils.hasText(sign) || !MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.UTF_8), sign.toLowerCase().getBytes(StandardCharsets.UTF_8))) {
            log.warn("Mock verify 鉴权失败(sign 不匹配): nonce={}", nonce);
            return err(40003, "sign invalid");
        }

        // 2. 参数：ticket 缺失 → 40005
        String ticket = null;
        try {
            JsonNode body = objectMapper.readTree(rawBody);
            ticket = body.path("ticket").isTextual() ? body.get("ticket").asText() : null;
        } catch (Exception e) {
            log.warn("Mock verify 请求体非 JSON: {}", e.getMessage());
        }
        if (!StringUtils.hasText(ticket)) {
            return err(40005, "ticket required");
        }

        // 3. 一次性消费（Lua 原子 GET+DEL，兼容 Redis 3.0）；取不到时分流：已消费 → 40002 重放，否则 → 40001 无效/过期
        String json = redis.execute(getdelScript, List.of(TICKET_KEY_PREFIX + ticket));
        if (json == null) {
            boolean used = Boolean.TRUE.equals(redis.hasKey(USED_KEY_PREFIX + ticket));
            log.warn("Mock verify 票据被拒: ticket={}, used={}", SsoSignUtil.maskTicket(ticket), used);
            return used ? err(40002, "ticket already used") : err(40001, "ticket invalid or expired");
        }
        redis.opsForValue().set(USED_KEY_PREFIX + ticket, "1", Duration.ofSeconds(USED_MARK_TTL_SECONDS));

        try {
            JsonNode payload = objectMapper.readTree(json);
            // 离职/停用场景 → 40004
            if ("resigned".equals(payload.path("scenario").asText(""))) {
                log.info("Mock verify 离职场景: ticket={}", SsoSignUtil.maskTicket(ticket));
                return err(40004, "user resigned");
            }
            Map<String, Object> user = new LinkedHashMap<>();
            for (String field : List.of("user_id", "name", "phone", "dept_id", "dept_name", "dept_path",
                    "employee_no", "email")) {
                JsonNode v = payload.get(field);
                user.put(field, v == null || v.isNull() ? null : v.asText());
            }
            Map<String, Object> ok = new LinkedHashMap<>();
            ok.put("errcode", 0);
            ok.put("errmsg", "ok");
            ok.put("user", user);
            ok.put("ticket_expire_at", payload.path("expire_at").asLong());
            log.info("Mock verify 成功: channelUserId={}, phone={}", user.get("user_id"),
                    SsoSignUtil.maskPhone((String) user.get("phone")));
            return ok;
        } catch (Exception e) {
            log.warn("Mock verify 票据载荷解析失败: {}", e.getMessage());
            return err(40001, "ticket invalid or expired");
        }
    }

    /** Mock 侧服务间鉴权配置：与 DemandHub 调用侧同源（demand_channel.config_json），密钥同样经 ENC 解密 */
    private ChannelSsoConfig loadMockSideConfig() {
        Channel channel = channelMapper.selectOne(new LambdaQueryWrapper<Channel>()
                .eq(Channel::getChannelCode, "CHUANGJIN_LS"));
        ChannelSsoConfig config = channel == null ? null : ChannelSsoConfig.parse(channel.getConfigJson());
        if (config == null || !config.isComplete()) {
            return null;
        }
        config.setAppSecret(secretCrypto.decryptIfMarked(config.getAppSecret()));
        return config;
    }

    private Map<String, Object> err(int errcode, String errmsg) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("errcode", errcode);
        map.put("errmsg", errmsg);
        return map;
    }

    /** 票据载荷：契约 user 字段（snake_case）+ scenario + expire_at；已建档用户按库内信息回源，未建档按参数构造 */
    private Map<String, Object> buildPayload(TicketIssueRequest request, String scenario) {
        ChannelUserMapping mapping = mappingMapper.selectOne(new LambdaQueryWrapper<ChannelUserMapping>()
                .eq(ChannelUserMapping::getChannelCode, "CHUANGJIN_LS")
                .eq(ChannelUserMapping::getChannelUserId, request.getChannelUserId()));
        UserSnapshot user = mapping != null ? userMapper.selectById(mapping.getDemandUserId()) : null;
        // dev 种子用户同时写了 demand_user.wecom_userid，映射缺失时兜底直查
        if (user == null) {
            user = userMapper.selectOne(new LambdaQueryWrapper<UserSnapshot>()
                    .eq(UserSnapshot::getWecomId, request.getChannelUserId()));
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("user_id", request.getChannelUserId());
        if (user != null) {
            payload.put("name", StringUtils.hasText(request.getName()) ? request.getName() : user.getName());
            payload.put("phone", StringUtils.hasText(request.getPhone()) ? request.getPhone() : user.getPhone());
            payload.put("employee_no", user.getEmployeeNo());
            payload.put("email", user.getEmail());
            if (user.getPrimaryOrgId() != null) {
                OrgSnapshot org = orgMapper.selectById(user.getPrimaryOrgId());
                if (org != null) {
                    payload.put("dept_id", org.getExternalDeptId());
                    payload.put("dept_name", org.getName());
                }
            }
        } else {
            payload.put("name", StringUtils.hasText(request.getName()) ? request.getName() : "渠道新员工");
            payload.put("phone", request.getPhone());
            payload.put("dept_id", request.getDeptId());
            payload.put("dept_name", request.getDeptName());
        }
        // no_phone 场景：强制手机为空（模拟敏感字段授权受限，不阻塞登录）
        if ("no_phone".equals(scenario)) {
            payload.put("phone", null);
        }
        payload.put("scenario", scenario);
        payload.put("expire_at", System.currentTimeMillis() + TICKET_TTL_SECONDS * 1000);
        return payload;
    }

    @Data
    public static class TicketIssueRequest implements Serializable {
        /** 渠道侧用户 ID（Mock 企微 userid，如 wq_u_mgr_tech；新人员工可自定义） */
        private String channelUserId;
        /** 场景：normal(默认) / expired(票据过期) / no_phone(字段缺失无手机) / resigned(离职40004)；重放场景自然消费两次即可 */
        private String scenario;
        /** 以下为新人员工可选字段（已建档用户忽略，按库内信息回源） */
        private String name;
        private String phone;
        private String deptId;
        private String deptName;
    }

    @Data
    public static class IssuedTicketVO implements Serializable {
        private String ticket;
        private Long expiresIn;
    }
}
