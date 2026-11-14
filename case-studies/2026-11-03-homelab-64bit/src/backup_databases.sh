#!/bin/bash
set -euo pipefail

BACKUP_DIR="~/backups/databases"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

echo "=== [$(date)] Starting Database Backups ==="

# 1. PostgreSQL 16 (Umami & Gitea)
if docker ps --format '{{.Names}}' | grep -q "^projects-db-1$"; then
    echo "Backing up PostgreSQL 16 (projects-db-1)..."
    docker exec projects-db-1 pg_dumpall -U umami | gzip > "${BACKUP_DIR}/postgres_umami_gitea_${DATE}.sql.gz"
    echo "Saved: ${BACKUP_DIR}/postgres_umami_gitea_${DATE}.sql.gz ($(du -sh "${BACKUP_DIR}/postgres_umami_gitea_${DATE}.sql.gz" | cut -f1))"
fi

# 2. Ghost MySQL
if docker ps --format '{{.Names}}' | grep -q "^projects-ghost-db-1$"; then
    echo "Backing up MySQL (projects-ghost-db-1)..."
    GHOST_PASS=$(docker inspect projects-ghost-db-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^MYSQL_PASSWORD=' | cut -d= -f2-)
    docker exec -e MYSQL_PWD="$GHOST_PASS" projects-ghost-db-1 mysqldump -u ghostuser --single-transaction --quick --no-tablespaces ghostdb | gzip > "${BACKUP_DIR}/mysql_ghostdb_${DATE}.sql.gz"
    echo "Saved: ${BACKUP_DIR}/mysql_ghostdb_${DATE}.sql.gz ($(du -sh "${BACKUP_DIR}/mysql_ghostdb_${DATE}.sql.gz" | cut -f1))"
fi

# 3. Immich PostgreSQL
if docker ps --format '{{.Names}}' | grep -q "^immich_postgres$"; then
    echo "Backing up Immich PostgreSQL (immich_postgres)..."
    docker exec immich_postgres pg_dumpall -U postgres | gzip > "${BACKUP_DIR}/postgres_immich_${DATE}.sql.gz"
    echo "Saved: ${BACKUP_DIR}/postgres_immich_${DATE}.sql.gz ($(du -sh "${BACKUP_DIR}/postgres_immich_${DATE}.sql.gz" | cut -f1))"
fi

# Rotate backups older than 7 days
echo "Pruning backups older than 7 days..."
find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime +7 -delete

echo "=== [$(date)] All Backups Completed Successfully! ==="
