#!/usr/bin/env bash
# Back the whole site up to a Cloudflare R2 bucket (or an isolated local folder
# for non-production drills). Run on the production server by hand or via a
# systemd timer; production mode needs rclone, mysqldump, gzip, and python3.
#
# Usage: scripts/backup_r2.sh [--dry-run]
#   --dry-run   show what would be uploaded and deleted; change nothing
#
# What goes where, under <bucket>/<BACKUP_PREFIX>/:
#   db/flog-<stamp>.sql.gz          database dump per run (gzip + size verified)
#   env/env-<stamp>                 copy of .env per run
#   manifests/manifest-<stamp>.json SHA-256 checksums + retention metadata
#   uploads/                        mirror of the upload folder; deleted files
#                                   move to uploads-removed/<stamp>/
#
# Retention policy:
#   Always keep at least BACKUP_MIN_KEEP (default 7) newest snapshots even if
#   older than BACKUP_KEEP_DAYS (default 30). Snapshots beyond BACKUP_MIN_KEEP
#   are pruned once older than BACKUP_KEEP_DAYS.
#
# Failure alerting:
#   On error, triggers BACKUP_ALERT_CMD (if set) or `.venv/bin/flask backup alert`
#   (which logs and sends email/webhook via Flog's configured alert channels).
#   Set BACKUP_ALERT_DISABLE=1 to suppress alerting in manual local runs.
#
# Settings: in .env.backup at the repository root (git-ignored; override path
# with FLOG_BACKUP_ENV). Environment variables override the settings file.
# Production (BACKUP_STORAGE=rclone, default):
#   R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET,
#   BACKUP_UPLOADS, BACKUP_ENV_FILE.
# Local non-production drill (BACKUP_STORAGE=local):
#   BACKUP_LOCAL_ROOT, R2_BUCKET (label), BACKUP_UPLOADS, BACKUP_ENV_FILE.
# Optional:
#   BACKUP_PREFIX (default flog), BACKUP_KEEP_DAYS (default 30),
#   BACKUP_MIN_KEEP (default 7), BACKUP_DB_BACKEND (mysql|sqlite, default mysql),
#   BACKUP_DB_NAME (default flog), BACKUP_DB_PATH (for sqlite),
#   BACKUP_ALERT_CMD, BACKUP_ALERT_WEBHOOK, BACKUP_PYTHON.
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
is_dry_run=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=(--dry-run); is_dry_run=1 ;;
        -h|--help) sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

STORAGE=${BACKUP_STORAGE:-rclone}
DB_BACKEND=${BACKUP_DB_BACKEND:-mysql}
BUCKET=${R2_BUCKET:?set R2_BUCKET in $settings}
UPLOADS=${BACKUP_UPLOADS:?set BACKUP_UPLOADS in $settings}
ENV_FILE=${BACKUP_ENV_FILE:?set BACKUP_ENV_FILE in $settings}
PREFIX=${BACKUP_PREFIX:-flog}
KEEP_DAYS=${BACKUP_KEEP_DAYS:-30}
MIN_KEEP=${BACKUP_MIN_KEEP:-7}
DB_NAME=${BACKUP_DB_NAME:-flog}
DB_PATH=${BACKUP_DB_PATH:-}
PYTHON_BIN=${BACKUP_PYTHON:-}
if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "$root/.venv/bin/python" ]]; then
        PYTHON_BIN="$root/.venv/bin/python"
    else
        PYTHON_BIN=$(command -v python3 || true)
    fi
fi

[[ -n "$PYTHON_BIN" ]] || { echo "python3 is required for manifest and retention calculations" >&2; exit 1; }
[[ "$KEEP_DAYS" =~ ^[1-9][0-9]*$ ]] || { echo "BACKUP_KEEP_DAYS must be a positive integer" >&2; exit 2; }
[[ "$MIN_KEEP" =~ ^[1-9][0-9]*$ ]] || { echo "BACKUP_MIN_KEEP must be a positive integer" >&2; exit 2; }
[[ -d "$UPLOADS" ]] || { echo "BACKUP_UPLOADS is not a directory: $UPLOADS" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "BACKUP_ENV_FILE is not a file: $ENV_FILE" >&2; exit 1; }

