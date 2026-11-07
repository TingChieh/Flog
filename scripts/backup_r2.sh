#!/usr/bin/env bash
# Back the whole site up to a Cloudflare R2 bucket. Run it on the production
# server (by hand, or from cron / a systemd timer); it needs rclone and mysqldump.
#
# Usage: scripts/backup_r2.sh [--dry-run]
#   --dry-run   show what would be uploaded and deleted; change nothing
#
# What goes where, under <bucket>/<BACKUP_PREFIX>/:
#   db/flog-<stamp>.sql.gz   a database dump per run; dumps older than
#                            BACKUP_KEEP_DAYS days are deleted
#   env/env-<stamp>          a copy of .env per run, same retention
#   uploads/                 a mirror of the upload folder (images and podcast
#                            audio). Only new or changed files are sent, so
#                            repeat runs are cheap. Files deleted on the server
#                            are moved to uploads-removed/<stamp>/ rather than
#                            destroyed; those folders are purged after the same
#                            BACKUP_KEEP_DAYS.
#
# Settings: in .env.backup at the repository root (git-ignored, like .env; override
# the path with FLOG_BACKUP_ENV): a shell file of KEY=value lines; environment
# variables win over it. Required:
# R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, BACKUP_UPLOADS
# (the app's UPLOAD_FOLDER), BACKUP_ENV_FILE (the app's .env). Optional:
# BACKUP_PREFIX (default flog), BACKUP_KEEP_DAYS (default 30), BACKUP_DB_NAME
# (default flog). Use an R2 API token limited to this one bucket.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
settings=${FLOG_BACKUP_ENV:-$root/.env.backup}
if [[ -f "$settings" ]]; then
    # Keep variables that are already set: the environment overrides the file.
    while IFS='=' read -r key value; do
        if [[ -z "${!key:-}" ]]; then export "$key=${value//[\"\']/}"; fi
    done < <(grep -E '^(R2|BACKUP)_[A-Z_]+=' "$settings")
fi

dry_run=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=(--dry-run) ;;
        -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

: "${R2_ACCOUNT_ID:?set R2_ACCOUNT_ID in $settings}"
: "${R2_ACCESS_KEY_ID:?set R2_ACCESS_KEY_ID in $settings}"
: "${R2_SECRET_ACCESS_KEY:?set R2_SECRET_ACCESS_KEY in $settings}"
BUCKET=${R2_BUCKET:?set R2_BUCKET in $settings}
UPLOADS=${BACKUP_UPLOADS:?set BACKUP_UPLOADS in $settings}
ENV_FILE=${BACKUP_ENV_FILE:?set BACKUP_ENV_FILE in $settings}
PREFIX=${BACKUP_PREFIX:-flog}
KEEP_DAYS=${BACKUP_KEEP_DAYS:-30}
DB_NAME=${BACKUP_DB_NAME:-flog}

command -v rclone >/dev/null || { echo "rclone is not installed" >&2; exit 1; }
[[ -d "$UPLOADS" ]] || { echo "BACKUP_UPLOADS is not a directory: $UPLOADS" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "BACKUP_ENV_FILE is not a file: $ENV_FILE" >&2; exit 1; }

# rclone reads its remote from the environment, so no config file (and no
# secret on disk besides the settings file) is needed.
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY
export RCLONE_CONFIG_R2_ENDPOINT="https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com"
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
remote="R2:$BUCKET/$PREFIX"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

stamp=$(date -u +%Y%m%dT%H%M%SZ)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
chmod 700 "$work"

log "Dumping database $DB_NAME"
mysqldump --single-transaction --routines "$DB_NAME" | gzip > "$work/flog-$stamp.sql.gz"
# An empty or truncated dump must never replace a good backup silently.
gzip -t "$work/flog-$stamp.sql.gz"
[[ $(gzip -dc "$work/flog-$stamp.sql.gz" | head -c 1000 | wc -c) -gt 100 ]] \
    || { echo "database dump looks empty" >&2; exit 1; }
cp -p "$ENV_FILE" "$work/env-$stamp"

log "Uploading database dump and .env"
rclone copyto "${dry_run[@]}" "$work/flog-$stamp.sql.gz" "$remote/db/flog-$stamp.sql.gz"
rclone copyto "${dry_run[@]}" "$work/env-$stamp" "$remote/env/env-$stamp"

log "Mirroring uploads"
rclone sync "${dry_run[@]}" "$UPLOADS" "$remote/uploads" \
    --backup-dir "$remote/uploads-removed/$stamp" --transfers 4 --stats-one-line -v

log "Removing backups older than $KEEP_DAYS days"
for folder in db env; do
    rclone delete "${dry_run[@]}" "$remote/$folder" --min-age "${KEEP_DAYS}d" --rmdirs
done
# uploads-removed/<stamp>/ holds files with their old modification times, so
# --min-age would delete them at once; judge each folder by the stamp in its name.
cutoff=$(date -u -d "$KEEP_DAYS days ago" +%Y%m%dT%H%M%SZ 2>/dev/null \
    || date -u -v-"${KEEP_DAYS}d" +%Y%m%dT%H%M%SZ)
while IFS= read -r old; do
    old=${old%/}
    if [[ "$old" =~ ^[0-9]{8}T[0-9]{6}Z$ && "$old" < "$cutoff" ]]; then
        rclone purge "${dry_run[@]}" "$remote/uploads-removed/$old"
    fi
done < <(rclone lsf --dirs-only "$remote/uploads-removed" 2>/dev/null || true)

log "Done: $remote ($stamp)"
