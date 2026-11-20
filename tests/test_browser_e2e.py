"""Real Chromium browser regression tests driven by Playwright."""
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.browser


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


def _wait_for(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f'Test server did not become ready at {url}')


def _seed_database(work_dir: Path, env: dict[str, str]) -> None:
    seed_script = """
import io
from werkzeug.datastructures import FileStorage
from app import app, db
from app.images import save_uploaded_image
from app.models import Category, Post, SiteSettings, User
from app.search_index import rebuild_search_index
from tests.conftest import make_image

with app.app_context():
    db.create_all()
    db.session.add(SiteSettings(id=1))
    admin = User(username='admin', email='admin@example.com', role='admin')
    admin.set_password('password')
    category = Category(name='工程实践')
    db.session.add_all([admin, category])
    db.session.commit()

    img = save_uploaded_image(
        FileStorage(io.BytesIO(make_image('PNG', (640, 400))), filename='demo.png'),
        admin,
    )
    filler = ('这是一段用于拉长页面以验证阅读进度条和目录定位的示例正文。' * 18 + '\\n\\n') * 5
    body = (
        '## 架构边界\\n\\n'
        + filler
        + f'![示例架构图](/files/{img.filename})\\n\\n'
        + '## 代码示例\\n\\n'
        + '```python\\ndef hello(name: str) -> str:\\n    return f"hi {name}"\\n```\\n\\n'
        + filler
        + '## 验证闭环\\n\\n'
        + filler
    )
    db.session.add(Post(
        title='浏览器端到端回归测试文章',
        body=body,
        body_format='markdown',
        author=admin,
        category=category,
        is_published=True,
    ))
    db.session.commit()
    rebuild_search_index(db.session.connection())
    db.session.commit()
"""
    subprocess.run(
        [sys.executable, '-c', seed_script],
        cwd=ROOT,
        env=env,
        check=True,
    )


def _launch_chromium(playwright):
    try:
        return playwright.chromium.launch()
    except Exception:
        for candidate in ('chromium', 'chromium-browser', 'google-chrome'):
            binary = shutil.which(candidate)
            if binary:
                return playwright.chromium.launch(executable_path=binary)
        pytest.skip('No Chromium executable available for Playwright browser tests')


@pytest.fixture(scope='module')
def live_server(tmp_path_factory):
    work_dir = tmp_path_factory.mktemp('flog-browser')
    db_url = f'sqlite:///{work_dir / "browser.sqlite3"}'
    env = {
        **os.environ,
        'FLASK_APP': 'flog.py',
        'FLASK_DEBUG': '0',
        'SECRET_KEY': 'browser-test-secret-key-at-least-32-bytes',
        'DATABASE_URL': db_url,
        'TEST_DATABASE_URL': db_url,
        'UPLOAD_FOLDER': str(work_dir / 'uploads'),
        'MAIL_SERVER': '',
    }
    _seed_database(work_dir, env)

    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, '-m', 'flask', 'run', '--no-reload', '--port', str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    base_url = f'http://127.0.0.1:{port}'
    try:
        _wait_for(base_url + '/')
        yield base_url
    finally:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)


@pytest.fixture(scope='module')
def browser():
    with sync_playwright() as playwright:
        instance = _launch_chromium(playwright)
        try:
            yield instance
        finally:
            instance.close()


def _attach_guards(page):
    page_errors: list[str] = []
    failed_requests: list[str] = []
    page.on('pageerror', lambda exc: page_errors.append(str(exc)))
    page.on(
        'response',
        lambda resp: failed_requests.append(f'{resp.status} {resp.url}')
        if resp.status >= 400 and resp.url.startswith('http://127.0.0.1')
        else None,
    )
    return page_errors, failed_requests


