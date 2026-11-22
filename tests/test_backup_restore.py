"""Tests for backup retention, manifest checksum verification, alerting, and isolated drills."""
import gzip
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import backup as backup_mod
from app.backup import (
    build_backup_manifest,
    notify_backup_failure,
    plan_retention,
    sha256_file,
    verify_backup_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = REPO_ROOT / 'scripts' / 'backup_r2.sh'
RESTORE_SCRIPT = REPO_ROOT / 'scripts' / 'restore_r2.sh'


def test_retention_policy_keeps_min_keep_even_when_all_expired():
    now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    names = [
        'flog-20250101T033000Z.sql.gz',
        'flog-20250201T033000Z.sql.gz',
        'flog-20250301T033000Z.sql.gz',
        'notes.txt',
    ]
    plan = plan_retention(names, keep_days=30, min_keep=5, now=now)
    assert plan.keep == [
        'flog-20250301T033000Z.sql.gz',
        'flog-20250201T033000Z.sql.gz',
        'flog-20250101T033000Z.sql.gz',
    ]
    assert plan.delete == []
    assert plan.ignored == ['notes.txt']


def test_retention_policy_prunes_expired_beyond_min_keep():
    now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    names = [
        'flog-20261122T033000Z.sql.gz',  # fresh (0d) -> keep
        'flog-20261110T033000Z.sql.gz',  # fresh (12d) -> keep
        'flog-20261023T120000Z.sql.gz',  # exact 30d boundary -> keep
        'flog-20261020T033000Z.sql.gz',  # expired (33d) -> delete (idx 3 >= min_keep 2)
        'flog-20260901T033000Z.sql.gz',  # expired (82d) -> delete
    ]
    plan = plan_retention(names, keep_days=30, min_keep=2, now=now)
    assert plan.keep == [
        'flog-20261122T033000Z.sql.gz',
        'flog-20261110T033000Z.sql.gz',
        'flog-20261023T120000Z.sql.gz',
    ]
    assert plan.delete == [
        'flog-20261020T033000Z.sql.gz',
        'flog-20260901T033000Z.sql.gz',
    ]


def test_retention_policy_rejects_non_positive_limits():
    with pytest.raises(ValueError):
        plan_retention([], keep_days=0)
    with pytest.raises(ValueError):
        plan_retention([], min_keep=0)


def test_manifest_build_and_verify_detects_tampering_missing_and_extra(tmp_path):
    db_file = tmp_path / 'flog-20261122T033000Z.sql.gz'
    env_file = tmp_path / 'env-20261122T033000Z'
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    db_file.write_bytes(gzip.compress(b'CREATE TABLE t(id INT); INSERT INTO t VALUES(1);'))
    env_file.write_text('SECRET_KEY=dummy\n', encoding='utf-8')
    (uploads / 'img.png').write_bytes(b'png-bytes')
    (uploads / 'audio').mkdir()
    (uploads / 'audio' / 'ep1.mp3').write_bytes(b'mp3-bytes')

    manifest = build_backup_manifest(
        stamp='20261122T033000Z',
        db_file=db_file,
        env_file=env_file,
        uploads_dir=uploads,
        keep_days=30,
        min_keep=7,
        db_backend='sqlite',
    )
    ok_res = verify_backup_manifest(
        manifest, db_file=db_file, env_file=env_file, uploads_dir=uploads)
    assert ok_res.ok is True
    assert ok_res.checked_files == 4

    # Tamper upload file -> mismatch detected.
    (uploads / 'img.png').write_bytes(b'corrupted')
    bad = verify_backup_manifest(
        manifest, db_file=db_file, env_file=env_file, uploads_dir=uploads)
    assert bad.ok is False
    assert any('uploads/img.png' in msg for msg in bad.mismatches)

    # Restore file, delete audio, add unexpected extra file -> missing & extra detected.
    (uploads / 'img.png').write_bytes(b'png-bytes')
    (uploads / 'audio' / 'ep1.mp3').unlink()
    (uploads / 'stray.txt').write_text('stray', encoding='utf-8')
    diff = verify_backup_manifest(
        manifest, db_file=db_file, env_file=env_file, uploads_dir=uploads)
    assert diff.ok is False
    assert diff.missing == ['uploads/audio/ep1.mp3']
    assert diff.extra == ['uploads/stray.txt']


def test_notify_backup_failure_dispatches_email_and_mock_webhook(
    application, outbox, monkeypatch, caplog
):
    sent_requests: list[tuple[str, dict]] = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=5):
        sent_requests.append((req.full_url, json.loads(req.data.decode('utf-8'))))
        return FakeResponse()

    monkeypatch.setattr(backup_mod.urllib.request, 'urlopen', fake_urlopen)
    monkeypatch.setitem(
        application.config, 'BACKUP_ALERT_WEBHOOK', 'https://alerts.example.test/hook')

    with application.app_context(), caplog.at_level('ERROR'):
        outcome = notify_backup_failure(
            stage='db_dump',
            exit_code=1,
            detail='mysqldump failed with exit 1',
            stamp='20261122T033000Z',
            target='local:drill/flog',
        )

    assert outcome.logged is True
    assert outcome.email_sent is True
    assert outcome.webhook_sent is True
    assert outcome.errors == []
    assert len(outbox) == 1
    assert '备份失败告警：db_dump' in outbox[0].subject
    assert 'mysqldump failed' in outbox[0].body
    assert len(sent_requests) == 1
    assert sent_requests[0][0] == 'https://alerts.example.test/hook'
    assert sent_requests[0][1]['event'] == 'backup_failure'
    assert sent_requests[0][1]['stage'] == 'db_dump'
    assert 'Backup failure alert' in caplog.text


