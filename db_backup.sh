#!/bin/bash
# Nightly MySQL backup with 7-day retention (scheduled via cron at 02:00).
#
# Credentials are NOT stored in this script. mysqldump reads them from
# ~/.my.cnf (chmod 600) of the deploy user:
#
#   [mysqldump]
#   user=rocha
#   password=<db-password>

set -euo pipefail

BACKUP_DIR="/backups"

mysqldump \
  --single-transaction \
  --routines \
  --triggers \
  --no-tablespaces \
  rochadb \
  | gzip > "${BACKUP_DIR}/rochadb_$(date +%F_%H%M).sql.gz"

# Keep only the last 7 days of backups
find "${BACKUP_DIR}" -name "*.sql.gz" -mtime +7 -delete
