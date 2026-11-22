#!/usr/bin/env bash
# Restore and verify a Flog backup from Cloudflare R2 (or an isolated local
# mirror) into an explicit target directory. Never overwrites live production
# databases or upload folders automatically.
#
# Historical snapshots (--stamp <stamp>) are reconstructed strictly from the
# selected manifest: files still matching the live uploads/ mirror are fetched
# from uploads/, while files later overwritten or removed are recovered from
# uploads-removed/<later_stamp>/ in chronological order.
#
# Usage:
#   scripts/restore_r2.sh --target-dir <dir> [--stamp <YYYYMMDDTHHMMSSZ>] [--dry-run] [--skip-db-import]
#
# Options:
#   --target-dir <dir>  Required isolated destination directory for restored files.
#   --stamp <stamp>     Specific snapshot stamp (defaults to the latest manifest).
#   --dry-run           Check remote/local manifest availability; write nothing.
#   --skip-db-import    Only decompress & verify the SQL dump; do not load sqlite3.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
settings=${FLOG_BACKUP_ENV:-$root/.env.backup}
if [[ -f "$settings" ]]; then
    while IFS='=' read -r key value; do
        if [[ -z "${!key:-}" ]]; then export "$key=${value//[\"\']/}"; fi
    done < <(grep -E '^(R2|BACKUP)_[A-Z_]+=' "$settings")
fi

TARGET_DIR=""
REQ_STAMP=""
DRY_RUN=0
SKIP_DB_IMPORT=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --target-dir) TARGET_DIR="${2:-}"; shift 2 ;;
        --stamp) REQ_STAMP="${2:-}"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --skip-db-import) SKIP_DB_IMPORT=1; shift ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

[[ -n "$TARGET_DIR" ]] || { echo "--target-dir is required (refusing to restore into live paths)" >&2; exit 2; }

STORAGE=${BACKUP_STORAGE:-rclone}
BUCKET=${R2_BUCKET:?set R2_BUCKET in $settings}
PREFIX=${BACKUP_PREFIX:-flog}
PYTHON_BIN=${BACKUP_PYTHON:-}
if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "$root/.venv/bin/python" ]]; then
        PYTHON_BIN="$root/.venv/bin/python"
    else
        PYTHON_BIN=$(command -v python3 || true)
    fi
fi
[[ -n "$PYTHON_BIN" ]] || { echo "python3 is required for checksum verification" >&2; exit 1; }

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

if [[ -n "$REQ_STAMP" ]]; then
    [[ "$REQ_STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || { echo "Invalid --stamp format: $REQ_STAMP" >&2; exit 2; }
    stamp="$REQ_STAMP"
else
    if [[ "$STORAGE" == "rclone" ]]; then
        manifests=$(rclone lsf --files-only "$remote/manifests" 2>/dev/null || true)
    else
        manifests=$([[ -d "$remote/manifests" ]] && ls -1 "$remote/manifests" || true)
    fi
    stamp=$(printf '%s\n' "$manifests" | sed -nE 's/^manifest-([0-9]{8}T[0-9]{6}Z)\.json$/\1/p' | sort | tail -n 1)
    [[ -n "$stamp" ]] || { echo "No backup manifest found under $remote/manifests" >&2; exit 1; }
fi

log "Selected backup snapshot: $stamp from $remote"
if (( DRY_RUN )); then
    log "[dry-run] Would restore db/flog-$stamp.sql.gz, env/env-$stamp, uploads/ into $TARGET_DIR"
    exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
chmod 700 "$work"
mkdir -p "$work/uploads" "$work/probe"

log "Fetching snapshot metadata, database dump, and .env"
if [[ "$STORAGE" == "rclone" ]]; then
    rclone copyto "$remote/manifests/manifest-$stamp.json" "$work/manifest-$stamp.json"
    rclone copyto "$remote/db/flog-$stamp.sql.gz" "$work/flog-$stamp.sql.gz"
    rclone copyto "$remote/env/env-$stamp" "$work/env-$stamp"
    removed_stamps=$(rclone lsf --dirs-only "$remote/uploads-removed" 2>/dev/null || true)
else
    [[ -f "$remote/manifests/manifest-$stamp.json" ]] || { echo "Missing manifest-$stamp.json" >&2; exit 1; }
    [[ -f "$remote/db/flog-$stamp.sql.gz" ]] || { echo "Missing flog-$stamp.sql.gz" >&2; exit 1; }
    [[ -f "$remote/env/env-$stamp" ]] || { echo "Missing env-$stamp" >&2; exit 1; }
    cp -p "$remote/manifests/manifest-$stamp.json" "$work/manifest-$stamp.json"
    cp -p "$remote/db/flog-$stamp.sql.gz" "$work/flog-$stamp.sql.gz"
    cp -p "$remote/env/env-$stamp" "$work/env-$stamp"
    removed_stamps=$([[ -d "$remote/uploads-removed" ]] && ls -1 "$remote/uploads-removed" || true)
fi

log "Reconstructing uploads for snapshot $stamp"
"$PYTHON_BIN" - "$STORAGE" "$remote" "$stamp" "$work/manifest-$stamp.json" \
    "$work/uploads" "$work/probe" "$removed_stamps" <<'PY'
import hashlib, json, re, shutil, subprocess, sys
from pathlib import Path

storage, remote, stamp, manifest_p, out_uploads_p, probe_p, raw_removed = sys.argv[1:]
manifest = json.loads(Path(manifest_p).read_text(encoding='utf-8'))
out_uploads = Path(out_uploads_p)
probe_dir = Path(probe_p)

stamp_re = re.compile(r'^[0-9]{8}T[0-9]{6}Z$')
later_stamps = sorted(
    s.strip().rstrip('/')
    for s in raw_removed.splitlines()
    if stamp_re.match(s.strip().rstrip('/')) and s.strip().rstrip('/') > stamp
)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def matches(path: Path, expected: dict) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == expected.get('size')
        and sha256(path) == expected.get('sha256')
    )

def fetch_candidate(rel_remote: str, dest: Path) -> bool:
    if storage == 'local':
        src = Path(remote) / rel_remote
        if not src.is_file():
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ['rclone', 'copyto', f'{remote}/{rel_remote}', str(dest)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0 and dest.is_file()

for idx, entry in enumerate(manifest.get('uploads', [])):
    rel = entry['path']
    # Guard against unsafe paths inside a crafted manifest.
    target = (out_uploads / rel).resolve()
    if not target.is_relative_to(out_uploads.resolve()):
        print(f'ERROR: unsafe upload path in manifest: {rel}', file=sys.stderr)
        sys.exit(1)

    # Try historical archives created right after `stamp` first only if live copy differs,
    # keeping normal latest-snapshot restores fast with a single fetch per file.
    live_probe = probe_dir / f'live-{idx}'
    fallback_mismatch = None
    if fetch_candidate(f'uploads/{rel}', live_probe):
        if matches(live_probe, entry):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(live_probe), str(target))
            continue
        fallback_mismatch = live_probe

    recovered = False
    for later in later_stamps:
        hist_probe = probe_dir / f'hist-{idx}-{later}'
        if fetch_candidate(f'uploads-removed/{later}/{rel}', hist_probe):
            if matches(hist_probe, entry):
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(hist_probe), str(target))
                recovered = True
                break
            hist_probe.unlink(missing_ok=True)
    if recovered:
        if fallback_mismatch is not None:
            fallback_mismatch.unlink(missing_ok=True)
        continue

    # No matching historical copy existed: place the mismatched live copy (if any)
    # so the manifest verifier reports the exact checksum mismatch.
    if fallback_mismatch is not None and fallback_mismatch.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(fallback_mismatch), str(target))
