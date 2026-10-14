#!/usr/bin/env bash
# DemandHub MySQL 备份脚本（生产/TEST 通用）
# 用法：DB_PASSWORD=xxx ./backup_mysql.sh [备份目录]
# 环境变量：DB_HOST(默认127.0.0.1) DB_PORT(默认3306) DB_USER(默认root) DB_NAME(默认demandhub) DB_PASSWORD(必填) KEEP_DAYS(默认14)
# 策略：--single-transaction 热备不锁表；gzip 压缩；保留 KEEP_DAYS 天；产出后校验非空且含建表语句。
set -euo pipefail

BACKUP_DIR="${1:-/opt/demandhub/backup}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-root}"
DB_NAME="${DB_NAME:-demandhub}"
KEEP_DAYS="${KEEP_DAYS:-14}"
: "${DB_PASSWORD:?必须提供 DB_PASSWORD 环境变量}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="$BACKUP_DIR/${DB_NAME}_${STAMP}.sql.gz"

export MYSQL_PWD="$DB_PASSWORD"
mysqldump -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" \
  --single-transaction --routines --triggers --set-gtid-purged=OFF \
  "$DB_NAME" | gzip > "$FILE"
unset MYSQL_PWD

# 产物校验：非空且解压后含 CREATE TABLE（防止静默产出空包）
[ -s "$FILE" ] || { echo "备份产物为空: $FILE" >&2; exit 1; }
zcat "$FILE" | grep -q "CREATE TABLE" || { echo "备份产物缺建表语句: $FILE" >&2; exit 1; }

# 轮转：清理 KEEP_DAYS 天前的备份
find "$BACKUP_DIR" -name "${DB_NAME}_*.sql.gz" -mtime +"$KEEP_DAYS" -delete

echo "backup-ok file=$FILE size=$(stat -c%s "$FILE")"
