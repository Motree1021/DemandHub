package com.demandhub.system.sso;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * 创金零售 SSO 客户端（任务 3.2，对接标准 v2.0 §3.3）。
 * verify 调用：POST {ls_base_url}/openapi/demandhub/sso/verify，
 * 请求头 X-App-Key / X-Timestamp(毫秒,偏差≤5分钟) / X-Nonce(5分钟不重复) / X-Sign(HMAC-SHA256 十六进制小写)；
 * 超时 3s 快速失败不重试；连续失败熔断降级（不放行任何未核验身份）；
 * 上游 errcode 40001~40005 映射本地错误码与 AC-07 文案；请求/响应留痕且 ticket/phone 脱敏。
 */
@Slf4j
@Component
public class ChuangjinLsSsoClient implements ChannelSsoClient {

    public static final String CHANNEL_CODE = "CHUANGJIN_LS";

    /** AC-07 文案（异常态用户提示，错误码+文案即 H5 维护提示约定，页面 P5 实现） */
    public static final String MSG_REENTER = "登录已失效，请从创金零售重新进入";
    public static final String MSG_UNAVAILABLE = "登录服务暂时不可用，请稍后重试";

    /** 熔断：连续 3 次传输层失败开启 30s，开启期间快速失败（票据仅 60s 有效，重试无意义） */
    private static final int BREAKER_FAILURE_THRESHOLD = 3;
    private static final long BREAKER_OPEN_MS = 30_000;

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final AtomicInteger consecutiveFailures = new AtomicInteger();
    private volatile long breakerOpenUntilMs = 0L;

    @Override
    public String channelCode() {
        return CHANNEL_CODE;
    }

