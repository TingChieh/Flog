"""Tests for lightweight aggregated statistics (empty data, boundaries, query budget, access)."""
import json
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import event

from app import db
from app.models import Category, Post, PostComment, PostLike, User
from app.stats import collect_site_stats
from tests.conftest import login


def test_stats_on_empty_database(application):
    with application.app_context():
        stats = collect_site_stats()
    assert stats.total_posts == 0
    assert stats.published_posts == 0
    assert stats.draft_posts == 0
    assert stats.scheduled_posts == 0
    assert stats.total_views == 0
    assert stats.total_comments == 0
    assert stats.total_likes == 0
    assert stats.top_posts == []
    assert stats.categories == []
    assert stats.to_dict()['posts']['total'] == 0


def test_stats_aggregates_posts_views_comments_likes_and_categories(application, users):
    now = datetime(2026, 11, 22, 6, 0, tzinfo=timezone.utc)
    with application.app_context():
        author = db.session.get(User, users['author'])
        assert author is not None
        cat_a = db.session.scalar(sa.select(Category))
        assert cat_a is not None
        cat_empty = Category(name='空分类')
        db.session.add(cat_empty)
        db.session.flush()

        p_live = db.session.get(Post, users['post'])
        assert p_live is not None
        p_live.view_count = 150
        p_live.timestamp = now - timedelta(days=5)

        p_top = Post(
            title='高阅读文章', body='body', author=author, category=cat_a,
            is_published=True, view_count=420, timestamp=now - timedelta(days=2),
        )
        p_draft = Post(
            title='未发布草稿', body='draft', author=author, category=cat_a,
            is_published=False, view_count=999, timestamp=now - timedelta(days=1),
        )
        p_sched = Post(
            title='定时文章', body='sched', author=author, category=cat_a,
            is_published=False, scheduled_at=now + timedelta(days=2), view_count=0,
        )
        db.session.add_all([p_top, p_draft, p_sched])
        db.session.flush()

        db.session.add_all([
            PostComment(post_id=p_top.id, name='A', email='a@e.co', body='ok',
                        status='approved', timestamp=now - timedelta(days=1)),
            PostComment(post_id=p_top.id, name='B', email='b@e.co', body='wait',
                        status='pending', timestamp=now - timedelta(days=2)),
            PostComment(post_id=p_live.id, name='C', email='c@e.co', body='old',
                        status='approved', timestamp=now - timedelta(days=60)),
            PostLike(post_id=p_top.id, visitor_id='v1', timestamp=now - timedelta(days=1)),
            PostLike(post_id=p_top.id, visitor_id='v2', timestamp=now - timedelta(days=45)),
        ])
        db.session.commit()

        stats = collect_site_stats(top_limit=5, recent_days=30, now=now)

        assert stats.total_posts == 4
        assert stats.published_posts == 2
        assert stats.draft_posts == 1
        assert stats.scheduled_posts == 1
        assert stats.total_views == 150 + 420 + 999
        assert stats.published_views == 150 + 420
        assert stats.total_comments == 3
        assert stats.approved_comments == 2
        assert stats.pending_comments == 1
        assert stats.recent_comments == 2
        assert stats.total_likes == 2
        assert stats.recent_likes == 1

        # Top posts must include only published posts, ordered by view_count desc.
        assert [p.title for p in stats.top_posts] == ['高阅读文章', 'Test']
        assert stats.top_posts[0].comment_count == 1  # approved only
        assert stats.top_posts[0].like_count == 2

        cat_map = {c.name: (c.published_posts, c.total_views) for c in stats.categories}
        assert cat_map['General'] == (2, 570)
        assert cat_map['空分类'] == (0, 0)

        # Boundary: top_limit=0 skips top-post queries cleanly.
        zero_top = collect_site_stats(top_limit=0, recent_days=1, now=now)
        assert zero_top.top_posts == []
        assert zero_top.recent_days == 1


def test_stats_query_budget_stays_constant_without_loading_post_bodies(application, users):
    with application.app_context():
        author = db.session.get(User, users['author'])
        cat = db.session.scalar(sa.select(Category))
        for i in range(25):
            post = Post(
                title=f'文章 {i}', body='很长的正文' * 200, author=author,
                category=cat, is_published=True, view_count=i * 10,
            )
            db.session.add(post)
            db.session.flush()
            db.session.add(PostComment(
                post_id=post.id, name='R', email='r@e.co', body='hi', status='approved'))
            db.session.add(PostLike(post_id=post.id, visitor_id=f'vis-{i}'))
        db.session.commit()

        queries: list[str] = []

        def listener(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        event.listen(db.engine, 'before_cursor_execute', listener)
        try:
            stats = collect_site_stats(top_limit=10, recent_days=30)
        finally:
            event.remove(db.engine, 'before_cursor_execute', listener)

    assert len(stats.top_posts) == 10
    assert len(queries) <= 7, f'Expected <= 7 aggregate queries, ran {len(queries)}'
    assert all('post.body' not in q.lower() for q in queries)


def test_admin_stats_access_and_cli_output(client, application, users):
    assert client.get('/admin/stats').status_code == 302

    login(client, 'author')
    assert client.get('/admin/stats').status_code == 403

    client.post('/logout')
    login(client, 'admin')
    resp = client.get('/admin/stats')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert '数据统计' in body
    assert '热门文章' in body
    assert '分类分布' in body

    runner = application.test_cli_runner()
    res_json = runner.invoke(args=['stats', '--json'])
    assert res_json.exit_code == 0, res_json.output
    data = json.loads(res_json.output)
    assert data['posts']['published'] == 1

    res_text = runner.invoke(args=['stats'])
    assert res_text.exit_code == 0, res_text.output
    assert 'Posts: 1 total' in res_text.output
