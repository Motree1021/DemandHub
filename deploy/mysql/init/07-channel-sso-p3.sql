SET NAMES utf8mb4;
-- =====================================================================
-- P3：创金零售 SSO 渠道适配器 + Mock 联调（开发计划 v2.0 任务 3.1~3.6）
-- 1) channel_dept_unmapped：verify 部门未映射校准清单（任务 3.5，P4 管理端展示）
-- 2) CHUANGJIN_LS config_json 落 dev 可用配置（任务 3.1/3.6）：
--    dev 的 sso_verify_base_url 指向内置 Mock verify（channel-sso.mock=true），
--    test/prod 由管理端/环境注入真实创金零售地址与独立密钥（app_secret 不入仓库、不回显）。
-- 幂等：CREATE IF NOT EXISTS + UPDATE，可在已有库重复执行。
-- =====================================================================

CREATE TABLE IF NOT EXISTS channel_dept_unmapped (
  id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  channel_code          VARCHAR(32)  NOT NULL COMMENT '渠道码',
  dept_id               VARCHAR(32)  NOT NULL COMMENT '渠道侧部门ID（verify回传，demand_org.external_dept_id 未命中）',
  dept_name             VARCHAR(128) NULL,
  dept_path             VARCHAR(256) NULL,
  sample_channel_user_id VARCHAR(64) NULL COMMENT '最近命中该部门的渠道用户ID（排查样本）',
  hit_count             INT          NOT NULL DEFAULT 1 COMMENT '未映射命中次数',
  first_seen_at         DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  last_seen_at          DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_channel_dept (channel_code, dept_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='渠道部门未映射校准清单（任务3.5，P4管理端展示）';

-- dev：verify 回源指向内置 Mock 端点（系统服务直连 8081，模拟创金零售服务端）；
-- app_key/app_secret 为 dev 专用假值，Mock 侧与调用侧同源读取本配置完成签名校验；
-- app_secret 落库为 AES-GCM 密文（ENC: 前缀，主密钥 dev 默认 demandhub-dev-secret-store-key-0123456789，
-- 生产经环境变量 SECRET_STORE_KEY 注入；明文 app_secret=dev-chuangjinls-secret-9f3c7a21b5e8d0f4 仅 dev 使用）。
UPDATE demand_channel SET config_json = JSON_OBJECT(
  'sso_verify_base_url', 'http://localhost:8081/system/mock-sso',
  'app_key',             'demandhub-dev',
  'app_secret',          'ENC:dUWOVqCbFi5tz4GO0QbR7epWMj7VaEtDnL9lM9Jw87Jo33zlOVQlP6oWQz+3gZLJ8ZwnmZoox2wu3+zxVnsvCqy6fw==',
  'ticket_ttl_seconds',  60,
  'timeout_ms',          3000
) WHERE channel_code = 'CHUANGJIN_LS';
