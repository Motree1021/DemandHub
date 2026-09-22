package com.demandhub.system.sso;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

/**
 * 渠道密钥落库加解密（任务 3.1：app_secret 落库脱敏不回显；对接标准 §3.4：密钥不进日志）。
 * config_json 中 app_secret 以 "ENC:" + Base64(iv(12B) ‖ 密文+GCM tag) 存储（AES-GCM，随机 IV）；
 * 无 ENC 前缀按明文兼容（仅 dev 便利）；MyBatis 行级日志/接口出参只见密文，解密仅发生在服务端内存。
 * 密钥来源：demandhub.channel-sso.secret-store-key（生产经环境变量 SECRET_STORE_KEY 注入）。
 */
@Component
public class SecretCrypto {

    public static final String ENC_PREFIX = "ENC:";
    private static final int IV_LENGTH = 12;
    private static final int GCM_TAG_BITS = 128;

    /** dev 默认主密钥（仅开发环境；生产必须经 SECRET_STORE_KEY 覆盖） */
    private static final String DEV_DEFAULT_KEY = "demandhub-dev-secret-store-key-0123456789";

    private final SecretKeySpec key;

    public SecretCrypto(@Value("${demandhub.channel-sso.secret-store-key:demandhub-dev-secret-store-key-0123456789}")
                        String storeKey) {
        this.key = new SecretKeySpec(sha256(storeKey), "AES");
    }

    /** 解密：ENC: 前缀 → AES-GCM 解密；否则原样返回（明文兼容） */
    public String decryptIfMarked(String value) {
        if (!StringUtils.hasText(value) || !value.startsWith(ENC_PREFIX)) {
            return value;
        }
        try {
            byte[] packed = Base64.getDecoder().decode(value.substring(ENC_PREFIX.length()));
            byte[] iv = new byte[IV_LENGTH];
            System.arraycopy(packed, 0, iv, 0, IV_LENGTH);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(GCM_TAG_BITS, iv));
            byte[] plain = cipher.doFinal(packed, IV_LENGTH, packed.length - IV_LENGTH);
            return new String(plain, StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new IllegalStateException("渠道密钥解密失败（检查 secret-store-key 配置）", e);
        }
    }

    public String encrypt(String plain) {
        try {
            byte[] iv = new byte[IV_LENGTH];
            new SecureRandom().nextBytes(iv);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(GCM_TAG_BITS, iv));
            byte[] ct = cipher.doFinal(plain.getBytes(StandardCharsets.UTF_8));
            byte[] packed = new byte[IV_LENGTH + ct.length];
            System.arraycopy(iv, 0, packed, 0, IV_LENGTH);
            System.arraycopy(ct, 0, packed, IV_LENGTH, ct.length);
            return ENC_PREFIX + Base64.getEncoder().encodeToString(packed);
        } catch (Exception e) {
            throw new IllegalStateException("渠道密钥加密失败", e);
        }
    }

    private static byte[] sha256(String s) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(s.getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    /** 生成落库密文：java SecretCrypto <plain> [storeKey]（用于种子/管理端写库前加密） */
    public static void main(String[] args) {
        if (args.length < 1) {
            System.err.println("usage: SecretCrypto <plain> [storeKey]");
            System.exit(2);
        }
        SecretCrypto crypto = new SecretCrypto(args.length > 1 ? args[1] : DEV_DEFAULT_KEY);
        System.out.println(crypto.encrypt(args[0]));
    }
}
