from datetime import datetime, timedelta, timezone

from app import db
from app.models import User
from tests.conftest import login


# The test client's requests share the fixture's app context and session.
def _last_seen(application, user_id):
    db.session.expire_all()
    return db.session.get(User, user_id).last_seen


def _set_last_seen(application, user_id, value):
    db.session.get(User, user_id).last_seen = value
    db.session.commit()


def test_last_seen_is_written_at_most_every_few_minutes(client, application, users):
    login(client, 'author')
    recent = datetime.now(timezone.utc) - timedelta(minutes=1)
    _set_last_seen(application, users['author'], recent)
    client.get('/')
    assert _last_seen(application, users['author']).replace(tzinfo=None) == recent.replace(tzinfo=None)

    _set_last_seen(application, users['author'], recent - timedelta(hours=1))
    client.get('/')
    assert _last_seen(application, users['author']).replace(tzinfo=None) > recent.replace(tzinfo=None)


def test_static_files_do_not_touch_last_seen(client, application, users):
    login(client, 'author')
    stale = datetime.now(timezone.utc) - timedelta(days=1)
    _set_last_seen(application, users['author'], stale)
    assert client.get('/static/site.js').status_code == 200
    assert _last_seen(application, users['author']).replace(tzinfo=None) == stale.replace(tzinfo=None)