PY

log "Verifying gzip integrity and SHA-256 manifest checksums"
gzip -t "$work/flog-$stamp.sql.gz"
db_backend=$("$PYTHON_BIN" - "$work/manifest-$stamp.json" "$work/flog-$stamp.sql.gz" "$work/env-$stamp" "$work/uploads" <<'PY'
import hashlib, json, sys
from pathlib import Path

manifest_path, db_path, env_path, uploads_dir = map(Path, sys.argv[1:])
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

errors = []
checked = 0

def verify(label: str, path: Path, expected: dict) -> None:
    global checked
    if not path.is_file():
        errors.append(f'missing: {label}')
        return
    checked += 1
    size = path.stat().st_size
    digest = sha256(path)
    if size != expected.get('size') or digest != expected.get('sha256'):
        errors.append(
            f'checksum mismatch on {label}: expected {expected.get("sha256")} ({expected.get("size")}B), '
            f'got {digest} ({size}B)'
        )

verify(manifest['db']['path'], db_path, manifest['db'])
verify(manifest['env']['path'], env_path, manifest['env'])

expected_uploads = set()
for entry in manifest.get('uploads', []):
    rel = entry['path']
    expected_uploads.add(rel)
    verify(f'uploads/{rel}', uploads_dir / rel, entry)

for path in sorted(uploads_dir.rglob('*')):
    if path.is_file():
        rel = path.relative_to(uploads_dir).as_posix()
        if rel not in expected_uploads:
            errors.append(f'unexpected extra file in uploads: {rel}')

if errors:
    for err in errors:
        print(f'ERROR: {err}', file=sys.stderr)
    sys.exit(1)

print(f'Verified {checked} file(s) against manifest {manifest["stamp"]}', file=sys.stderr)
print(manifest.get('db_backend', 'mysql'))
PY
)

log "Writing verified snapshot into $TARGET_DIR"
mkdir -p "$TARGET_DIR/db" "$TARGET_DIR/env" "$TARGET_DIR/uploads"
cp -p "$work/manifest-$stamp.json" "$TARGET_DIR/manifest.json"
cp -p "$work/flog-$stamp.sql.gz" "$TARGET_DIR/db/flog-$stamp.sql.gz"
gzip -dc "$work/flog-$stamp.sql.gz" > "$TARGET_DIR/db/flog-$stamp.sql"
cp -p "$work/env-$stamp" "$TARGET_DIR/env/.env"
chmod 600 "$TARGET_DIR/env/.env"
cp -a "$work/uploads/." "$TARGET_DIR/uploads/"

if [[ "$db_backend" == "sqlite" && "$SKIP_DB_IMPORT" == "0" ]]; then
    command -v sqlite3 >/dev/null || { echo "sqlite3 is required to restore sqlite snapshot" >&2; exit 1; }
    rm -f "$TARGET_DIR/db/restored.sqlite3"
    sqlite3 "$TARGET_DIR/db/restored.sqlite3" < "$TARGET_DIR/db/flog-$stamp.sql"
    integrity=$(sqlite3 "$TARGET_DIR/db/restored.sqlite3" "PRAGMA integrity_check;")
    [[ "$integrity" == "ok" ]] || { echo "SQLite integrity_check failed: $integrity" >&2; exit 1; }
    log "Restored and verified SQLite database: $TARGET_DIR/db/restored.sqlite3"
elif [[ "$db_backend" == "mysql" ]]; then
    log "Verified MySQL dump unpacked to $TARGET_DIR/db/flog-$stamp.sql"
    log "Manual import (only into an intended target DB): mysql <target_db> < $TARGET_DIR/db/flog-$stamp.sql"
fi

log "Restore verification completed: $TARGET_DIR ($stamp)"
