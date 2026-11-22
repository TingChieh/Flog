"""Regression tests for migration rollback ordering (downgrade before git reset)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = ROOT / 'scripts' / 'deploy.sh'
TAXONOMY_SPEC = ROOT / 'docs' / 'superpowers' / 'specs' / '2026-11-22-article-tags-and-series-design.md'


def _extract_rollback_hint(script_text: str) -> str:
    match = re.search(
        r'rollback_hint\(\)\s*\{.*?<<EOF\n(.*?)\nEOF\n\}',
        script_text,
        re.DOTALL,
    )
    assert match is not None, 'rollback_hint() heredoc not found in scripts/deploy.sh'
    return match.group(1)


def test_deploy_script_syntax_and_rollback_hint_order():
    syntax = subprocess.run(
        ['bash', '-n', str(DEPLOY_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    hint = _extract_rollback_hint(DEPLOY_SCRIPT.read_text(encoding='utf-8'))

    stop_idx = hint.find('systemctl stop $SERVICE')
    downgrade_idx = hint.find('flask db downgrade ${db_before:-base}')
    reset_idx = hint.find('git reset --hard ${current:0:7}')
    restart_idx = hint.find('systemctl restart $SERVICE')

    assert stop_idx != -1, hint
    assert downgrade_idx != -1, hint
    assert reset_idx != -1, hint
    assert restart_idx != -1, hint
    assert stop_idx < downgrade_idx < reset_idx < restart_idx, hint
    assert 'Full backup: $backup (database dump, uploads, .env)' in hint


def test_taxonomy_design_spec_documents_downgrade_before_git_reset():
    spec = TAXONOMY_SPEC.read_text(encoding='utf-8')
    section_match = re.search(
        r'## Migration and rollback\n(.*?)(?:\n## |\Z)',
        spec,
        re.DOTALL,
    )
    assert section_match is not None
    section = section_match.group(1)

    downgrade_idx = section.find('flask db downgrade')
    reset_idx = section.find('git reset --hard')
    restart_idx = section.find('systemctl restart')

    assert downgrade_idx != -1
    assert reset_idx != -1
    assert restart_idx != -1
    assert downgrade_idx < reset_idx < restart_idx


def _write_alembic_dir(script_dir: Path, include_taxonomy_rev: bool) -> Config:
    versions_dir = script_dir / 'versions'
    versions_dir.mkdir(parents=True)

    (script_dir / 'env.py').write_text(
        'from alembic import context\n'
        'import sqlalchemy as sa\n'
        'url = context.config.get_main_option("sqlalchemy.url")\n'
        'engine = sa.create_engine(url)\n'
        'with engine.connect() as conn:\n'
        '    context.configure(connection=conn, target_metadata=None)\n'
        '    with context.begin_transaction():\n'
        '        context.run_migrations()\n'
        'engine.dispose()\n',
        encoding='utf-8',
    )

    (versions_dir / '1111aaaa2222_base_post.py').write_text(
        'from alembic import op\n'
        'import sqlalchemy as sa\n\n'
        'revision = "1111aaaa2222"\n'
        'down_revision = None\n'
        'branch_labels = None\n'
        'depends_on = None\n\n'
        'def upgrade():\n'
        '    op.create_table(\n'
        '        "post",\n'
        '        sa.Column("id", sa.Integer(), primary_key=True),\n'
        '        sa.Column("title", sa.String(120), nullable=False),\n'
        '    )\n\n'
        'def downgrade():\n'
        '    op.drop_table("post")\n',
        encoding='utf-8',
    )

    if include_taxonomy_rev:
        (versions_dir / 'zzzz_taxonomy_probe.py').write_text(
            'from alembic import op\n'
            'import sqlalchemy as sa\n\n'
            'revision = "zzzz_taxonomy_probe"\n'
            'down_revision = "1111aaaa2222"\n'
            'branch_labels = None\n'
            'depends_on = None\n\n'
            'def upgrade():\n'
            '    op.create_table(\n'
            '        "tag",\n'
            '        sa.Column("id", sa.Integer(), primary_key=True),\n'
            '        sa.Column("slug", sa.String(80), nullable=False, unique=True),\n'
            '    )\n'
            '    op.create_table(\n'
            '        "post_tag",\n'
            '        sa.Column("post_id", sa.Integer(), sa.ForeignKey("post.id", ondelete="CASCADE"), primary_key=True),\n'
            '        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),\n'
            '    )\n\n'
            'def downgrade():\n'
            '    op.drop_table("post_tag")\n'
            '    op.drop_table("tag")\n',
            encoding='utf-8',
        )

    cfg = Config()
    cfg.set_main_option('script_location', str(script_dir))
    return cfg


def test_alembic_downgrade_fails_from_old_build_and_succeeds_from_new_build(tmp_path):
    db_url = f'sqlite:///{tmp_path / "rollback.sqlite3"}'
    old_cfg = _write_alembic_dir(tmp_path / 'old_migrations', include_taxonomy_rev=False)
    new_cfg = _write_alembic_dir(tmp_path / 'new_migrations', include_taxonomy_rev=True)
    old_cfg.set_main_option('sqlalchemy.url', db_url)
    new_cfg.set_main_option('sqlalchemy.url', db_url)

    # Start on the old build and seed existing article data.
    command.upgrade(old_cfg, 'head')
    engine = sa.create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO post (id, title) VALUES (1, 'Keep me')"))

        # Upgrade with the new build that introduces the taxonomy revision.
        command.upgrade(new_cfg, 'head')
        with engine.begin() as conn:
            conn.execute(sa.text("INSERT INTO tag (id, slug) VALUES (1, 'python')"))
            conn.execute(sa.text('INSERT INTO post_tag (post_id, tag_id) VALUES (1, 1)'))

        # Old order (reset first, then downgrade from old build) must fail because
        # the old build does not contain the new revision file.
        with pytest.raises(CommandError, match="Can't locate revision identified by 'zzzz_taxonomy_probe'"):
            command.downgrade(old_cfg, '1111aaaa2222')

        # New order (downgrade from new build first) succeeds and preserves legacy data.
        command.downgrade(new_cfg, '1111aaaa2222')

        # After downgrading, switching back to the old build matches its migration head.
        command.current(old_cfg)
        with engine.connect() as conn:
            version = conn.execute(sa.text('SELECT version_num FROM alembic_version')).scalar_one()
            posts = conn.execute(sa.text('SELECT id, title FROM post')).fetchall()
            tables = set(sa.inspect(conn).get_table_names())

        assert version == '1111aaaa2222'
        assert posts == [(1, 'Keep me')]
        assert 'tag' not in tables
        assert 'post_tag' not in tables
    finally:
        engine.dispose()
