#!/usr/bin/env bash
# Set up a Python 3.14 development environment and start Flog.
#
# Usage: ./scripts/bootstrap.sh [--upgrade] [--no-run] [--prod]
#   --upgrade  re-resolve requirements.in to the latest versions first
#   --no-run   set everything up but do not start the server
#   --prod     install runtime dependencies only (no pytest)
set -euo pipefail

PYTHON_VERSION=3.14
VENV=.venv

cd "$(dirname "$0")/.."

upgrade=0
run=1
reqs=requirements-dev.txt
for arg in "$@"; do
    case "$arg" in
        --upgrade) upgrade=1 ;;
        --no-run) run=0 ;;
        --prod) reqs=requirements.txt ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

if command -v uv >/dev/null 2>&1; then
    use_uv=1
else
    use_uv=0
    python_bin=$(command -v "python$PYTHON_VERSION" || true)
    if [[ -z "$python_bin" ]]; then
        echo "Python $PYTHON_VERSION not found. Install uv or python$PYTHON_VERSION." >&2
        exit 1
    fi
fi

# Recreate the virtualenv when it is missing or built on another version.
current=""
if [[ -x "$VENV/bin/python" ]]; then
    current=$("$VENV/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
fi
if [[ "$current" != "$PYTHON_VERSION" ]]; then
    log "Creating $VENV with Python $PYTHON_VERSION${current:+ (replacing $current)}"
    rm -rf "$VENV"
    if (( use_uv )); then
        uv venv --python "$PYTHON_VERSION" "$VENV"
    else
        "$python_bin" -m venv "$VENV"
    fi
fi

if (( upgrade )); then
    if (( ! use_uv )); then
        echo "--upgrade requires uv (https://docs.astral.sh/uv/)." >&2
        exit 1
    fi
    log "Resolving latest versions into requirements.txt"
    uv pip compile requirements.in --python-version "$PYTHON_VERSION" \
        --upgrade --no-header --no-annotate -o requirements.txt
fi

log "Installing $reqs"
if (( use_uv )); then
    uv pip install --python "$VENV/bin/python" -r "$reqs"
else
    "$VENV/bin/python" -m pip install --upgrade pip
    "$VENV/bin/python" -m pip install -r "$reqs"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
export FLASK_APP=flog.py

if [[ ! -f .env ]]; then
    log "Creating .env from .env.example"
    cp .env.example .env
    secret=$(python -c 'import secrets; print(secrets.token_hex(32))')
    # The example DATABASE_URL is a placeholder; fall back to local SQLite.
    sed -i.bak -e "s/^SECRET_KEY=.*/SECRET_KEY=$secret/" \
        -e 's/^DATABASE_URL=/# DATABASE_URL=/' .env && rm -f .env.bak
fi

log "Compiling translations"
flask translate compile

log "Applying database migrations"
flask db upgrade

if (( run )); then
    log "Starting development server on http://127.0.0.1:5000"
    exec flask run
fi
log "Done. Activate with: source $VENV/bin/activate"
