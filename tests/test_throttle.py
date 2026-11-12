from datetime import datetime, timedelta

import sqlalchemy as sa

from app import db
from app.models import AuthAttempt
from app.throttle import LIMITS, LOGIN, RESET


def sign_in(client, password, address='10.0.0.1'):
    return client.post('/login', data={'username': 'author', 'password': password},
                       environ_base={'REMOTE_ADDR': address})


def test_repeated_failed_sign_ins_are_refused_for_a_while(client, users):
    limit, _ = LIMITS[LOGIN]
    for _ in range(limit):
        assert sign_in(client, 'wrong').headers['Location'] == '/login'

    blocked = sign_in(client, 'password')
    assert blocked.status_code == 429
    assert '登录失败次数过多' in blocked.get_data(as_text=True)
    # Another network is not held back by this one.
    assert sign_in(client, 'password', address='10.0.0.2').status_code == 302


def test_successful_sign_ins_do_not_count(client, users):
    limit, _ = LIMITS[LOGIN]
    for _ in range(limit + 2):
        assert sign_in(client, 'password').status_code == 302
        client.post('/logout')
    assert db.session.scalar(sa.select(sa.func.count()).select_from(AuthAttempt)) == 0


def test_reset_mail_is_capped_per_address_asked_for(client, users, outbox):
    limit, _ = LIMITS[RESET]
    for number in range(limit + 2):
        client.post('/reset_password_request', data={'email': 'author@example.com'},
                    environ_base={'REMOTE_ADDR': f'10.0.1.{number}'})
    assert len(outbox) == limit


def test_old_attempts_are_forgotten(client, users):
    db.session.add(AuthAttempt(action=LOGIN, key_hash='x' * 64,
                               created_at=datetime(2020, 1, 1)))
    db.session.commit()
    sign_in(client, 'wrong')
    assert db.session.scalar(sa.select(sa.func.count()).select_from(AuthAttempt).where(
        AuthAttempt.created_at < datetime.now() - timedelta(days=2))) == 0
