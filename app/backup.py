"""Backup manifest verification, retention planning, failure alerts, and local drills."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from flask import current_app

from app.email import mail_configured, mail_sender, send_email
from app.site_text import site_text


BACKUP_MANIFEST_VERSION = 1
STAMP_RE = re.compile(r'([0-9]{8}T[0-9]{6}Z)')
DEFAULT_KEEP_DAYS = 30
DEFAULT_MIN_KEEP = 7


@dataclass(frozen=True)
class RetentionPlan:
    keep: list[str]
    delete: list[str]
    ignored: list[str]


@dataclass
class VerificationResult:
    ok: bool
    checked_files: int = 0
    missing: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)


@dataclass
class AlertResult:
    logged: bool = True
    email_sent: bool = False
    webhook_sent: bool = False
    errors: list[str] = field(default_factory=list)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse_backup_stamp(name: str) -> datetime | None:
    """Extract UTC timestamp from a backup filename or directory name."""
    match = STAMP_RE.search(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), '%Y%m%dT%H%M%SZ').replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def plan_retention(
    names: list[str],
    *,
    keep_days: int = DEFAULT_KEEP_DAYS,
    min_keep: int = DEFAULT_MIN_KEEP,
    now: datetime | None = None,
) -> RetentionPlan:
    """Decide which timestamped backups to keep vs delete.

    Always retains at least the newest ``min_keep`` valid snapshots regardless
    of age so a failed schedule or clock issue can never wipe out every backup.
    Older snapshots beyond ``min_keep`` are deleted only when strictly older
    than ``now - timedelta(days=keep_days)``.
    """
    if keep_days < 1:
        raise ValueError('keep_days must be at least 1')
    if min_keep < 1:
        raise ValueError('min_keep must be at least 1')

    reference = now if now is not None else datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    cutoff = reference - timedelta(days=keep_days)

    stamped: list[tuple[datetime, str]] = []
    ignored: list[str] = []
    for raw in names:
        clean = raw.rstrip('/')
        ts = parse_backup_stamp(clean)
        if ts is None:
            ignored.append(clean)
        else:
            stamped.append((ts, clean))

    stamped.sort(key=lambda item: (item[0], item[1]), reverse=True)
    keep: list[str] = []
    delete: list[str] = []
    for index, (ts, name) in enumerate(stamped):
        if index < min_keep or ts >= cutoff:
            keep.append(name)
        else:
            delete.append(name)
    return RetentionPlan(keep=keep, delete=delete, ignored=sorted(ignored))


def _file_record(path: Path, rel_path: str) -> dict[str, Any]:
    return {
        'path': rel_path,
        'size': path.stat().st_size,
        'sha256': sha256_file(path),
    }


def build_backup_manifest(
    *,
    stamp: str,
    db_file: Path,
    env_file: Path,
    uploads_dir: Path,
    keep_days: int = DEFAULT_KEEP_DAYS,
    min_keep: int = DEFAULT_MIN_KEEP,
    db_backend: str = 'mysql',
) -> dict[str, Any]:
    """Build a JSON-serializable checksum manifest for a backup snapshot."""
    upload_entries: list[dict[str, Any]] = []
    if uploads_dir.is_dir():
        for file_path in sorted(p for p in uploads_dir.rglob('*') if p.is_file()):
            rel = file_path.relative_to(uploads_dir).as_posix()
            upload_entries.append(_file_record(file_path, rel))

    return {
        'version': BACKUP_MANIFEST_VERSION,
        'stamp': stamp,
        'created_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'db_backend': db_backend,
        'retention': {
            'keep_days': keep_days,
            'min_keep': min_keep,
        },
        'db': _file_record(db_file, f'db/{db_file.name}'),
        'env': _file_record(env_file, f'env/{env_file.name}'),
        'uploads': upload_entries,
    }


def verify_backup_manifest(
    manifest: dict[str, Any],
    *,
    db_file: Path,
    env_file: Path,
    uploads_dir: Path,
) -> VerificationResult:
    """Verify restored or staged files against a backup manifest's SHA-256 hashes."""
    result = VerificationResult(ok=True)

    def check_entry(label: str, path: Path, expected: dict[str, Any]) -> None:
        if not path.is_file():
            result.missing.append(label)
            return
        result.checked_files += 1
        actual_size = path.stat().st_size
        actual_sha = sha256_file(path)
        if actual_size != expected.get('size') or actual_sha != expected.get('sha256'):
            result.mismatches.append(
                f'{label}: expected sha256={expected.get("sha256")} size={expected.get("size")}, '
                f'got sha256={actual_sha} size={actual_size}'
            )

    check_entry(manifest['db']['path'], db_file, manifest['db'])
    check_entry(manifest['env']['path'], env_file, manifest['env'])

    expected_uploads: set[str] = set()
    for entry in manifest.get('uploads', []):
        rel = entry['path']
        expected_uploads.add(rel)
        check_entry(f'uploads/{rel}', uploads_dir / rel, entry)

    if uploads_dir.is_dir():
        for file_path in sorted(p for p in uploads_dir.rglob('*') if p.is_file()):
            rel = file_path.relative_to(uploads_dir).as_posix()
            if rel not in expected_uploads:
                result.extra.append(f'uploads/{rel}')

    result.ok = not (result.missing or result.mismatches or result.extra)
    return result


