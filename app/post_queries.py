"""Queries for published article lists and reading links."""

from datetime import datetime, timezone

import sqlalchemy as sa

from app import db
from app.models import Post


def published_post_statement():
    return sa.select(Post).where(Post.is_published.is_(True))


def article_discovery(post: Post):
    candidates = (published_post_statement()
                  .with_only_columns(Post.id, Post.title, Post.timestamp)
                  .where(Post.timestamp <= datetime.now(timezone.utc)))
    earlier = sa.and_(Post.timestamp <= post.timestamp,
                      sa.or_(Post.timestamp < post.timestamp, Post.id < post.id))
    later = sa.and_(Post.timestamp >= post.timestamp,
                    sa.or_(Post.timestamp > post.timestamp, Post.id > post.id))
    latest_first = (Post.timestamp.desc(), Post.id.desc())
    previous = candidates.where(earlier).order_by(*latest_first).limit(1).subquery()
    following = candidates.where(later).order_by(Post.timestamp, Post.id).limit(1).subquery()
    # Isolate each ordered LIMIT so SQLite and MariaDB can combine the results in one round trip.
    selections = [sa.select(sa.literal('prev').label('slot'), previous),
                  sa.select(sa.literal('next').label('slot'), following)]
    if post.category_id is not None:
        related = (candidates.where(Post.category_id == post.category_id, Post.id != post.id)
                   .order_by(*latest_first).limit(3).subquery())
        selections.append(sa.select(sa.literal('related').label('slot'), related))

    links = sa.union_all(*selections).subquery()
    rows = db.session.execute(sa.select(links).order_by(links.c.timestamp.desc(), links.c.id.desc())).all()
    return {
        'previous_article': next((row for row in rows if row.slot == 'prev'), None),
        'next_article': next((row for row in rows if row.slot == 'next'), None),
        'related_articles': [row for row in rows if row.slot == 'related'],
    }
