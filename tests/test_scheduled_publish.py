"""Tests for scheduled post publishing: timezone handling, boundaries, idempotency, UI, and migration."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app import db
from app.models import Post, User
from app.post_drafts import (
    DraftValues,
    PostDraftError,
    cancel_schedule,
    publish_draft,
    publish_due_posts,
    save_draft,
    schedule_post,
    unpublish_post,
)
from tests.conftest import login


def _new_draft(users, title='定时文章', body='正文内容'):
    author = db.session.get(User, users['author'])
    assert author is not None
    post = save_draft(author, None, DraftValues(title, body, 1))
    db.session.flush()
    return author, post


def test_schedule_post_converts_display_timezone_and_hides_from_public(
    client, application, users
):
    with application.app_context():
        author, post = _new_draft(users, title='明日发布', body='计划明天发布')
        # 2026-12-01 08:30 in Asia/Shanghai -> 2026-12-01 00:30 UTC.
        local_future = datetime(2026, 12, 1, 8, 30)
        ref_now = datetime(2026, 11, 30, 0, 0, tzinfo=timezone.utc)

        schedule_post(author, post.id, local_future, now=ref_now)
        db.session.commit()
        post_id = post.id

        assert post.is_published is False
        assert post.scheduled_at == datetime(2026, 12, 1, 0, 30)

    # Must not leak on any public endpoint before due time.
    assert client.get(f'/post/{post_id}').status_code == 404
    for path in ('/', '/archive', '/feed.xml', '/sitemap.xml'):
        assert '明日发布' not in client.get(path).get_data(as_text=True), path
    assert client.get('/api/search?q=明日发布').get_json()['results'] == []
    assert '计划明天发布' not in client.get('/search?q=明日发布').get_data(as_text=True)


def test_schedule_post_rejects_past_time_live_post_and_incomplete_draft(
    application, users
):
    with application.app_context():
        author, post = _new_draft(users)
        ref_now = datetime(2026, 11, 22, 6, 0, tzinfo=timezone.utc)

        # Past time rejected (13:59 Asia/Shanghai == 05:59 UTC < 06:00 UTC).
        with pytest.raises(PostDraftError, match='future'):
            schedule_post(author, post.id, datetime(2026, 11, 22, 13, 59), now=ref_now)

        # Already-published post rejected.
        with pytest.raises(PostDraftError, match='Already published'):
            schedule_post(author, users['post'], datetime(2026, 12, 1, 8, 0), now=ref_now)

        # Empty body rejected.
        save_draft(author, post, DraftValues('仅标题', '   ', 1))
        with pytest.raises(PostDraftError, match='body'):
            schedule_post(author, post.id, datetime(2026, 12, 1, 8, 0), now=ref_now)


def test_publish_due_posts_boundary_and_idempotency(client, application, users):
    with application.app_context():
        author, due_post = _new_draft(users, title='到点文章', body='到点内容')
        _, future_post = _new_draft(users, title='未到点文章', body='未来内容')
        ref_now = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)
        due_time = datetime(2026, 12, 1, 8, 0, tzinfo=timezone(timedelta(hours=8)))  # 00:00 UTC
        future_time = datetime(2026, 12, 1, 9, 0, tzinfo=timezone(timedelta(hours=8)))  # 01:00 UTC

        schedule_post(author, due_post.id, due_time, now=ref_now - timedelta(hours=1))
        schedule_post(author, future_post.id, future_time, now=ref_now - timedelta(hours=1))
        db.session.commit()
        due_id, future_id = due_post.id, future_post.id

        # 1 second before due -> publishes nothing.
        early = publish_due_posts(now=ref_now - timedelta(seconds=1))
        assert early.published_ids == []

        # Exact due moment -> publishes due_post only.
        on_time = publish_due_posts(now=ref_now)
        db.session.commit()
        assert on_time.published_ids == [due_id]
        assert on_time.failed == []

        refreshed_due = db.session.get(Post, due_id)
        refreshed_future = db.session.get(Post, future_id)
        assert refreshed_due is not None and refreshed_future is not None
        assert refreshed_due.is_published is True
        assert refreshed_due.scheduled_at is None
        assert refreshed_due.draft is None
        assert refreshed_due.timestamp == datetime(2026, 12, 1, 0, 0)
        assert refreshed_due.updated_at is None
        assert refreshed_future.is_published is False
        assert refreshed_future.scheduled_at == datetime(2026, 12, 1, 1, 0)

        # Repeating publish_due_posts is strictly idempotent.
        again = publish_due_posts(now=ref_now + timedelta(minutes=30))
        db.session.commit()
        assert again.published_ids == []
        assert db.session.get(Post, due_id).timestamp == datetime(2026, 12, 1, 0, 0)

    assert client.get(f'/post/{due_id}').status_code == 200
    assert client.get(f'/post/{future_id}').status_code == 404


def test_cancel_schedule_manual_publish_and_unpublish_clear_schedule(application, users):
    with application.app_context():
        author, post = _new_draft(users, title='可取消定时', body='正文')
        base = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)
        target = base + timedelta(hours=2)

        schedule_post(author, post.id, target, now=base)
        cancel_schedule(author, post.id)
        db.session.commit()
        assert post.scheduled_at is None
        assert publish_due_posts(now=target + timedelta(hours=1)).published_ids == []

        # Re-schedule then manually publish immediately -> schedule cleared.
        schedule_post(author, post.id, target, now=base)
        publish_draft(author, post.id)
        db.session.commit()
        assert post.is_published is True
        assert post.scheduled_at is None

        # Unpublish clears any schedule and never auto-republishes.
        unpublish_post(author, post.id)
        db.session.commit()
        assert post.is_published is False
        assert post.scheduled_at is None
        assert publish_due_posts(now=target + timedelta(days=1)).published_ids == []


def test_admin_schedule_routes_and_cli_publish_due(client, application, users):
    with application.app_context():
        _, post = _new_draft(users, title='后台定时文章', body='内容')
        db.session.commit()
        post_id = post.id

    # Other non-owner cannot schedule.
    login(client, 'other')
    assert client.post(
        f'/admin/posts/{post_id}/schedule',
        data={'scheduled_at': '2099-01-02T09:30'},
    ).status_code == 403

    client.post('/logout')
    login(client, 'author')
    resp = client.post(
        f'/admin/posts/{post_id}/schedule',
        data={'scheduled_at': '2099-01-02T09:30'},
    )
    assert resp.status_code == 302
    list_html = client.get('/admin/posts').get_data(as_text=True)
    assert '定时发布 2099-01-02 09:30' in list_html

    # CLI publishes when --at reaches the scheduled time.
    runner = application.test_cli_runner()
    cli_res = runner.invoke(
        args=['posts', 'publish-due', '--at', '2099-01-02T09:30:00+08:00'])
    assert cli_res.exit_code == 0, cli_res.output
    assert 'Published 1 scheduled post(s).' in cli_res.output
    assert client.get(f'/post/{post_id}').status_code == 200


def test_scheduled_at_migration_upgrade_and_downgrade():
    path = (
        Path(__file__).parents[1]
        / 'migrations'
        / 'versions'
        / 'd4e8f1a2b305_add_post_scheduled_at.py'
    )
    spec = importlib.util.spec_from_file_location('post_scheduled_at', path)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    posts = sa.Table(
        'post', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('title', sa.String(120), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(posts.insert().values(title='Existing'))
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
            rows = connection.execute(sa.text('SELECT title, scheduled_at FROM post')).all()
            assert rows == [('Existing', None)]
            indexes = {i['name'] for i in sa.inspect(connection).get_indexes('post')}
            assert 'ix_post_scheduled_at' in indexes
            revision.downgrade()
            columns = [c['name'] for c in sa.inspect(connection).get_columns('post')]
    assert 'scheduled_at' not in columns