def _valid_webhook_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url.strip())
    if parsed.scheme in ('http', 'https') and parsed.netloc:
        return url.strip()
    return None


def notify_backup_failure(
    *,
    stage: str,
    exit_code: int,
    detail: str,
    stamp: str | None = None,
    target: str | None = None,
    webhook_url: str | None = None,
) -> AlertResult:
    """Emit structured log + email (reusing Flog mail) + optional webhook alert."""
    result = AlertResult(logged=True)
    occurred_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        'event': 'backup_failure',
        'occurred_at': occurred_at,
        'stage': stage,
        'exit_code': exit_code,
        'stamp': stamp or 'unknown',
        'target': target or 'unspecified',
        'detail': detail,
    }
    current_app.logger.error(
        'Backup failure alert: stage=%s exit_code=%s stamp=%s target=%s detail=%s',
        stage, exit_code, payload['stamp'], payload['target'], detail,
    )

    recipients = list(current_app.config.get('ADMINS') or [])
    if mail_configured() and recipients:
        try:
            name = site_text()['site_name']
        except Exception:
            name = 'Flog'
        subject = f'[{name}] 备份失败告警：{stage}'
        text_body = (
            f'Flog 备份执行失败，请及时排查。\n\n'
            f'时间（UTC）：{occurred_at}\n'
            f'阶段：{stage}\n'
            f'退出码：{exit_code}\n'
            f'批次：{payload["stamp"]}\n'
            f'目标：{payload["target"]}\n'
            f'详情：{detail}\n'
        )
        html_body = (
            f'<p>Flog 备份执行失败，请及时排查。</p>'
            f'<ul>'
            f'<li><strong>时间（UTC）</strong>：{occurred_at}</li>'
            f'<li><strong>阶段</strong>：{stage}</li>'
            f'<li><strong>退出码</strong>：{exit_code}</li>'
            f'<li><strong>批次</strong>：{payload["stamp"]}</li>'
            f'<li><strong>目标</strong>：{payload["target"]}</li>'
            f'<li><strong>详情</strong>：{detail}</li>'
            f'</ul>'
        )
        try:
            send_email(
                subject=subject,
                sender=(name, mail_sender()),
                recipients=recipients,
                text_body=text_body,
                html_body=html_body,
                sync=True,
            )
            result.email_sent = True
        except Exception as exc:
            current_app.logger.exception('Failed to dispatch backup failure email')
            result.errors.append(f'email: {exc}')

    configured_webhook = _valid_webhook_url(
        webhook_url if webhook_url is not None
        else current_app.config.get('BACKUP_ALERT_WEBHOOK')
    )
    if configured_webhook:
        req = urllib.request.Request(
            configured_webhook,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                status = getattr(resp, 'status', 200)
                if 200 <= status < 300:
                    result.webhook_sent = True
                else:
                    result.errors.append(f'webhook: HTTP {status}')
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            current_app.logger.warning('Failed to dispatch backup webhook: %s', exc)
            result.errors.append(f'webhook: {exc}')

    return result