    @Override
    public SsoProfile verify(ChannelSsoConfig config, String ticket) {
        if (!StringUtils.hasText(ticket)) {
            throw new BizException(ErrorCode.CHANNEL_TICKET_INVALID, MSG_REENTER);
        }
        failFastIfBreakerOpen();

        String body = "{\"ticket\":\"" + ticket + "\"}";
        String timestamp = String.valueOf(System.currentTimeMillis());
        String nonce = UUID.randomUUID().toString().replace("-", "");
        String sign = SsoSignUtil.hmacSha256Hex(config.getAppSecret(),
                SsoSignUtil.stringToSign(SsoSignUtil.VERIFY_PATH, config.getAppKey(), timestamp, nonce, body));

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(config.getSsoVerifyBaseUrl() + SsoSignUtil.VERIFY_PATH))
                .timeout(Duration.ofMillis(config.getTimeoutMs()))
                .header("Content-Type", "application/json")
                .header("X-App-Key", config.getAppKey())
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Sign", sign)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        long startMs = System.currentTimeMillis();
        HttpResponse<String> response;
        try {
            response = httpClient(config).send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            onTransportFailure("verify 调用异常: " + e.getClass().getSimpleName(), config, ticket, startMs);
            throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE);
        }
        long costMs = System.currentTimeMillis() - startMs;

        if (response.statusCode() != 200) {
            // 5xx/非 200：创金零售服务异常，计入熔断
            onTransportFailure("verify HTTP " + response.statusCode(), config, ticket, startMs);
            throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE);
        }

        JsonNode root;
        try {
            root = objectMapper.readTree(response.body());
        } catch (Exception e) {
            onTransportFailure("verify 响应非 JSON", config, ticket, startMs);
            throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE);
        }

        int errcode = root.path("errcode").asInt(-1);
        log.info("渠道 verify 留痕: channel={}, appKey={}, nonce={}, errcode={}, ticket={}, costMs={}",
                CHANNEL_CODE, config.getAppKey(), nonce, errcode, SsoSignUtil.maskTicket(ticket), costMs);

        if (errcode == 0) {
            consecutiveFailures.set(0);
            return toProfile(root.path("user"), ticket);
        }
        throw mapUpstreamError(errcode, root.path("errmsg").asText(""), ticket);
    }

    /** 上游错误码映射（对接标准 §3.3 错误响应表 + AC-07 文案） */
    private BizException mapUpstreamError(int errcode, String errmsg, String ticket) {
        switch (errcode) {
            case 40001: // ticket 无效或过期
            case 40002: // ticket 已被使用（防重放）
                log.warn("渠道票据被拒({}): ticket={}, errmsg={}", errcode, SsoSignUtil.maskTicket(ticket), errmsg);
                return new BizException(ErrorCode.CHANNEL_TICKET_INVALID, MSG_REENTER);
            case 40003: // 签名/鉴权失败：告警（配置错误或伪造调用），不暴露细节
                log.error("渠道 verify 鉴权失败告警(40003): ticket={}, errmsg={}（检查 app_key/app_secret 配置）",
                        SsoSignUtil.maskTicket(ticket), errmsg);
                return new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE);
            case 40004: // 用户已离职/停用
                log.warn("渠道用户不可用(40004): ticket={}", SsoSignUtil.maskTicket(ticket));
                return new BizException(ErrorCode.CHANNEL_ACCOUNT_UNAVAILABLE);
            case 40005: // 参数缺失：告警并引导重新进入
                log.warn("渠道 verify 参数缺失告警(40005): ticket={}, errmsg={}", SsoSignUtil.maskTicket(ticket), errmsg);
                return new BizException(ErrorCode.CHANNEL_TICKET_INVALID, MSG_REENTER);
            default:   // 500xx 及未知错误：服务异常
                log.error("渠道 verify 未知错误({}): ticket={}, errmsg={}", errcode, SsoSignUtil.maskTicket(ticket), errmsg);
                return new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE);
        }
    }

    /** 契约 user 字段映射（snake_case → SsoProfile）；user_id/name 必填，缺失按服务异常告警 */
    private SsoProfile toProfile(JsonNode user, String ticket) {
        SsoProfile profile = new SsoProfile();
        profile.setUserId(text(user, "user_id"));
        profile.setName(text(user, "name"));
        profile.setPhone(text(user, "phone"));
        profile.setDeptId(text(user, "dept_id"));
        profile.setDeptName(text(user, "dept_name"));
        profile.setDeptPath(text(user, "dept_path"));
        profile.setEmployeeNo(text(user, "employee_no"));
        profile.setEmail(text(user, "email"));
        if (!StringUtils.hasText(profile.getUserId()) || !StringUtils.hasText(profile.getName())) {
            log.error("渠道 verify 成功但必填身份字段缺失告警: ticket={}, hasUserId={}, hasName={}",
                    SsoSignUtil.maskTicket(ticket), StringUtils.hasText(profile.getUserId()),
                    StringUtils.hasText(profile.getName()));
            throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE);
        }
        log.info("渠道身份回源成功: channelUserId={}, name={}, phone={}, deptId={}",
                profile.getUserId(), profile.getName(), SsoSignUtil.maskPhone(profile.getPhone()), profile.getDeptId());
        return profile;
    }

    /** 熔断器：开启期间快速失败（不放行未核验身份）；半开放行单请求试探 */
    private void failFastIfBreakerOpen() {
        long openUntil = breakerOpenUntilMs;
        if (openUntil > 0 && System.currentTimeMillis() < openUntil) {
            log.warn("渠道 verify 熔断中，快速失败（{}ms 后恢复）", openUntil - System.currentTimeMillis());
            throw new BizException(ErrorCode.AUTH_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE);
        }
    }

    private void onTransportFailure(String reason, ChannelSsoConfig config, String ticket, long startMs) {
        int failures = consecutiveFailures.incrementAndGet();
        long costMs = System.currentTimeMillis() - startMs;
        log.warn("渠道 verify 传输失败({}/{}): reason={}, baseUrl={}, ticket={}, costMs={}",
                failures, BREAKER_FAILURE_THRESHOLD, reason, config.getSsoVerifyBaseUrl(),
                SsoSignUtil.maskTicket(ticket), costMs);
        if (failures >= BREAKER_FAILURE_THRESHOLD) {
            breakerOpenUntilMs = System.currentTimeMillis() + BREAKER_OPEN_MS;
            consecutiveFailures.set(0);
            log.error("渠道 verify 连续失败熔断告警: baseUrl={}, 熔断 {}ms（不放行任何未核验身份）",
                    config.getSsoVerifyBaseUrl(), BREAKER_OPEN_MS);
        }
    }

    private HttpClient httpClient(ChannelSsoConfig config) {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(config.getTimeoutMs()))
                .build();
    }

    private static String text(JsonNode node, String field) {
        JsonNode v = node.get(field);
        return v == null || v.isNull() ? null : v.asText();
    }
}
