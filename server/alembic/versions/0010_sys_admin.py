"""P5 系统管理：字典/需求类型/渠道/组织树/渠道部门未映射五表 + 种子。

- sys_dict：业务字典（URGENCY/CLOSE_REASON/HOLD_REASON/TECH_SUBTYPE/RELATED_SYSTEM 21 项种子）
- demand_type：需求类型注册（表管注册/启停/状态机绑定；五区字段标准仍走 yaml 快照）
  sla_config / parent_type_code 为蓝本预留列，一期透传不参与业务
- demand_channel：渠道注册（只做登记/启停；SSO 对接参数走 .env 不迁表，config_json 蓝本预留列）
- demand_org：组织树（物化路径 /100/110/ 尾斜杠；900=外部虚拟组织，渠道部门未映射兜底挂载点）
- channel_dept_unmapped：渠道部门未映射校准清单（登录未命中时 upsert 计数，管理员校准后删行）
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    # ---- 业务字典 ----
    op.execute(sa.text("""
        CREATE TABLE sys_dict (
          id         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          dict_type  VARCHAR(64)  NOT NULL COMMENT '字典分组，如 URGENCY/CLOSE_REASON',
          item_code  VARCHAR(64)  NOT NULL COMMENT '字典项编码',
          item_name  VARCHAR(128) NOT NULL COMMENT '字典项名称',
          sort       INT          NOT NULL DEFAULT 0 COMMENT '排序',
          status     VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
          created_at DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_dict (dict_type, item_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='业务字典'
    """))

    # ---- 需求类型（表管注册/启停/状态机绑定；五区字段标准仍走 yaml 快照） ----
    op.execute(sa.text("""
        CREATE TABLE demand_type (
          id                BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
          type_code         VARCHAR(32) NOT NULL COMMENT '类型编码（大写字母/数字/下划线）',
          type_name         VARCHAR(64) NOT NULL COMMENT '类型名称',
          parent_type_code  VARCHAR(32)          COMMENT '父类型编码（蓝本预留，一期不用）',
          default_org_id    BIGINT               COMMENT '默认承接组织（demand_org.id）',
          state_machine_key VARCHAR(64) NOT NULL DEFAULT 'DEFAULT' COMMENT '绑定状态机配置 key',
          sla_config        JSON                 COMMENT '类型级 SLA 配置（蓝本预留，一期不用，走 sla_config 表）',
          sort              INT         NOT NULL DEFAULT 0 COMMENT '排序',
          status            VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
          created_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_type_code (type_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求类型'
    """))

    # ---- 渠道注册（只做登记/启停；SSO 对接参数走 .env 不迁表） ----
    op.execute(sa.text("""
        CREATE TABLE demand_channel (
          id               BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
          channel_code     VARCHAR(32) NOT NULL COMMENT '渠道码',
          channel_name     VARCHAR(64) NOT NULL COMMENT '渠道名称',
          app_id           VARCHAR(64)          COMMENT '渠道侧应用ID',
          callback_enabled TINYINT(1)  NOT NULL DEFAULT 0 COMMENT '回调是否启用',
          status           VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
          config_json      JSON                 COMMENT '渠道配置（蓝本预留：SSO 对接参数走 .env 不迁表）',
          created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_channel_code (channel_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求来源渠道'
    """))

    # ---- 组织树（物化路径尾斜杠格式） ----
    op.execute(sa.text("""
        CREATE TABLE demand_org (
          id               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          name             VARCHAR(128) NOT NULL COMMENT '组织名称',
          level            VARCHAR(16)  NOT NULL COMMENT 'LINE 业务线/DEPT 部门/GROUP 小组',
          parent_id        BIGINT       NOT NULL DEFAULT 0 COMMENT '父组织（0=根）',
          path             VARCHAR(512) NOT NULL COMMENT '物化路径，如 /100/110/（尾斜杠，子树前缀匹配）',
          org_kind         VARCHAR(16)           COMMENT 'REPORTER 提报侧/ASSIGNER 承接侧/BOTH 双向',
          external_flag    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否外部虚拟组织',
          external_dept_id VARCHAR(32)           COMMENT '渠道侧部门ID（票据登录部门映射用）',
          status           VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
          created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          KEY idx_parent (parent_id),
          KEY idx_path (path),
          KEY idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='组织树'
    """))

    # ---- 渠道部门未映射校准清单 ----
    op.execute(sa.text("""
        CREATE TABLE channel_dept_unmapped (
          id                     BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          channel_code           VARCHAR(32)  NOT NULL COMMENT '渠道码',
          dept_id                VARCHAR(32)  NOT NULL COMMENT '渠道侧部门ID（verify回传，demand_org.external_dept_id 未命中）',
          dept_name              VARCHAR(128)          COMMENT '渠道侧部门名',
          dept_path              VARCHAR(256)          COMMENT '渠道侧部门路径',
          sample_channel_user_id VARCHAR(64)           COMMENT '最近命中该部门的渠道用户ID（排查样本）',
          hit_count              INT          NOT NULL DEFAULT 1 COMMENT '未映射命中次数',
          first_seen_at          DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '首次命中时间',
          last_seen_at           DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最近命中时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_channel_dept (channel_code, dept_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='渠道部门未映射校准清单'
    """))

    # ---- 种子：组织树（id 保留 100~141 + 900 外部虚拟组织） ----
    op.execute(sa.text("""
        INSERT IGNORE INTO demand_org(id, name, level, parent_id, path, org_kind, external_flag, status) VALUES
        (100, '创金合信零售业务线', 'LINE',  0,   '/100/',        'BOTH',     0, 'ACTIVE'),
        (110, '财管科技产品部',     'DEPT',  100, '/100/110/',    'BOTH',     0, 'ACTIVE'),
        (111, '科技产品一组',       'GROUP', 110, '/100/110/111/', 'ASSIGNER', 0, 'ACTIVE'),
        (112, '科技产品二组',       'GROUP', 110, '/100/110/112/', 'ASSIGNER', 0, 'ACTIVE'),
        (120, '客户陪伴服务部',     'DEPT',  100, '/100/120/',    'BOTH',     0, 'ACTIVE'),
        (121, '客户陪伴一组',       'GROUP', 120, '/100/120/121/', 'ASSIGNER', 0, 'ACTIVE'),
        (130, '培训开发部',         'DEPT',  100, '/100/130/',    'BOTH',     0, 'ACTIVE'),
        (131, '培训开发一组',       'GROUP', 130, '/100/130/131/', 'ASSIGNER', 0, 'ACTIVE'),
        (140, '零售一线营业部',     'DEPT',  100, '/100/140/',    'REPORTER', 0, 'ACTIVE'),
        (141, '营业部一组',         'GROUP', 140, '/100/140/141/', 'REPORTER', 0, 'ACTIVE'),
        (900, '外部/待确认',        'DEPT',  0,   '/900/',        NULL,       1, 'ACTIVE')
    """))

    # ---- 种子：需求类型（default_org_id 指向组织种子；五区标准仍走 yaml） ----
    op.execute(sa.text("""
        INSERT IGNORE INTO demand_type(type_code, type_name, default_org_id, state_machine_key, sort) VALUES
        ('TECH',  '科技需求', 111, 'DEFAULT', 1),
        ('MATL',  '物料需求', 121, 'DEFAULT', 2),
        ('TRAIN', '培训需求', 131, 'DEFAULT', 3)
    """))

    # ---- 种子：渠道注册（一期启用 WEB + CHUANGJIN_LS，其余预留 DISABLED；SSO 配置走 .env） ----
    op.execute(sa.text("""
        INSERT IGNORE INTO demand_channel(channel_code, channel_name, callback_enabled, status) VALUES
        ('WEB',          'PC管理端',       0, 'ACTIVE'),
        ('CHUANGJIN_LS', '创金零售小程序', 0, 'ACTIVE'),
        ('WECOM_APP',    '企微应用',       0, 'DISABLED'),
        ('WECOM_BOT',    '企微机器人',     0, 'DISABLED'),
        ('FEISHU_BOT',   '飞书机器人',     0, 'DISABLED'),
        ('DOUBAO_WORK',  '豆包工作台',     0, 'DISABLED'),
        ('WORKBUDDY',    '工作伙伴',       0, 'DISABLED'),
        ('VOICE',        '语音渠道',       0, 'DISABLED')
    """))

    # ---- 种子：业务字典（RELATED_SYSTEM 存储值取 item_name，与历史自由文本兼容） ----
    op.execute(sa.text("""
        INSERT IGNORE INTO sys_dict(dict_type, item_code, item_name, sort) VALUES
        ('URGENCY',        'NORMAL',       '普通',         1),
        ('URGENCY',        'URGENT',       '紧急',         2),
        ('URGENCY',        'CRITICAL',     '特急',         3),
        ('CLOSE_REASON',   'NOT_ACCEPTED', '不受理',       1),
        ('CLOSE_REASON',   'DUPLICATE',    '重复需求',     2),
        ('CLOSE_REASON',   'REVOKED',      '提报人撤销',   3),
        ('HOLD_REASON',    'WAIT_EXTERNAL','等待外部依赖', 1),
        ('HOLD_REASON',    'WAIT_RESOURCE','等待资源',     2),
        ('HOLD_REASON',    'OTHER',        '其他',         9),
        ('TECH_SUBTYPE',   'SYS_DEV',      '系统开发',     1),
        ('TECH_SUBTYPE',   'DATA_RPT',     '数据报表',     2),
        ('TECH_SUBTYPE',   'SYS_INT',      '系统集成',     3),
        ('TECH_SUBTYPE',   'OPS_OPT',      '运维优化',     4),
        ('TECH_SUBTYPE',   'OTHER',        '其他',         5),
        ('RELATED_SYSTEM', 'DIRECT_SALES', '代销系统',     1),
        ('RELATED_SYSTEM', 'CRM',          'CRM',          2),
        ('RELATED_SYSTEM', 'DATA_CENTER',  '数据中心',     3),
        ('RELATED_SYSTEM', 'ORG_PLATFORM', '机构服务平台', 4),
        ('RELATED_SYSTEM', 'PORTAL',       '官网/APP',     5),
        ('RELATED_SYSTEM', 'OTHER',        '其他',         6)
    """))


def downgrade():
    for table in ("channel_dept_unmapped", "demand_org", "demand_channel", "demand_type", "sys_dict"):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
