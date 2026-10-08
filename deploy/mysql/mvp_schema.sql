-- =============================================================
-- DemandHub 科技需求收集智能体 · MVP 数据库初始化（Python 栈）
-- 依据：server/app/db/models.py（SQLAlchemy 现行模型）v1.0
-- 目标：MySQL 8.4 实例（127.0.0.1:3307）
-- 说明：本脚本与 deploy/mysql/init/*.sql（旧 Java 栈 schema）无关，
--       仅创建 MVP 6 张表；字段命名遵循 Snake Case。
-- =============================================================

CREATE DATABASE IF NOT EXISTS demandhub DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE demandhub;

-- 1. dh_user 渠道回源用户
CREATE TABLE IF NOT EXISTS dh_user (
    id            BIGINT       NOT NULL AUTO_INCREMENT,
    name          VARCHAR(64)  NOT NULL,
    wecom_userid  VARCHAR(64)  NOT NULL,
    phone         VARCHAR(32)  NULL,
    employee_no   VARCHAR(32)  NULL,
    email         VARCHAR(128) NULL,
    dept_id       VARCHAR(32)  NULL,
    dept_name     VARCHAR(128) NULL,
    dept_path     VARCHAR(512) NULL,
    channel       VARCHAR(32)  NOT NULL DEFAULT 'CHUANGJIN_LS',
    status        VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    last_login_at DATETIME(3)  NULL,
    created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_dh_user_wecom (wecom_userid)
) ENGINE = InnoDB COMMENT = '渠道回源用户';

-- 2. prompt_version 不可变标准与提示词快照
CREATE TABLE IF NOT EXISTS prompt_version (
    id           BIGINT      NOT NULL AUTO_INCREMENT,
    code         VARCHAR(64) NOT NULL,
    version      VARCHAR(32) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    snapshot     JSON        NOT NULL,
    created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_prompt_version_hash (content_hash)
) ENGINE = InnoDB COMMENT = '不可变标准与提示词快照';

-- 3. demand 草稿与正式需求（核心）
CREATE TABLE IF NOT EXISTS demand (
    id                  BIGINT       NOT NULL AUTO_INCREMENT,
    demand_no           VARCHAR(40)  NULL,
    title               VARCHAR(256) NULL,
    demand_type_code    VARCHAR(32)  NULL,
    subtype_code        VARCHAR(32)  NULL,
    content             TEXT         NULL,
    urgency             VARCHAR(16)  NOT NULL DEFAULT 'NORMAL',
    expect_delivery_at  DATE         NULL,
    ext                 JSON         NOT NULL,
    quality             JSON         NULL,
    field_sources       JSON         NOT NULL,
    revision            INT          NOT NULL DEFAULT 0,
    client_request_id   VARCHAR(64)  NOT NULL,
    create_request_hash VARCHAR(64)  NOT NULL,
    standard_version_id BIGINT       NULL,
    quality_content_hash VARCHAR(64) NULL,
    status              VARCHAR(16)  NOT NULL DEFAULT 'DRAFT',
    submitter_id        BIGINT       NOT NULL,
    submitter_name      VARCHAR(64)  NULL,
    submitter_dept      VARCHAR(128) NULL,
    channel             VARCHAR(32)  NULL,
    session_id          BIGINT       NULL,
    submitted_at        DATETIME(3)  NULL,
    closed_at           DATETIME(3)  NULL,
    close_reason        VARCHAR(256) NULL,
    created_at          DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at          DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_demand_create (submitter_id, client_request_id),
    UNIQUE KEY uq_demand_no (demand_no),
    UNIQUE KEY uq_demand_session (session_id),
    KEY ix_demand_owner_status (submitter_id, status),
    KEY ix_demand_type_status (demand_type_code, status),
    KEY ix_demand_submitted (submitted_at),
    CONSTRAINT fk_demand_prompt_version FOREIGN KEY (standard_version_id) REFERENCES prompt_version (id),
    CONSTRAINT fk_demand_user FOREIGN KEY (submitter_id) REFERENCES dh_user (id)
) ENGINE = InnoDB COMMENT = '草稿与正式需求';

-- 4. demand_no_seq 按类型按日编号流水
CREATE TABLE IF NOT EXISTS demand_no_seq (
    biz_date  DATE        NOT NULL,
    type_code VARCHAR(32) NOT NULL,
    seq       INT         NOT NULL DEFAULT 0,
    PRIMARY KEY (biz_date, type_code)
) ENGINE = InnoDB COMMENT = '按类型按日编号流水';

-- 5. agent_session 每份草稿唯一启发会话
CREATE TABLE IF NOT EXISTS agent_session (
    id           BIGINT       NOT NULL AUTO_INCREMENT,
    session_no   VARCHAR(64)  NOT NULL,
    user_id      BIGINT       NOT NULL,
    scene        VARCHAR(32)  NOT NULL DEFAULT 'SUBMIT_GUIDE',
    demand_id    BIGINT       NOT NULL,
    title        VARCHAR(256) NULL,
    status       VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    asked_target VARCHAR(64)  NULL,
    created_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_agent_session_no (session_no),
    UNIQUE KEY uq_agent_session_demand (demand_id),
    CONSTRAINT fk_session_user FOREIGN KEY (user_id) REFERENCES dh_user (id),
    CONSTRAINT fk_session_demand FOREIGN KEY (demand_id) REFERENCES demand (id)
) ENGINE = InnoDB COMMENT = '每份草稿唯一启发会话';

-- 6. agent_message Agent 消息与幂等响应
CREATE TABLE IF NOT EXISTS agent_message (
    id                BIGINT      NOT NULL AUTO_INCREMENT,
    session_id        BIGINT      NOT NULL,
    role              VARCHAR(16) NOT NULL,
    content           TEXT        NOT NULL,
    structured_payload JSON       NULL,
    request_id        VARCHAR(64) NULL,
    request_hash      VARCHAR(64) NULL,
    prompt_version_id BIGINT      NULL,
    model             VARCHAR(64) NULL,
    prompt_tokens     INT         NULL,
    completion_tokens INT         NULL,
    latency_ms        INT         NULL,
    created_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uq_message_request_role (session_id, request_id, role),
    CONSTRAINT fk_message_session FOREIGN KEY (session_id) REFERENCES agent_session (id),
    CONSTRAINT fk_message_prompt_version FOREIGN KEY (prompt_version_id) REFERENCES prompt_version (id)
) ENGINE = InnoDB COMMENT = 'Agent 消息与幂等响应';
