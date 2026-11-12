"""Slow down password guessing and floods of reset emails.

Each failed sign-in and each reset request is written down under keyed hashes
(of the network address, and for a reset also of the email address asked for)
and forgotten after a day. Nothing here commits; the caller owns the
transaction.
"""
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from app import db
from app.likes import _digest, hash_address
from app.models import AuthAttempt

LOGIN, RESET = 'login', 'reset'
# action -> (attempts allowed, within this many seconds)
LIMITS = {
    LOGIN: (10, 15 * 60),
    RESET: (5, 60 * 60),
}
KEEP = timedelta(days=1)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _keys(emails):
    return [hash_address()] + [
        _digest('email', email.strip().lower()) for email in emails if email]


def blocked(action, *emails):
    """Whether this address, or any of ``emails``, has used up its attempts."""
    limit, seconds = LIMITS[action]
    since = _now() - timedelta(seconds=seconds)
    for key in _keys(emails):
        used = db.session.scalar(sa.select(sa.func.count()).select_from(
            AuthAttempt).where(
                AuthAttempt.action == action, AuthAttempt.key_hash == key,
                AuthAttempt.created_at >= since))
        if used >= limit:
            return True
    return False


def note(action, *emails):
    """Count one attempt against this address and ``emails``."""
    now = _now()
    db.session.execute(sa.delete(AuthAttempt).where(
        AuthAttempt.created_at < now - KEEP))
    db.session.add_all(AuthAttempt(action=action, key_hash=key, created_at=now)
                       for key in _keys(emails))
