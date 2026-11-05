import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app import app

ROOT = Path(__file__).resolve().parents[1]
# Built from pieces so this file does not contain the IDs it looks for.
PRIVATE_IDS = ('GTM-' + 'TCG2DVQL', 'G-' + 'NZS42NTC19')
TEXT_SUFFIXES = {'.py', '.html', '.js', '.css', '.md', '.txt', '.toml',
                 '.example', '.in', '.cfg', '.json'}


def tracked_text_files():
    names = subprocess.run(
        ['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.splitlines()
    for name in names:
        path = ROOT / name
        if 'static/vendor/' in name or not path.is_file():
            continue
        if path.suffix in TEXT_SUFFIXES or path.name.startswith('.env'):
            yield name, path


def test_no_personal_analytics_ids_are_committed():
    hits = [name for name, path in tracked_text_files()
            if any(i in path.read_text(errors='ignore') for i in PRIVATE_IDS)]
    assert hits == []


def test_docs_and_code_carry_no_local_machine_paths():
    markers = ('/Users/', '/private/tmp', 'claude-501')
    hits = [name for name, path in tracked_text_files()
            if name != 'tests/test_public_repo_hygiene.py'
            and any(m in path.read_text(errors='ignore') for m in markers)]
    assert hits == []


# --- analytics is opt-in -----------------------------------------------------------

def page(client):
    return client.get('/').get_data(as_text=True)


def test_analytics_is_off_by_default(client):
    html = page(client)
    assert 'googletagmanager' not in html
    assert 'gtag(' not in html
    assert 'dataLayer' not in html


def test_tag_manager_loads_only_when_configured(client, application):
    application.config['GTM_ID'] = 'GTM-TEST123'
    html = page(client)
    assert "'dataLayer','GTM-TEST123'" in html
    assert 'ns.html?id=GTM-TEST123' in html
    assert 'gtag(' not in html


def test_google_tag_loads_only_when_configured(client, application):
    application.config['GA_MEASUREMENT_ID'] = 'G-TEST12345'
    html = page(client)
    assert 'gtag/js?id=G-TEST12345' in html
    assert "gtag('config', 'G-TEST12345')" in html
    assert 'gtm.js' not in html


@pytest.fixture(autouse=True)
def _reset_analytics_config(application):
    yield
    application.config.pop('GTM_ID', None)
    application.config.pop('GA_MEASUREMENT_ID', None)


# --- config parsing --------------------------------------------------------------------

def load_config(tmp_path, **env):
    shutil.copy2(ROOT / 'config.py', tmp_path / 'config.py')
    environment = {k: v for k, v in os.environ.items()
                   if k not in ('GTM_ID', 'GA_MEASUREMENT_ID')}
    environment.update(env)
    result = subprocess.run(
        [sys.executable, '-c',
         'import json; from config import Config; '
         'print(json.dumps({"gtm": Config.GTM_ID, "ga": Config.GA_MEASUREMENT_ID}))'],
        cwd=tmp_path, env=environment, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_config_defaults_to_no_analytics(tmp_path):
    assert load_config(tmp_path) == {'gtm': None, 'ga': None}


def test_config_accepts_well_formed_ids(tmp_path):
    assert load_config(tmp_path, GTM_ID='GTM-ABC123', GA_MEASUREMENT_ID='G-ABC123XYZ') == {
        'gtm': 'GTM-ABC123', 'ga': 'G-ABC123XYZ'}


@pytest.mark.parametrize('bad', ["GTM-'];alert(1);//", 'gtm-abc', 'G-ABC', '<script>', 'GTM-'])
def test_config_drops_malformed_ids(tmp_path, bad):
    assert load_config(tmp_path, GTM_ID=bad, GA_MEASUREMENT_ID=bad) == {
        'gtm': None, 'ga': None}


def test_env_example_documents_the_optional_ids():
    text = (ROOT / '.env.example').read_text()
    assert '# GTM_ID=' in text and '# GA_MEASUREMENT_ID=' in text


# --- third-party artwork is gone ------------------------------------------------------

REMOVED_IMAGES = ('aisaka.png', 'toto.jpg', 'totoro.gif', 'hero.jpg', 'hero.png')


@pytest.mark.parametrize('name', REMOVED_IMAGES)
def test_removed_images_are_gone_and_unreferenced(name):
    assert not (ROOT / 'app/static/images' / name).exists()
    hits = [n for n, path in tracked_text_files()
            if not n.startswith('docs/') and n != 'tests/test_public_repo_hygiene.py'
            and f'images/{name}' in path.read_text(errors='ignore')
            and not n.startswith('tests/test_ui_shell.py')]
    assert hits == []


def test_every_image_the_stylesheet_references_exists():
    import re
    css = (ROOT / 'app/static/style.css').read_text()
    for match in re.finditer(r'url\(\s*["\']?(images/[^"\')\s]+)', css):
        assert (ROOT / 'app/static' / match.group(1)).is_file(), match.group(1)
