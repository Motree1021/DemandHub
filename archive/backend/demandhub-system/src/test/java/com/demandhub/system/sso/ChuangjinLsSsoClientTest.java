package com.demandhub.system.sso;

import com.demandhub.common.core.ErrorCode;
import com.demandhub.common.exception.BizException;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * ChuangjinLsSsoClient 契约单测（P7 任务 7.1）：MockWebServer 模拟创金零售 verify。
 * 覆盖：正常回源、上游 40001~40005 五类异常、必填字段缺失、非 200 / 非 JSON、
 * 超时快速失败、连续失败熔断后不再耗票；异常映射断言与 phase3/phase6 契约口径一致。
 */
class ChuangjinLsSsoClientTest {

    private static final String APP_KEY = "demandhub-test";
    private static final String APP_SECRET = "test-secret-0123456789";
    private static final String TICKET = "T-abc123";

    private MockWebServer server;
    private ChuangjinLsSsoClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();
        // 每用例新实例：熔断状态（consecutiveFailures/breakerOpenUntilMs）实例级隔离
        client = new ChuangjinLsSsoClient();
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    private ChannelSsoConfig config(int timeoutMs) {
        ChannelSsoConfig c = new ChannelSsoConfig();
        // server.url("") 末尾带 "/"，VERIFY_PATH 以 "/" 开头，去尾斜杠避免双斜杠
        c.setSsoVerifyBaseUrl(server.url("").toString().replaceAll("/$", ""));
        c.setAppKey(APP_KEY);
        c.setAppSecret(APP_SECRET);
        c.setTimeoutMs(timeoutMs);
        return c;
    }

