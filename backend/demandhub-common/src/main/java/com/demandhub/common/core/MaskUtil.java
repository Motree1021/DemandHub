package com.demandhub.common.core;

/**
 * 敏感字段脱敏（NFR 安全：手机号/邮箱出参脱敏）。
 * 仅用于出参展示，库中仍存明文（主数据来自权限中心同步）。
 */
public final class MaskUtil {

    private MaskUtil() {
    }

    /** 手机号：保留前 3 后 2，中间打码；不足 6 位全打码 */
    public static String phone(String phone) {
        if (phone == null || phone.isEmpty()) {
            return phone;
        }
        if (phone.length() < 6) {
            return "****";
        }
        return phone.substring(0, 3) + "****" + phone.substring(phone.length() - 2);
    }

    /** 邮箱：本地部分首字符 + *** + 域名；无 @ 按普通串打码 */
    public static String email(String email) {
        if (email == null || email.isEmpty()) {
            return email;
        }
        int at = email.indexOf('@');
        if (at <= 0) {
            return email.charAt(0) + "***";
        }
        return email.charAt(0) + "***" + email.substring(at);
    }
}
