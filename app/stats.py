"""Lightweight aggregated site statistics (constant SQL queries, no body loads)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa

from app import db
from app.models import Category, Post, PostComment, PostLike
from app.post_drafts import normalize_utc_naive, utc_now_naive
from app.timezones import to_display


DEFAULT_TOP_LIMIT = 10
DEFAULT_RECENT_DAYS = 30


@dataclass(frozen=True)
class TopPostStat:
    id: int
    title: str
    view_count: int
    comment_count: int
    like_count: int
    published_at: datetime


@dataclass(frozen=True)
class CategoryStat:
    id: int
    name: str
    published_posts: int
    total_views: int


@dataclass(frozen=True)
class SiteStats:
    total_posts: int = 0
    published_posts: int = 0
    draft_posts: int = 0
    scheduled_posts: int = 0
    total_views: int = 0
    published_views: int = 0
    total_comments: int = 0
    approved_comments: int = 0
    pending_comments: int = 0
    recent_comments: int = 0
    total_likes: int = 0
    recent_likes: int = 0
    recent_days: int = DEFAULT_RECENT_DAYS
    top_posts: list[TopPostStat] = field(default_factory=list)
    categories: list[CategoryStat] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'posts': {
                'total': self.total_posts,
                'published': self.published_posts,
                'draft': self.draft_posts,
                'scheduled': self.scheduled_posts,
            },
            'views': {
                'total': self.total_views,
                'published': self.published_views,
            },
            'comments': {
                'total': self.total_comments,
                'approved': self.approved_comments,
                'pending': self.pending_comments,
                'recent': self.recent_comments,
                'recent_days': self.recent_days,
            },
            'likes': {
                'total': self.total_likes,
                'recent': self.recent_likes,
                'recent_days': self.recent_days,
            },
            'top_posts': [
                {
                    'id': item.id,
                    'title': item.title,
                    'view_count': item.view_count,
                    'comment_count': item.comment_count,
                    'like_count': item.like_count,
                    'published_at': to_display(item.published_at).replace(microsecond=0).isoformat(),
                }
                for item in self.top_posts
            ],
            'categories': [
                {
                    'id': item.id,
                    'name': item.name,
                    'published_posts': item.published_posts,
                    'total_views': item.total_views,
                }
                for item in self.categories
            ],
        }


def collect_site_stats(
    *,
    top_limit: int = DEFAULT_TOP_LIMIT,
    recent_days: int = DEFAULT_RECENT_DAYS,
    now: datetime | None = None,
) -> SiteStats:
    """Compute site-wide metrics using bounded aggregate SQL queries."""
    clamped_top = max(0, min(int(top_limit), 100))
    clamped_days = max(1, min(int(recent_days), 365))
    reference = normalize_utc_naive(now) if now is not None else utc_now_naive()
    cutoff = reference - timedelta(days=clamped_days)

    post_row = db.session.execute(
        sa.select(
            sa.func.count(Post.id),
            sa.func.coalesce(
                sa.func.sum(sa.case((Post.is_published.is_(True), 1), else_=0)), 0),
            sa.func.coalesce(
                sa.func.sum(sa.case(
                    (sa.and_(Post.is_published.is_(False), Post.scheduled_at.is_not(None)), 1),
                    else_=0)),
                0),
            sa.func.coalesce(sa.func.sum(Post.view_count), 0),
            sa.func.coalesce(
                sa.func.sum(sa.case((Post.is_published.is_(True), Post.view_count), else_=0)), 0),
        )
    ).one()

    total_posts = int(post_row[0] or 0)
    published_posts = int(post_row[1] or 0)
    scheduled_posts = int(post_row[2] or 0)
    draft_posts = max(0, total_posts - published_posts - scheduled_posts)
    total_views = int(post_row[3] or 0)
    published_views = int(post_row[4] or 0)

    comment_row = db.session.execute(
        sa.select(
            sa.func.count(PostComment.id),
            sa.func.coalesce(
                sa.func.sum(sa.case((PostComment.status == 'approved', 1), else_=0)), 0),
            sa.func.coalesce(
                sa.func.sum(sa.case((PostComment.status == 'pending', 1), else_=0)), 0),
            sa.func.coalesce(
                sa.func.sum(sa.case((PostComment.timestamp >= cutoff, 1), else_=0)), 0),
        )
    ).one()

    like_row = db.session.execute(
        sa.select(
            sa.func.count(PostLike.id),
            sa.func.coalesce(
                sa.func.sum(sa.case((PostLike.timestamp >= cutoff, 1), else_=0)), 0),
        )
    ).one()

    top_posts: list[TopPostStat] = []
    if clamped_top > 0:
        top_rows = db.session.execute(
            sa.select(Post.id, Post.title, Post.view_count, Post.timestamp)
            .where(Post.is_published.is_(True))
            .order_by(Post.view_count.desc(), Post.timestamp.desc(), Post.id.desc())
            .limit(clamped_top)
        ).all()
        if top_rows:
            top_ids = [row.id for row in top_rows]
            comment_counts = dict(db.session.execute(
                sa.select(PostComment.post_id, sa.func.count(PostComment.id))
                .where(
                    PostComment.post_id.in_(top_ids),
                    PostComment.status == 'approved',
                )
                .group_by(PostComment.post_id)
            ).all())
            like_counts = dict(db.session.execute(
                sa.select(PostLike.post_id, sa.func.count(PostLike.id))
                .where(PostLike.post_id.in_(top_ids))
                .group_by(PostLike.post_id)
            ).all())
            top_posts = [
                TopPostStat(
                    id=int(row.id),
                    title=row.title,
                    view_count=int(row.view_count or 0),
                    comment_count=int(comment_counts.get(row.id, 0)),
                    like_count=int(like_counts.get(row.id, 0)),
                    published_at=row.timestamp,
                )
                for row in top_rows
            ]

    category_rows = db.session.execute(
        sa.select(
            Category.id,
            Category.name,
            sa.func.count(Post.id),
            sa.func.coalesce(sa.func.sum(Post.view_count), 0),
        )
        .outerjoin(
            Post,
            sa.and_(Post.category_id == Category.id, Post.is_published.is_(True)),
        )
        .group_by(Category.id, Category.name)
        .order_by(sa.func.coalesce(sa.func.sum(Post.view_count), 0).desc(), Category.name)
    ).all()
    categories = [
        CategoryStat(
            id=int(row[0]),
            name=row[1],
            published_posts=int(row[2] or 0),
            total_views=int(row[3] or 0),
        )
        for row in category_rows
    ]

    return SiteStats(
        total_posts=total_posts,
        published_posts=published_posts,
        draft_posts=draft_posts,
        scheduled_posts=scheduled_posts,
        total_views=total_views,
        published_views=published_views,
        total_comments=int(comment_row[0] or 0),
        approved_comments=int(comment_row[1] or 0),
        pending_comments=int(comment_row[2] or 0),
        recent_comments=int(comment_row[3] or 0),
        total_likes=int(like_row[0] or 0),
        recent_likes=int(like_row[1] or 0),
        recent_days=clamped_days,
        top_posts=top_posts,
        categories=categories,
    )