if [[ "$STORAGE" == "rclone" ]]; then
    : "${R2_ACCOUNT_ID:?set R2_ACCOUNT_ID in $settings}"
    : "${R2_ACCESS_KEY_ID:?set R2_ACCESS_KEY_ID in $settings}"
    : "${R2_SECRET_ACCESS_KEY:?set R2_SECRET_ACCESS_KEY in $settings}"
    command -v rclone >/dev/null || { echo "rclone is not installed" >&2; exit 1; }
    export RCLONE_CONFIG_R2_TYPE=s3
    export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
    export RCLONE_CONFIG_R2_ACCESS_KEY_ID=$R2_ACCESS_KEY_ID
    export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=$R2_SECRET_ACCESS_KEY
    export RCLONE_CONFIG_R2_ENDPOINT="https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com"
    export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
    remote="R2:$BUCKET/$PREFIX"
elif [[ "$STORAGE" == "local" ]]; then
    LOCAL_ROOT=${BACKUP_LOCAL_ROOT:?set BACKUP_LOCAL_ROOT when BACKUP_STORAGE=local}
    remote="$LOCAL_ROOT/$BUCKET/$PREFIX"
else
    echo "Unsupported BACKUP_STORAGE: $STORAGE (expected rclone or local)" >&2
    exit 2
fi

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

stamp=$(date -u +%Y%m%dT%H%M%SZ)
work=$(mktemp -d)
chmod 700 "$work"
CURRENT_STAGE="init"
ALERT_SENT=0

send_failure_alert() {
    local stage="$1" rc="$2" detail="$3"
    if [[ "${BACKUP_ALERT_DISABLE:-0}" == "1" || "$ALERT_SENT" == "1" ]]; then
        return 0
    fi
    ALERT_SENT=1
    if [[ -n "${BACKUP_ALERT_CMD:-}" ]]; then
        BACKUP_ALERT_STAGE="$stage" \
        BACKUP_ALERT_EXIT_CODE="$rc" \
        BACKUP_ALERT_STAMP="$stamp" \
        BACKUP_ALERT_TARGET="$remote" \
        BACKUP_ALERT_MESSAGE="$detail" \
        bash -c "$BACKUP_ALERT_CMD" || echo "Warning: BACKUP_ALERT_CMD failed" >&2
        return 0
    fi
    if [[ -x "$root/.venv/bin/flask" ]]; then
        (
            cd "$root"
            FLASK_APP=flog.py "$root/.venv/bin/flask" backup alert \
                --stage "$stage" \
                --exit-code "$rc" \
                --detail "$detail" \
                --stamp "$stamp" \
                --target "$remote" \
                ${BACKUP_ALERT_WEBHOOK:+--webhook "$BACKUP_ALERT_WEBHOOK"}
        ) || echo "Warning: flask backup alert failed" >&2
    fi
}

LAST_ERROR_CMD=""
on_error() {
    LAST_ERROR_CMD="${BASH_COMMAND:-unknown}"
}

on_exit() {
    local rc=$?
    rm -rf "$work"
    if [[ "$rc" -ne 0 && "$CURRENT_STAGE" != "done" ]]; then
        local detail="Stage '$CURRENT_STAGE' exited with code $rc"
        if [[ -n "$LAST_ERROR_CMD" ]]; then
            detail="$detail (command: $LAST_ERROR_CMD)"
        fi
        echo "Backup failed: $detail" >&2
        send_failure_alert "$CURRENT_STAGE" "$rc" "$detail"
    fi
    exit "$rc"
}
trap on_error ERR
trap on_exit EXIT

