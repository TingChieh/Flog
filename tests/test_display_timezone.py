import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from lxml import html as lxml_html

from app import db
from app.models import Category, Post
from app.timezones import to_display
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]
# 2022-12-05 01:02 in China is still 2022-12-04 in UTC.
EARLY = datetime(2022, 12, 4, 17, 2)
NEW_YEAR = datetime(2022, 12, 31, 17, 0)   # 2023-01-01 01:00 in China


def add_post(users, when, title, published=True):
    category = db.session.scalar(sa.select(Category))
    db.session.add(Post(title=title, body='b', user_id=users['admin'],
                        category=category, is_published=published,
                        timestamp=when))
    db.session.commit()


def test_to_display_converts_naive_utc_to_the_display_zone(application):
    with application.app_context():
        local = to_display(EARLY)
        assert (local.year, local.month, local.day, local.hour) == (2022, 12, 5, 1)
        assert local.utcoffset().total_seconds() == 8 * 3600


def test_to_display_accepts_aware_values_and_none(application):
    with application.app_context():
        aware = datetime(2022, 12, 4, 17, 2, tzinfo=timezone.utc)
        assert to_display(aware).day == 5
        assert to_display(None) is None


def test_display_zone_is_configurable(application):
    application.config['DISPLAY_TIMEZONE'] = 'UTC'
    try:
        with application.app_context():
            assert to_display(EARLY).day == 4
    finally:
        application.config['DISPLAY_TIMEZONE'] = 'Asia/Shanghai'


def load_config(tmp_path, **env):
    import os
    import shutil
    shutil.copy2(ROOT / 'config.py', tmp_path / 'config.py')
    environment = {k: v for k, v in os.environ.items() if k != 'DISPLAY_TIMEZONE'}
    environment.update(env)
    result = subprocess.run(
        [sys.executable, '-c',
         'import json; from config import Config; '
         'print(json.dumps([Config.DISPLAY_TIMEZONE, Config.BABEL_DEFAULT_TIMEZONE]))'],
        cwd=tmp_path, env=environment, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_config_defaults_to_china_time(tmp_path):
    assert load_config(tmp_path) == ['Asia/Shanghai', 'Asia/Shanghai']


def test_config_accepts_a_valid_zone_and_ignores_a_bad_one(tmp_path):
    assert load_config(tmp_path, DISPLAY_TIMEZONE='Europe/Berlin') == [
        'Europe/Berlin', 'Europe/Berlin']
    assert load_config(tmp_path, DISPLAY_TIMEZONE='Not/AZone') == [
        'Asia/Shanghai', 'Asia/Shanghai']


def test_archive_uses_local_dates_and_local_months(client, application, users):
    with application.app_context():
        add_post(users, EARLY, 'Early morning')
        add_post(users, NEW_YEAR, 'New year')
    document = lxml_html.fromstring(client.get('/archive').get_data(as_text=True))
    # NEW_YEAR is 22:00 on 31 Dec in UTC but already 2023 in China.
    assert document.xpath('//section[h2[normalize-space()="2023"]]//a[contains(., "New year")]')
    assert not document.xpath('//section[h2[normalize-space()="2022"]]//a[contains(., "New year")]')
    assert document.xpath('//section[h2[normalize-space()="2022"]]//a[contains(., "Early morning")]')
    early = document.xpath('//li[.//a[contains(., "Early morning")]]//time')[0]
    assert early.text_content().strip() == '2022年12月5日'
    assert early.get('datetime').startswith('2022-12-05T01:02')
    assert early.get('datetime').endswith('+08:00')


def test_post_list_shows_local_dates(client, application, users):
    with application.app_context():
        add_post(users, EARLY, 'Early morning')
    html = client.get('/').get_data(as_text=True)
    assert '2022年12月5日' in html
    assert '2022年12月4日' not in html


def test_admin_post_list_shows_local_dates(client, application, users):
    with application.app_context():
        add_post(users, EARLY, 'Early morning')
    login(client, 'admin')
    assert '2022-12-05' in client.get('/admin/posts').get_data(as_text=True)


def test_search_results_show_local_dates(client, application, users):
    with application.app_context():
        add_post(users, EARLY, 'Zebra crossing')
    payload = client.get('/api/search?q=Zebra').get_json()
    assert payload['results'][0]['date'] == '2022-12-05'