def test_cli_backup_alert_command(application, outbox):
    runner = application.test_cli_runner()
    res = runner.invoke(args=[
        'backup', 'alert',
        '--stage', 'upload_snapshots',
        '--exit-code', '2',
        '--detail', 'simulated rclone timeout',
        '--stamp', '20261122T033000Z',
        '--target', 'R2:nonprod-bucket/flog',
    ])
    assert res.exit_code == 0, res.output
    assert 'email_sent=True' in res.output
    assert len(outbox) == 1


def _create_fixture_sqlite_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE category (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
            CREATE TABLE post (id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL);
            INSERT INTO category (id, name) VALUES (1, '工程'), (2, '随笔');
            INSERT INTO post (id, title, body) VALUES
                (1, '演练文章一', '包含中文与 ![pic](/files/sample.png) 的正文内容，用于校验备份恢复完整性。'),
                (2, '演练文章二', '第二篇演练文章，确保多行数据完整恢复且 SHA-256 校验通过。');
            """
        )
        conn.commit()
    finally:
        conn.close()


def _base_drill_env(tmp_path: Path, db_path: Path, env_file: Path, uploads: Path,
                    local_r2: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        'BACKUP_STORAGE': 'local',
        'BACKUP_DB_BACKEND': 'sqlite',
        'BACKUP_LOCAL_ROOT': str(local_r2),
        'R2_BUCKET': 'flog-drill-bucket',
        'BACKUP_PREFIX': 'nonprod-drill',
        'BACKUP_DB_PATH': str(db_path),
        'BACKUP_UPLOADS': str(uploads),
        'BACKUP_ENV_FILE': str(env_file),
        'BACKUP_KEEP_DAYS': '30',
        'BACKUP_MIN_KEEP': '2',
        'BACKUP_ALERT_DISABLE': '1',
    })
    return env


def test_isolated_local_backup_and_restore_drill_end_to_end(tmp_path):
    db_path = tmp_path / 'source.sqlite3'
    _create_fixture_sqlite_db(db_path)
    env_file = tmp_path / 'source.env'
    env_file.write_text('SECRET_KEY=drill-secret-key\nDISPLAY_TIMEZONE=Asia/Shanghai\n',
                        encoding='utf-8')
    uploads = tmp_path / 'uploads'
    (uploads / 'audio').mkdir(parents=True)
    (uploads / 'photo.png').write_bytes(b'\x89PNG\r\n\x1a\nfake-png-content-12345')
    (uploads / 'audio' / 'ep.mp3').write_bytes(b'ID3fake-mp3-audio-payload')
    local_r2 = tmp_path / 'r2-mock'
    restore_dir = tmp_path / 'restored'

    env = _base_drill_env(tmp_path, db_path, env_file, uploads, local_r2)

    # 1) --dry-run must write nothing into the mock bucket.
    dry = subprocess.run(
        [str(BACKUP_SCRIPT), '--dry-run'],
        env=env, capture_output=True, text=True, check=True,
    )
    assert '[dry-run]' in dry.stdout
    assert not (local_r2 / 'flog-drill-bucket').exists()

    # 2) Seed expired snapshots to verify retention keeps BACKUP_MIN_KEEP and prunes older ones.
    prefix_dir = local_r2 / 'flog-drill-bucket' / 'nonprod-drill'
    for folder, template in (
        ('db', 'flog-{s}.sql.gz'),
        ('env', 'env-{s}'),
        ('manifests', 'manifest-{s}.json'),
    ):
        (prefix_dir / folder).mkdir(parents=True, exist_ok=True)
        for old_stamp in ('20250101T000000Z', '20250102T000000Z', '20250103T000000Z'):
            (prefix_dir / folder / template.format(s=old_stamp)).write_text('old', encoding='utf-8')
    (prefix_dir / 'uploads-removed' / '20250101T000000Z').mkdir(parents=True, exist_ok=True)
    (prefix_dir / 'uploads-removed' / '20250102T000000Z').mkdir(parents=True, exist_ok=True)
    (prefix_dir / 'uploads-removed' / '20250103T000000Z').mkdir(parents=True, exist_ok=True)

    # 3) Run real backup into isolated local mock bucket.
    run = subprocess.run(
        [str(BACKUP_SCRIPT)],
        env=env, capture_output=True, text=True, check=True,
    )
    assert 'Done:' in run.stdout
    # New snapshot + 1 newest old snapshot = BACKUP_MIN_KEEP (2); older 2 pruned.
    remaining_manifests = sorted(p.name for p in (prefix_dir / 'manifests').iterdir())
    assert len(remaining_manifests) == 2
    assert 'manifest-20250103T000000Z.json' in remaining_manifests
    assert 'manifest-20250101T000000Z.json' not in remaining_manifests
    assert not (prefix_dir / 'uploads-removed' / '20250101T000000Z').exists()

    # 4) Run restore_r2.sh into isolated restore_dir and verify content & SHA-256 parity.
    restored = subprocess.run(
        [str(RESTORE_SCRIPT), '--target-dir', str(restore_dir)],
        env=env, capture_output=True, text=True, check=True,
    )
    assert 'Restore verification completed' in restored.stdout
    assert sha256_file(restore_dir / 'env' / '.env') == sha256_file(env_file)
    assert sha256_file(restore_dir / 'uploads' / 'photo.png') == sha256_file(uploads / 'photo.png')
    assert sha256_file(restore_dir / 'uploads' / 'audio' / 'ep.mp3') == sha256_file(
        uploads / 'audio' / 'ep.mp3')

    restored_conn = sqlite3.connect(restore_dir / 'db' / 'restored.sqlite3')
    try:
        rows = restored_conn.execute('SELECT id, title, body FROM post ORDER BY id').fetchall()
        assert len(rows) == 2
        assert rows[0][1] == '演练文章一'
        assert rows[1][1] == '演练文章二'
    finally:
        restored_conn.close()

    # 5) Tampering a backed-up upload file must fail checksum verification on restore.
    (prefix_dir / 'uploads' / 'photo.png').write_bytes(b'TAMPERED')
    tampered_target = tmp_path / 'restored-tampered'
    failed_restore = subprocess.run(
        [str(RESTORE_SCRIPT), '--target-dir', str(tampered_target)],
        env=env, capture_output=True, text=True,
    )
    assert failed_restore.returncode != 0
    assert 'checksum mismatch' in failed_restore.stderr
    assert not tampered_target.exists()


def test_backup_script_triggers_failure_alert_and_preserves_exit_code(tmp_path):
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    env_file = tmp_path / 'source.env'
    env_file.write_text('SECRET_KEY=drill\n', encoding='utf-8')
    alert_log = tmp_path / 'alert-fired.json'

    env = os.environ.copy()
    env.update({
        'BACKUP_STORAGE': 'local',
        'BACKUP_DB_BACKEND': 'sqlite',
        'BACKUP_LOCAL_ROOT': str(tmp_path / 'r2-mock'),
        'R2_BUCKET': 'flog-drill-bucket',
        'BACKUP_PREFIX': 'nonprod-drill',
        'BACKUP_DB_PATH': str(tmp_path / 'missing.sqlite3'),
        'BACKUP_UPLOADS': str(uploads),
        'BACKUP_ENV_FILE': str(env_file),
        'BACKUP_ALERT_DISABLE': '0',
        'BACKUP_ALERT_CMD': (
            f'printf \'{{"stage":"%s","code":"%s","target":"%s"}}\\n\' '
            f'"$BACKUP_ALERT_STAGE" "$BACKUP_ALERT_EXIT_CODE" "$BACKUP_ALERT_TARGET" '
            f'> "{alert_log}"'
        ),
    })

    result = subprocess.run(
        [str(BACKUP_SCRIPT)],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert alert_log.is_file()
    recorded = json.loads(alert_log.read_text(encoding='utf-8'))
    assert recorded['stage'] == 'db_dump'
    assert int(recorded['code']) == result.returncode
    assert 'flog-drill-bucket/nonprod-drill' in recorded['target']