CURRENT_STAGE="db_dump"
if [[ "$DB_BACKEND" == "mysql" ]]; then
    log "Dumping MySQL database $DB_NAME"
    mysqldump --single-transaction --routines "$DB_NAME" | gzip > "$work/flog-$stamp.sql.gz"
elif [[ "$DB_BACKEND" == "sqlite" ]]; then
    [[ -n "$DB_PATH" && -f "$DB_PATH" ]] || { echo "BACKUP_DB_PATH is missing for sqlite backend: $DB_PATH" >&2; exit 1; }
    command -v sqlite3 >/dev/null || { echo "sqlite3 is not installed" >&2; exit 1; }
    log "Dumping SQLite database $DB_PATH"
    sqlite3 "$DB_PATH" .dump | gzip > "$work/flog-$stamp.sql.gz"
else
    echo "Unsupported BACKUP_DB_BACKEND: $DB_BACKEND (expected mysql or sqlite)" >&2
    exit 2
fi

CURRENT_STAGE="db_verify"
# An empty or truncated dump must never replace a good backup silently.
gzip -t "$work/flog-$stamp.sql.gz"
[[ $(gzip -dc "$work/flog-$stamp.sql.gz" | head -c 1000 | wc -c) -gt 100 ]] \
    || { echo "database dump looks empty" >&2; exit 1; }
cp -p "$ENV_FILE" "$work/env-$stamp"

CURRENT_STAGE="manifest"
log "Generating checksum manifest"
"$PYTHON_BIN" - "$stamp" "$work/flog-$stamp.sql.gz" "$work/env-$stamp" \
    "$UPLOADS" "$KEEP_DAYS" "$MIN_KEEP" "$DB_BACKEND" "$work/manifest-$stamp.json" <<'PY'
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

stamp, db_p, env_p, uploads_p, keep_days, min_keep, backend, out_p = sys.argv[1:]

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def record(path: Path, rel: str) -> dict:
    return {'path': rel, 'size': path.stat().st_size, 'sha256': digest(path)}

db_path, env_path, uploads_dir = Path(db_p), Path(env_p), Path(uploads_p)
uploads = [
    record(p, p.relative_to(uploads_dir).as_posix())
    for p in sorted(uploads_dir.rglob('*')) if p.is_file()
]
manifest = {
    'version': 1,
    'stamp': stamp,
    'created_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    'db_backend': backend,
    'retention': {'keep_days': int(keep_days), 'min_keep': int(min_keep)},
    'db': record(db_path, f'db/{db_path.name}'),
    'env': record(env_path, f'env/{env_path.name}'),
    'uploads': uploads,
}
Path(out_p).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
PY

CURRENT_STAGE="upload_snapshots"
log "Uploading database dump, .env, and manifest"
if [[ "$STORAGE" == "rclone" ]]; then
    rclone copyto "${dry_run[@]}" "$work/flog-$stamp.sql.gz" "$remote/db/flog-$stamp.sql.gz"
    rclone copyto "${dry_run[@]}" "$work/env-$stamp" "$remote/env/env-$stamp"
    rclone copyto "${dry_run[@]}" "$work/manifest-$stamp.json" "$remote/manifests/manifest-$stamp.json"
else
    if (( is_dry_run )); then
        echo "[dry-run] copy $work/flog-$stamp.sql.gz -> $remote/db/flog-$stamp.sql.gz"
        echo "[dry-run] copy $work/env-$stamp -> $remote/env/env-$stamp"
        echo "[dry-run] copy $work/manifest-$stamp.json -> $remote/manifests/manifest-$stamp.json"
    else
        mkdir -p "$remote/db" "$remote/env" "$remote/manifests" "$remote/uploads" "$remote/uploads-removed"
        cp -p "$work/flog-$stamp.sql.gz" "$remote/db/flog-$stamp.sql.gz"
        cp -p "$work/env-$stamp" "$remote/env/env-$stamp"
        cp -p "$work/manifest-$stamp.json" "$remote/manifests/manifest-$stamp.json"
    fi
fi

