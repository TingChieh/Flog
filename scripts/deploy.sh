#!/usr/bin/env bash
# Deploy the public repository's main to the production server.
#
# Usage: ./scripts/deploy.sh [--dry-run] [--no-optimize] [--recompress]
#   --dry-run      check everything and show what would change; touch nothing
#   --no-optimize  skip `flask images optimize` (back-filling older uploads)
#   --recompress   pass --recompress to it (shrinks stored files in place)
#
# What gets deployed is exactly origin/main of the public repository. The
# server cannot reach github.com, so the commits travel as a git bundle over
# SSH and are applied to the server checkout as `origin/main`, then
# fast-forwarded: the server's repository always follows the public one.
#
# Order: preflight -> backup (database dump, uploads, .env) -> code -> Python
# dependencies -> ffmpeg -> database migration -> restart -> optimize -> smoke
# test. Nothing is changed before the backup. Caddy is not touched.
#
# Settings (environment): DEPLOY_HOST, DEPLOY_DIR, DEPLOY_USER, DEPLOY_SERVICE,
# DEPLOY_BACKUPS, DEPLOY_LOCAL_URL (checked on the server), DEPLOY_SITE.
set -euo pipefail

HOST=${DEPLOY_HOST:-hk_server}
DIR=${DEPLOY_DIR:-/home/ubuntu/flog}
APP_USER=${DEPLOY_USER:-ubuntu}
SERVICE=${DEPLOY_SERVICE:-flog}
BACKUPS=${DEPLOY_BACKUPS:-/root/flog-backups}
LOCAL_URL=${DEPLOY_LOCAL_URL:-http://127.0.0.1:8001}
SITE=${DEPLOY_SITE:-https://blog.aisaka.cc}
SOCKET="/tmp/flog-deploy-%C"

dry_run=0 optimize=1 recompress=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=1 ;;
        --no-optimize) optimize=0 ;;
        --recompress) recompress="--recompress" ;;
        -h|--help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/.."

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mxx>\033[0m %s\n' "$*" >&2; exit 1; }

# One multiplexed SSH connection; the server sometimes drops a fresh handshake,
# so opening it is retried and everything after that reuses it.
ssh_opts=(-o BatchMode=yes -o ConnectTimeout=15 -o ControlPath="$SOCKET")
open_connection() {
    for attempt in 1 2 3 4 5; do
        if ssh "${ssh_opts[@]}" -o ControlMaster=yes -o ControlPersist=600 -fN "$HOST" 2>/dev/null; then
            return 0
        fi
        sleep 3
    done
    die "cannot connect to $HOST"
}
remote() { ssh "${ssh_opts[@]}" "$HOST" "$@"; }
close_connection() { ssh "${ssh_opts[@]}" -O exit "$HOST" >/dev/null 2>&1 || true; }
trap close_connection EXIT

as_app() {   # run a command as the app user inside the checkout
    printf 'cd %q && sudo -u %q -H bash -c %q' "$DIR" "$APP_USER" "$1"
}

# ---------------------------------------------------------------- preflight
log "Checking the public repository"
git fetch origin --quiet
target=$(git rev-parse origin/main)
short=${target:0:7}
if [[ "$(git rev-parse HEAD)" != "$target" ]]; then
    echo "   note: local HEAD ($(git rev-parse --short HEAD)) differs from origin/main ($short); deploying origin/main"
fi

open_connection
log "Checking $HOST"
current=$(remote "$(as_app 'git rev-parse HEAD')")
dirty=$(remote "$(as_app 'git status --porcelain --untracked-files=no')")
[[ -z "$dirty" ]] || die "the server checkout has local changes:\n$dirty"
git cat-file -e "$current^{commit}" 2>/dev/null \
    || die "server is at $current, which is not in this repository"
git merge-base --is-ancestor "$current" "$target" \
    || die "server ($current) is not an ancestor of origin/main ($target); resolve by hand"
db_before=$(remote "$(as_app '.venv314/bin/flask db current 2>/dev/null | grep -oE "^[0-9a-f]{12}" | head -1')" || true)

echo "   server: ${current:0:7}   ->   origin/main: $short   (database revision: ${db_before:-none})"
git log --oneline "$current..$target" | sed 's/^/   /'
if (( dry_run )); then
    log "Dry run: nothing changed"
    exit 0
fi

# ------------------------------------------------------------------- backup
stamp=$(date +%Y%m%d-%H%M)
backup="$BACKUPS/$stamp-before-$short"
log "Backing up to $backup"
remote "set -euo pipefail
mkdir -p '$backup' && chmod 700 '$backup'
mysqldump --single-transaction --routines flog | gzip > '$backup/flog_full.sql.gz'
tar -C '$DIR/instance' -czf '$backup/uploads.tar.gz' uploads
cp -p '$DIR/.env' '$backup/env'
ls -la '$backup'"

# --------------------------------------------------------------------- code
if [[ "$current" != "$target" ]]; then
    log "Sending commits"
    bundle=$(mktemp -t flog-deploy.XXXXXX)
    trap 'rm -f "$bundle"; close_connection' EXIT
    git bundle create "$bundle" refs/remotes/origin/main "^$current" 2>/dev/null
    scp -q -o ControlPath="$SOCKET" "$bundle" "$HOST:/tmp/flog-deploy.bundle"
    remote "chmod 644 /tmp/flog-deploy.bundle && $(as_app "git fetch -q /tmp/flog-deploy.bundle refs/remotes/origin/main:refs/remotes/origin/main && test \"\$(git rev-parse origin/main)\" = '$target' && git merge -q --ff-only origin/main && git log --oneline -1") && rm -f /tmp/flog-deploy.bundle"