    private void enqueueSuccess(String userJson) {
        server.enqueue(new MockResponse().setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"errcode\":0,\"errmsg\":\"ok\",\"user\":" + userJson + "}"));
    }

    private void enqueueErrcode(int errcode) {
        server.enqueue(new MockResponse().setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("{\"errcode\":" + errcode + ",\"errmsg\":\"upstream err\"}"));
    }

    private static BizException assertBiz(Runnable r, ErrorCode code) {
        BizException ex = assertThrows(BizException.class, r::run);
        assertEquals(code.getCode(), ex.getCode());
        return ex;
    }

    @Test
    void success_mapsProfileFields() {
        enqueueSuccess("{\"user_id\":\"wq_u_001\",\"name\":\"张三\",\"phone\":\"13800001111\","
                + "\"dept_id\":\"D100\",\"dept_name\":\"零售线\",\"dept_path\":\"根/零售线\","
                + "\"employee_no\":\"E001\",\"email\":\"a@b.c\"}");

        SsoProfile p = client.verify(config(3000), TICKET);

        assertEquals("wq_u_001", p.getUserId());
        assertEquals("张三", p.getName());
        assertEquals("13800001111", p.getPhone());
        assertEquals("D100", p.getDeptId());
        assertEquals("零售线", p.getDeptName());
        assertEquals("根/零售线", p.getDeptPath());
        assertEquals("E001", p.getEmployeeNo());
        assertEquals("a@b.c", p.getEmail());
    }

    @Test
    void success_requestContract_signatureHeadersAndBody() throws Exception {
        enqueueSuccess("{\"user_id\":\"wq_u_001\",\"name\":\"张三\"}");

        client.verify(config(3000), TICKET);

        RecordedRequest req = server.takeRequest(1, TimeUnit.SECONDS);
        assertNotNull(req);
        // 契约路径与四签名头（对接标准 §3.3，与 phase3/phase6 口径一致）
        assertEquals(SsoSignUtil.VERIFY_PATH, req.getPath());
        assertEquals(APP_KEY, req.getHeader("X-App-Key"));
        String timestamp = req.getHeader("X-Timestamp");
        String nonce = req.getHeader("X-Nonce");
        String sign = req.getHeader("X-Sign");
        assertNotNull(timestamp);
        assertNotNull(nonce);
        assertNotNull(sign);
        String body = req.getBody().readUtf8();
        assertEquals("{\"ticket\":\"" + TICKET + "\"}", body);
        // 用同一实现重算签名，必须一致（HMAC-SHA256 十六进制小写）
        String expected = SsoSignUtil.hmacSha256Hex(APP_SECRET,
                SsoSignUtil.stringToSign(SsoSignUtil.VERIFY_PATH, APP_KEY, timestamp, nonce, body));
        assertEquals(expected, sign);
    }

    @Test
    void errcode40001_ticketInvalid_mapsToTicketInvalidWithReenterMsg() {
        enqueueErrcode(40001);
        BizException ex = assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.CHANNEL_TICKET_INVALID);
        assertEquals(ChuangjinLsSsoClient.MSG_REENTER, ex.getMessage());
    }

    @Test
    void errcode40002_ticketReplayed_mapsToTicketInvalid() {
        enqueueErrcode(40002);
        BizException ex = assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.CHANNEL_TICKET_INVALID);
        assertEquals(ChuangjinLsSsoClient.MSG_REENTER, ex.getMessage());
    }

    @Test
    void errcode40003_signFailed_mapsToServiceUnavailable() {
        enqueueErrcode(40003);
        BizException ex = assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.AUTH_SERVICE_UNAVAILABLE);
        assertEquals(ChuangjinLsSsoClient.MSG_UNAVAILABLE, ex.getMessage());
    }

    @Test
    void errcode40004_accountUnavailable_mapsToChannelAccountUnavailable() {
        enqueueErrcode(40004);
        assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.CHANNEL_ACCOUNT_UNAVAILABLE);
    }

    @Test
    void errcode40005_paramMissing_mapsToTicketInvalid() {
        enqueueErrcode(40005);
        BizException ex = assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.CHANNEL_TICKET_INVALID);
        assertEquals(ChuangjinLsSsoClient.MSG_REENTER, ex.getMessage());
    }

    @Test
    void successButMissingRequiredUserId_mapsToServiceUnavailable() {
        // user_id/name 必填，缺失按协议异常告警（v2.1 口径：不允许放行残缺身份）
        enqueueSuccess("{\"name\":\"张三\"}");
        assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.AUTH_SERVICE_UNAVAILABLE);
    }

    @Test
    void httpNon200_mapsToServiceUnavailableAndCountsBreaker() {
        server.enqueue(new MockResponse().setResponseCode(500).setBody("oops"));
        assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.AUTH_SERVICE_UNAVAILABLE);
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void nonJsonResponse_mapsToServiceUnavailable() {
        server.enqueue(new MockResponse().setResponseCode(200).setBody("not-json"));
        assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.AUTH_SERVICE_UNAVAILABLE);
    }

    @Test
    void timeout_failsFastWithoutRetry() {
        // 上游挂起（响应头 5s 不下发），客户端 300ms 超时：快速失败不重试（对接标准 3s 快速失败）。
        // 注：必须用 headersDelay 模拟——JDK HttpClient 超时在收到响应头后即解除，bodyDelay 不会触发超时
        server.enqueue(new MockResponse().setResponseCode(200)
                .setBody("{}").setHeadersDelay(5, TimeUnit.SECONDS));
        long start = System.currentTimeMillis();
        assertBiz(() -> client.verify(config(300), TICKET), ErrorCode.AUTH_SERVICE_UNAVAILABLE);
        long cost = System.currentTimeMillis() - start;
        assertTrue(cost < 2500, "超时快速失败，实际耗时 " + cost + "ms");
        assertEquals(1, server.getRequestCount());
    }

    @Test
    void breakerOpensAfter3ConsecutiveFailures_subsequentCallFailsFastWithoutHttp() {
        // 连续 3 次传输层失败（HTTP 500）→ 熔断开启；开启期间快速失败不再消耗票据
        for (int i = 0; i < 3; i++) {
            server.enqueue(new MockResponse().setResponseCode(500).setBody("oops"));
        }
        for (int i = 0; i < 3; i++) {
            assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.AUTH_SERVICE_UNAVAILABLE);
        }
        assertEquals(3, server.getRequestCount());

        // 第 4 次：熔断开启，快速失败，不再发 HTTP（票据仅 60s，重试无意义）
        assertBiz(() -> client.verify(config(3000), TICKET), ErrorCode.AUTH_SERVICE_UNAVAILABLE);
        assertEquals(3, server.getRequestCount(), "熔断开启期间不应再调用上游");
    }

    @Test
    void blankTicket_rejectedBeforeHttp() {
        assertBiz(() -> client.verify(config(3000), " "), ErrorCode.CHANNEL_TICKET_INVALID);
        assertEquals(0, server.getRequestCount());
    }
}
