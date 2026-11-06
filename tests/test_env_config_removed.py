from pathlib import Path

import pytest
from lxml import html as lxml_html

from app import app
from config import Config
from tests.conftest import login


ROOT = Path(__file__).resolve().parents[1]
UNUSED_SETTINGS = ('REDIS_URL', 'APPID', 'BD_TRANSLATOR_KEY',
                   'MS_TRANSLATOR_KEY', 'ELASTICSEARCH_URL', 'ENV_FILE_PATH')
KEPT_SETTINGS = ('SECRET_KEY', 'DATABASE_URL', 'ADMIN_EMAILS', 'MAIL_SERVER',
                 'MAIL_PORT', 'MAIL_USE_SSL', 'MAIL_USERNAME', 'MAIL_PASSWORD',
                 'UPLOAD_FOLDER', 'FFMPEG_PATH')


def test_environment_settings_page_is_gone(client, users):
    assert client.get('/admin/settings/environment').status_code == 404
    login(client, 'admin')
    assert client.get('/admin/settings/environment').status_code == 404
    assert client.post('/admin/settings/environment', data={
        'action': 'save'}).status_code == 404


def test_admin_navigation_has_no_environment_entry(client, users):
    login(client, 'admin')
    page = lxml_html.fromstring(client.get('/admin/').get_data(as_text=True))
    assert not page.xpath('//nav[@aria-label="管理导航"]//a[contains(., "环境配置")]')
    assert page.xpath('//nav[@aria-label="管理导航"]//a[contains(., "网站设置")]')


@pytest.mark.parametrize('relative', [
    'app/admin/env_settings.py', 'app/env_config.py', 'app/env_file.py',
    'app/env_checks.py', 'app/translate.py',
    'app/templates/admin/settings/environment.html',
    'tests/test_admin_env_settings.py', 'tests/test_env_checks.py',
    'tests/test_env_config.py', 'tests/test_env_file.py',
])
def test_environment_code_and_unused_translation_client_are_deleted(relative):
    assert not (ROOT / relative).exists(), relative


@pytest.mark.parametrize('name', UNUSED_SETTINGS)
def test_unused_settings_are_not_configured(name):
    assert not hasattr(Config, name), name
    assert name not in app.config, name


def test_no_redis_client_or_cache_object():
    import app as flog
    assert not hasattr(flog.app, 'redis')
    assert not hasattr(flog, 'cache')


def test_unused_dependencies_are_gone():
    for name in ('requirements.in', 'requirements.txt'):
        lines = {line.split('==')[0].strip().lower()
                 for line in (ROOT / name).read_text().splitlines()
                 if line and not line.startswith(('#', ' '))}
        for package in ('redis', 'requests', 'flask-caching', 'cachelib',
                        'urllib3', 'certifi', 'charset-normalizer'):
            assert package not in lines, (name, package)


def test_env_example_lists_only_settings_the_code_reads():
    keys = [line.split('=')[0] for line in
            (ROOT / '.env.example').read_text().splitlines()
            if line.strip() and not line.startswith('#')]
    assert set(keys) == set(KEPT_SETTINGS)


def test_stylesheet_has_no_environment_settings_rules():
    assert 'env-settings' not in (
        ROOT / 'app' / 'static' / 'style.css').read_text()
