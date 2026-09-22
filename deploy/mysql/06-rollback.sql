-- =========================================================
-- DemandHub 用户域重建回滚脚本（06-rebuild-user-domain.sql 的逆操作）
-- 作用：删除新五表，恢复改名保留的旧三表（demand_user_snapshot / demand_org_snapshot / 旧 demand_role_grant）
-- 注意：全新库（无 *_legacy 表）执行本脚本会清空用户域表结构，仅用于全新环境回退到无用户域状态；
--       旧库执行后业务回到 snapshot 方案，Java 侧需同步回退代码版本。
-- 执行：docker exec -i demandhub-mysql mysql -uroot -pdemandhub123 demandhub < deploy/mysql/06-rollback.sql
-- 注意：本脚本不可放入 mysql/init/（docker-entrypoint-initdb.d 会按字母序自动执行全部 .sql，全新初始化时会把新表 DROP 掉）
-- =========================================================

SET NAMES utf8mb4;
USE demandhub;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------- 1) 删除新五表 ----------
DROP TABLE IF EXISTS channel_user_mapping;
DROP TABLE IF EXISTS demand_role_grant;
DROP TABLE IF EXISTS demand_channel;
DROP TABLE IF EXISTS demand_user;
DROP TABLE IF EXISTS demand_org;

-- ---------- 2) 恢复旧三表（存在才恢复） ----------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.TABLES
                WHERE TABLE_SCHEMA='demandhub' AND TABLE_NAME='demand_user_snapshot_legacy') > 0,
               'RENAME TABLE demand_user_snapshot_legacy TO demand_user_snapshot', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.TABLES
                WHERE TABLE_SCHEMA='demandhub' AND TABLE_NAME='demand_org_snapshot_legacy') > 0,
               'RENAME TABLE demand_org_snapshot_legacy TO demand_org_snapshot', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.TABLES
                WHERE TABLE_SCHEMA='demandhub' AND TABLE_NAME='demand_role_grant_legacy') > 0,
               'RENAME TABLE demand_role_grant_legacy TO demand_role_grant', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET FOREIGN_KEY_CHECKS = 1;