else
    log "Server already has $short"
fi

# ------------------------------------------------------------- dependencies
log "Installing Python dependencies"
remote "$(as_app '"$HOME/.local/bin/uv" pip install --python .venv314/bin/python -q -r requirements.txt')"

log "Checking ffmpeg (Live Photo clips)"
remote "set -e
if ! command -v ffmpeg >/dev/null; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends ffmpeg >/dev/null
fi
ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264 || { echo 'ffmpeg has no libx264' >&2; exit 1; }
ffmpeg -version | head -1"

# ---------------------------------------------------------------- migration
log "Migrating the database"
remote "$(as_app 'set -o pipefail; .venv314/bin/flask db upgrade 2>&1 | tail -5')"
db_after=$(remote "$(as_app '.venv314/bin/flask db current 2>/dev/null | grep -oE "^[0-9a-f]{12}" | head -1')")
echo "   database revision: ${db_before:-none} -> $db_after"

# ------------------------------------------------------------------ restart
rollback_hint() {
    cat >&2 <<EOF

To roll back:
  ssh $HOST "cd $DIR && sudo -u $APP_USER git reset --hard ${current:0:7} && sudo -u $APP_USER .venv314/bin/flask db downgrade ${db_before:-base} && systemctl restart $SERVICE"
Full backup: $backup (database dump, uploads, .env)
EOF
}
log "Restarting $SERVICE"
restarted_at=$(remote "date '+%Y-%m-%d %H:%M:%S'")
remote "systemctl restart $SERVICE"
for attempt in $(seq 1 30); do
    code=$(remote "curl -s -o /dev/null -w '%{http_code}' -m 5 $LOCAL_URL/ || true")
    [[ "$code" == 200 ]] && break
    sleep 1
done
[[ "$code" == 200 ]] || { remote "journalctl -u $SERVICE -n 30 --no-pager" >&2 || true; rollback_hint; die "$SERVICE did not come back (HTTP $code)"; }

# ----------------------------------------------------------------- optimize
if (( optimize )); then
    log "Back-filling older uploads"
    remote "$(as_app "set -o pipefail; .venv314/bin/flask images optimize $recompress 2>&1 | tail -3")"
fi

# --------------------------------------------------------------- smoke test
log "Smoke test"
fail=0
check() { # description, expected, actual
    if [[ "$3" == *"$2"* ]]; then echo "   ok    $1"; else echo "   FAIL  $1 (got: $3)"; fail=1; fi
}
check "home page via $SITE" 200 "$(curl -s -o /dev/null -w '%{http_code}' -m 20 "$SITE/")"
sample=$(remote "ls '$DIR/instance/uploads' | grep -E '^[0-9a-f]{32}\\.(jpg|png)\$' | head -1" || true)
if [[ -n "$sample" ]]; then
    headers=$(curl -sI -m 20 "$SITE/files/$sample")
    check "uploaded image is served" "200" "$(head -1 <<<"$headers")"
    check "uploaded image is cached for a year" "immutable" "$headers"
fi
errors=$(remote "journalctl -u $SERVICE --since '$restarted_at' --no-pager | grep -c -E 'Traceback|ERROR' || true")
if [[ "$errors" == 0 ]]; then echo "   ok    no errors logged since the restart"; else echo "   FAIL  $errors error lines logged since the restart"; fail=1; fi

(( fail == 0 )) || { rollback_hint; die "smoke test failed"; }
log "Deployed $short"
rollback_hint