def test_article_toc_reading_progress_lightbox_and_code_copy(browser, live_server):
    context = browser.new_context(
        viewport={'width': 1280, 'height': 800},
        permissions=['clipboard-read', 'clipboard-write'],
    )
    page = context.new_page()
    page_errors, failed_requests = _attach_guards(page)
    try:
        page.goto(f'{live_server}/post/1', wait_until='networkidle')

        # Code block highlighting + Copy button.
        code_el = page.locator('.article-body pre code.language-python')
        assert code_el.count() == 1
        assert code_el.locator('span').count() > 0
        copy_btn = page.locator('.article-body pre .code-copy')
        copy_btn.wait_for(state='visible')
        copy_btn.click()
        page.wait_for_function(
            "() => document.querySelector('.code-copy')?.textContent === 'Copied!'",
        )
        clipboard_text = page.evaluate('() => navigator.clipboard.readText()')
        assert 'def hello(name: str) -> str:' in clipboard_text

        # Reading progress advances as the reader scrolls through the article.
        initial_scale = page.evaluate(
            "() => getComputedStyle(document.querySelector('.reading-progress__bar')).transform",
        )
        page.evaluate('() => window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_function(
            """() => {
                const m = getComputedStyle(document.querySelector('.reading-progress__bar')).transform;
                if (!m || m === 'none') return false;
                const scaleX = parseFloat(m.replace('matrix(', '').split(',')[0]);
                return scaleX > 0.5;
            }""",
        )
        scrolled_scale = page.evaluate(
            "() => getComputedStyle(document.querySelector('.reading-progress__bar')).transform",
        )
        assert scrolled_scale != initial_scale

        # Table of contents jumps to heading anchor and updates aria-current.
        toc_links = page.locator('.article-toc-side .article-toc a')
        assert toc_links.count() == 3
        toc_links.nth(2).click()
        page.wait_for_function(
            "() => document.querySelectorAll('.article-toc-side .article-toc a')[2].getAttribute('aria-current') === 'location'",
        )

        # Image lightbox opens on click and closes with Escape while restoring focus.
        img = page.locator('.article-body img').first
        img.scroll_into_view_if_needed()
        img.click()
        page.locator('.pswp--open.pswp--ui-visible').wait_for(state='visible')
        page.locator('.pswp__button--close').wait_for(state='visible')
        page.wait_for_timeout(400)
        page.keyboard.press('Escape')
        page.locator('.pswp--open').wait_for(state='detached')

        assert page_errors == []
        assert failed_requests == []
    finally:
        context.close()


def test_search_modal_and_responsive_mobile_navigation(browser, live_server):
    # Desktop search dialog keyboard flow.
    desktop = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = desktop.new_page()
    page_errors, failed_requests = _attach_guards(page)
    try:
        page.goto(f'{live_server}/', wait_until='networkidle')
        page.keyboard.press('Control+k')
        dialog = page.locator('[data-search-dialog]')
        dialog.wait_for(state='visible')
        page.locator('[data-search-input]').fill('浏览器端到端')
        result_link = page.locator('[data-search-results] a').first
        result_link.wait_for(state='visible')
        assert '浏览器端到端回归测试文章' in (result_link.text_content() or '')
        page.keyboard.press('Escape')
        dialog.wait_for(state='hidden')
        assert page_errors == []
        assert failed_requests == []
    finally:
        desktop.close()

    # Mobile responsive layout + hamburger nav keyboard accessibility.
    mobile = browser.new_context(viewport={'width': 375, 'height': 812})
    m_page = mobile.new_page()
    m_errors, m_failed = _attach_guards(m_page)
    try:
        for path in ('/', '/post/1', '/archive'):
            m_page.goto(f'{live_server}{path}', wait_until='networkidle')
            overflow = m_page.evaluate(
                '() => document.documentElement.scrollWidth - window.innerWidth',
            )
            assert overflow <= 1, f'Horizontal overflow of {overflow}px on {path}'

        toggle = m_page.locator('[data-nav-toggle]')
        nav = m_page.locator('[data-site-nav]')
        assert toggle.is_visible()
        assert toggle.get_attribute('aria-expanded') == 'false'
        toggle.click()
        assert toggle.get_attribute('aria-expanded') == 'true'
        assert nav.is_visible()
        m_page.keyboard.press('Escape')
        assert toggle.get_attribute('aria-expanded') == 'false'
        assert not nav.is_visible()

        assert m_errors == []
        assert m_failed == []
    finally:
        mobile.close()