CURRENT_STAGE="mirror_uploads"
log "Mirroring uploads"
if [[ "$STORAGE" == "rclone" ]]; then
    rclone sync "${dry_run[@]}" "$UPLOADS" "$remote/uploads" \
        --backup-dir "$remote/uploads-removed/$stamp" --transfers 4 --stats-one-line -v
else
    "$PYTHON_BIN" - "$UPLOADS" "$remote/uploads" "$remote/uploads-removed/$stamp" "$is_dry_run" <<'PY'
import filecmp, shutil, sys
from pathlib import Path

src_root, dst_root, removed_root = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
dry = sys.argv[4] == '1'

src_files = {p.relative_to(src_root).as_posix(): p for p in src_root.rglob('*') if p.is_file()}
dst_files = ({p.relative_to(dst_root).as_posix(): p for p in dst_root.rglob('*') if p.is_file()}
             if dst_root.is_dir() else {})

for rel, src_path in sorted(src_files.items()):
    dst_path = dst_root / rel
    if rel not in dst_files or not filecmp.cmp(src_path, dst_path, shallow=False):
        if dry:
            print(f'[dry-run] sync {rel}')
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

for rel, dst_path in sorted(dst_files.items()):
    if rel not in src_files:
        if dry:
            print(f'[dry-run] archive removed {rel}')
        else:
            archive_path = removed_root / rel
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst_path), str(archive_path))
PY
fi

CURRENT_STAGE="retention"
log "Applying retention policy (keep >= $MIN_KEEP snapshots, prune older than $KEEP_DAYS days)"
compute_deletes() {
    "$PYTHON_BIN" -c '
import re, sys
from datetime import datetime, timedelta, timezone

keep_days, min_keep = int(sys.argv[1]), int(sys.argv[2])
stamp_re = re.compile(r"([0-9]{8}T[0-9]{6}Z)")
cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
items = []
for raw in sys.stdin:
    name = raw.strip().rstrip("/")
    if not name:
        continue
    m = stamp_re.search(name)
    if not m:
        continue
    try:
        ts = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        continue
    items.append((ts, name))
items.sort(key=lambda pair: (pair[0], pair[1]), reverse=True)
for idx, (ts, name) in enumerate(items):
    if idx >= min_keep and ts < cutoff:
        print(name)
' "$KEEP_DAYS" "$MIN_KEEP"
}

for folder in db env manifests; do
    if [[ "$STORAGE" == "rclone" ]]; then
        entries=$(rclone lsf --files-only "$remote/$folder" 2>/dev/null || true)
    else
        entries=$([[ -d "$remote/$folder" ]] && ls -1 "$remote/$folder" || true)
    fi
    while IFS= read -r old; do
        [[ -n "$old" ]] || continue
        if [[ "$STORAGE" == "rclone" ]]; then
            rclone deletefile "${dry_run[@]}" "$remote/$folder/$old"
        elif (( is_dry_run )); then
            echo "[dry-run] delete $remote/$folder/$old"
        else
            rm -f "$remote/$folder/$old"
        fi
    done < <(printf '%s\n' "$entries" | compute_deletes)
done

if [[ "$STORAGE" == "rclone" ]]; then
    removed_entries=$(rclone lsf --dirs-only "$remote/uploads-removed" 2>/dev/null || true)
else
    removed_entries=$([[ -d "$remote/uploads-removed" ]] && ls -1 "$remote/uploads-removed" || true)
fi
while IFS= read -r old; do
    [[ -n "$old" ]] || continue
    if [[ "$STORAGE" == "rclone" ]]; then
        rclone purge "${dry_run[@]}" "$remote/uploads-removed/$old"
    elif (( is_dry_run )); then
        echo "[dry-run] purge $remote/uploads-removed/$old"
    else
        rm -rf "$remote/uploads-removed/$old"
    fi
done < <(printf '%s\n' "$removed_entries" | compute_deletes)

CURRENT_STAGE="done"
log "Done: $remote ($stamp)"
