import sqlalchemy as sa
from flask import Response, current_app, url_for
from itsdangerous import BadSignature, TimestampSigner
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app import db
from app.models import Post


COOKIE_PREFIX = 'post_viewed_'
SIGNING_SALT = 'post-view-count'
# MariaDB snapshot-isolation conflict (1020) and InnoDB deadlock (1213).
_RETRYABLE_MYSQL_ERRNOS = frozenset({1020, 1213})
_MAX_VIEW_UPDATE_ATTEMPTS = 2


def view_cookie_name(post_id: int) -> str:
    return f'{COOKIE_PREFIX}{post_id}'


def _signer() -> TimestampSigner:
    return TimestampSigner(current_app.config['SECRET_KEY'], salt=SIGNING_SALT)


def has_recent_view(post_id: int, marker: str | None) -> bool:
    if not marker:
        return False
    try:
        payload = _signer().unsign(
            marker,
            max_age=current_app.config['POST_VIEW_WINDOW_SECONDS'],
        )
    except BadSignature:
        return False
    return payload == str(post_id).encode('ascii')


def _is_retryable_concurrency_error(exc: SQLAlchemyError) -> bool:
    if not isinstance(exc, OperationalError):
        return False
    orig = exc.orig
    return (orig is not None and bool(orig.args)
            and orig.args[0] in _RETRYABLE_MYSQL_ERRNOS)


def record_view(post: Post) -> bool:
    post_id = post.id
    for attempt in range(1, _MAX_VIEW_UPDATE_ATTEMPTS + 1):
        try:
            db.session.execute(
                sa.update(Post)
                .where(Post.id == post_id)
                .values(view_count=Post.view_count + 1)
                .execution_options(synchronize_session=False)
            )
            db.session.refresh(post)
            db.session.commit()
            return True
        except SQLAlchemyError as exc:
            db.session.rollback()
            if (attempt < _MAX_VIEW_UPDATE_ATTEMPTS
                    and _is_retryable_concurrency_error(exc)):
                continue
            current_app.logger.exception(
                'Failed to increment view count for post %s', post_id)
            return False
    return False


def attach_view_cookie(response: Response, post_id: int) -> None:
    max_age = current_app.config['POST_VIEW_WINDOW_SECONDS']
    marker = _signer().sign(str(post_id).encode('ascii')).decode('ascii')
    response.set_cookie(
        view_cookie_name(post_id),
        marker,
        max_age=max_age,
        path=url_for('post', post_id=post_id),
        secure=bool(current_app.config.get('SESSION_COOKIE_SECURE', False)),
        httponly=True,
        samesite='Lax',
    )
