package com.demandhub.system.sso;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;

/**
 * 渠道 SSO 签名与日志脱敏工具（对接标准 v2.0 §3.3）：
 * X-Sign = HMAC-SHA256(app_secret, "POST\n{path}\n{X-App-Key}\n{X-Timestamp}\n{X-Nonce}\n{body原文}") 十六进制小写。
 * 客户端（ChuangjinLsSsoClient）与 Mock verify 端点共用同一实现，保证契约一致。
 */
public final class SsoSignUtil {

    /** 契约固定接口路径（不含域名），签名与 URL 拼接均使用 */
    public static final String VERIFY_PATH = "/openapi/demandhub/sso/verify";

    private SsoSignUtil() {
    }

    /** 待签名字符串：POST\n{path}\n{appKey}\n{timestamp}\n{nonce}\n{body原文} */
    public static String stringToSign(String path, String appKey, String timestamp, String nonce, String body) {
        return "POST\n" + path + "\n" + appKey + "\n" + timestamp + "\n" + nonce + "\n" + (body == null ? "" : body);
    }

    /** HMAC-SHA256 十六进制小写 */
    public static String hmacSha256Hex(String secret, String data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] digest = mac.doFinal(data.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(digest.length * 2);
            for (byte b : digest) {
                sb.append(Character.forDigit((b >> 4) & 0xF, 16));
                sb.append(Character.forDigit(b & 0xF, 16));
            }
            return sb.toString();
        } catch (Exception e) {
            throw new IllegalStateException("HMAC-SHA256 签名失败", e);
        }
    }

    /** 票据脱敏：仅保留前 4 位（ticket 为敏感凭证，不入日志原文） */
    public static String maskTicket(String ticket) {
        if (ticket == null || ticket.isEmpty()) {
            return "***";
        }
        return ticket.length() <= 4 ? "***" : ticket.substring(0, 4) + "***";
    }

    /** 手机号脱敏：138****0000 */
    public static String maskPhone(String phone) {
        if (phone == null || phone.length() < 7) {
            return phone == null ? null : "***";
        }
        return phone.substring(0, 3) + "****" + phone.substring(phone.length() - 4);
    }
}
