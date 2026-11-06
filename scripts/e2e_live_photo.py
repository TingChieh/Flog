#!/usr/bin/env python
"""Drive a real browser through the Live Photo and image-delivery features.

Seeds a throw-away database and upload folder, starts the app on a free port
and checks, in Chromium via Playwright CLI: layout, responsive variants,
automatic first play, the LIVE button, the lightbox and the admin upload form.

    .venv/bin/python scripts/e2e_live_photo.py [--keep] [--headed]

Needs Node (``npx``) and ffmpeg. Playwright CLI is fetched by npx on first use;
set PWCLI to use another command (e.g. ``PWCLI=playwright-cli``). Nothing
touches the development database or ``instance/``. ``--keep`` leaves the temp
folder (with screenshots in ``shots/``) for inspection.
"""
import io
import json
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASSWORD = 'password'


def seed(work):
    """Create the database, an admin, and a post with a Live Photo."""
    work = Path(work)
    from werkzeug.datastructures import FileStorage

    from app import app, db
    from app.images import save_uploaded_image
    from app.models import Category, Post, SiteSettings, User
    from tests.conftest import make_heic, make_image, make_video

    def upload(data, name, user, video=None):
        return save_uploaded_image(
            FileStorage(io.BytesIO(data), filename=name), user, video=video)

    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(SiteSettings(id=1))
        admin = User(username='admin', email='admin@example.com', role='admin')
        admin.set_password(PASSWORD)
        category = Category(name='General')
        db.session.add_all([admin, category])
        db.session.commit()

        clip = make_video(work, '.mov', size='1280x720', seconds=3)
        live = upload(make_heic((1600, 2400), 'steelblue'), 'IMG_0001.HEIC', admin,
                      video=FileStorage(io.BytesIO(clip), filename='IMG_0001.MOV'))
        plain = upload(make_image('JPEG', (2400, 1200), photo=True), 'plain.jpg', admin)
        tall = upload(make_image('JPEG', (1200, 2400), photo=True), 'tall.jpg', admin)
        body = (f'开头。\n\n![海边](/files/{live.filename})\n\n中间。\n\n'
                f'![普通图](/files/{plain.filename})\n\n'
                f'![竖图](/files/{tall.filename})\n\n结尾。')
        db.session.add(Post(title='Live Photo 测试', body=body, author=admin,
                            body_format='markdown', category=category,
                            is_published=True))
        db.session.commit()
    (Path(work) / 'IMG_7777.HEIC').write_bytes(make_heic((1600, 1200), 'orange'))
    (Path(work) / 'IMG_7777.MOV').write_bytes(clip)


class Runner:
    def __init__(self, work, base, headed):
        self.work, self.base, self.headed = Path(work), base, headed
        self.pwcli = shlex.split(os.environ.get('PWCLI') or
                                 'npx --yes --package @playwright/cli playwright-cli')
        self.failures = []

    def pw(self, *args, timeout=240):
        result = subprocess.run([*self.pwcli, *args], cwd=self.work, text=True,
                                capture_output=True, timeout=timeout)
        return result.stdout + result.stderr

    def run(self, js):
        """Run an async ``page => ...`` snippet and return its JSON result."""
        out = self.pw('run-code', js)
        marker = '### Result\n'
        if marker not in out:
            raise RuntimeError(f'no result from browser:\n{out[-800:]}')
        text = out.split(marker, 1)[1].split('\n### ', 1)[0].strip()
        return json.loads(text) if text else None

    def check(self, name, ok, detail=''):
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f'   {detail}' if detail and not ok else ''))
        if not ok:
            self.failures.append(name)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_for(url, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError(f'{url} did not come up')


GOTO_POST = "await page.goto(BASE + '/post/1'); await page.waitForLoadState('load');"


def scenarios(t):
    base = t.base
    shots = t.work / 'shots'
    shots.mkdir(exist_ok=True)
    # run-code wraps the snippet in a call, so BASE must live inside the function.
    head = f"async page => {{ const BASE = {json.dumps(base)}; "

    t.pw('open', 'about:blank', *(['--headed'] if t.headed else []))
    print('article page')
    layout = t.run(head + GOTO_POST + """
      await page.waitForFunction(() => document.querySelector('.live-photo img').complete);
      return await page.evaluate(() => {
        const box = document.querySelector('.live-photo'), img = box.querySelector('img');
        const r = box.getBoundingClientRect(), i = img.getBoundingClientRect();
        const b = box.querySelector('.live-photo__badge').getBoundingClientRect();
        return {sameBox: [r.x, r.y, r.width, r.height].join() === [i.x, i.y, i.width, i.height].join(),
                centred: Math.abs(r.x + r.width / 2 - innerWidth / 2) < 2,
                badge: [Math.round(r.right - b.right), Math.round(b.y - r.y)],
                badgeTag: box.querySelector('.live-photo__badge').tagName,
                src: img.currentSrc, hasSize: !!(img.width && img.getAttribute('height')),
                lazy: img.loading, boxes: document.querySelectorAll('.live-photo').length,
                height: i.height, width: i.width, vh: innerHeight};
      });
    }""")
    t.check('box is exactly the image and centred', layout['sameBox'] and layout['centred'], layout)
    t.check('LIVE button sits top-right', layout['badge'] == [10, 10] and layout['badgeTag'] == 'BUTTON', layout)
    t.check('tall photo is capped at 75% of the screen height', layout['height'] <= min(0.75 * layout['vh'], 640) + 1, layout)
    t.check('capped photo keeps its proportions', abs(layout['width'] / layout['height'] - 1333 / 2000) < 0.01, layout)
    t.check('browser picked a WebP variant from srcset', '/files/_w/' in layout['src'] and layout['src'].endswith('.webp'), layout['src'])
    t.check('image is lazy with intrinsic size', layout['lazy'] == 'lazy' and layout['hasSize'])
    t.check('only the Live Photo is wrapped', layout['boxes'] == 1, layout['boxes'])

    plain = t.run(head + GOTO_POST + """
      await page.waitForFunction(() => [...document.querySelectorAll('.article-body img')].every((i) => i.complete));
      return await page.evaluate(() => [...document.querySelectorAll('.article-body img')]
        .filter((i) => !i.closest('.live-photo')).map((i) => {
          const r = i.getBoundingClientRect();
          return {alt: i.alt, w: r.width, h: r.height, ratio: i.naturalWidth / i.naturalHeight, vh: innerHeight, x: r.x + r.width / 2};
        }));
    """ + "}")
    by_alt = {item['alt']: item for item in plain}
    tall, wide = by_alt['竖图'], by_alt['普通图']
    t.check('an ordinary tall photo is capped too', tall['h'] <= min(0.75 * tall['vh'], 640) + 1, tall)
    t.check('the capped ordinary photo keeps its proportions and stays centred',
            abs(tall['w'] / tall['h'] - 0.5) < 0.01 and abs(tall['x'] - 640) < 2, tall)
    t.check('a wide photo is untouched by the cap', abs(wide['w'] / wide['h'] - 2) < 0.01 and wide['h'] < 540, wide)

    print('playback')
    auto = t.run(head + GOTO_POST + f"""
      const box = page.locator('.live-photo');
      const playing = () => page.evaluate(() => document.querySelector('.live-photo').classList.contains('is-playing'));
      // Only the top of the photo is on screen at load: it must not start yet.
      await page.waitForTimeout(1500);
      const atLoad = await playing();
      // Flicking past it must not start it either.
      await page.evaluate(() => document.querySelector('.live-photo').scrollIntoView({{block: 'center'}}));
      await page.waitForTimeout(150);
      await page.evaluate(() => scrollTo(0, 0));
      await page.waitForTimeout(900);
      const flyBy = await playing();
      // Scrolling it into place and staying there starts it.
      await page.evaluate(() => document.querySelector('.live-photo').scrollIntoView({{block: 'center'}}));
      await page.waitForFunction(() => document.querySelector('.live-photo').classList.contains('is-playing'), null, {{timeout: 8000}});
      const during = await page.evaluate(() => {{
        const box = document.querySelector('.live-photo'), v = box.querySelector('video');
        const r = box.getBoundingClientRect(), vr = v.getBoundingClientRect();
        return {{muted: v.muted, w: v.videoWidth,
                 covers: Math.abs(vr.width - r.width) < 1 && Math.abs(vr.height - r.height) < 1}};
      }});
      await page.waitForTimeout(400);
      await box.screenshot({{path: {json.dumps(str(shots / 'autoplay.png'))}}});
      await page.waitForFunction(() => !document.querySelector('.live-photo').classList.contains('is-playing'), null, {{timeout: 8000}});
      await page.waitForTimeout(1500);
      return {{atLoad, flyBy, during, again: await playing()}};
    }}""")
    t.check('it does not start while only part of it is on screen', not auto['atLoad'], auto)
    t.check('flicking past it does not start it', not auto['flyBy'], auto)
    t.check('scrolled into place, it plays by itself: muted, covering the still', auto['during']['muted'] and auto['during']['covers'], auto)
    t.check('clip is the transcoded 960px one', auto['during']['w'] == 960, auto)
    t.check('it plays only once on its own', not auto['again'], auto)

    manual = t.run(head + GOTO_POST + f"""
      const box = page.locator('.live-photo');
      await box.scrollIntoViewIfNeeded();
      await page.waitForFunction(() => document.querySelector('.live-photo').classList.contains('is-playing'), null, {{timeout: 8000}});
      await page.waitForFunction(() => !document.querySelector('.live-photo').classList.contains('is-playing'), null, {{timeout: 8000}});
      const state = () => page.evaluate(() => document.querySelector('.live-photo').classList.contains('is-playing'));
      const out = {{}};
      await box.hover();
      await page.waitForTimeout(700);
      out.hoverPlays = await state();
      await page.evaluate(async () => {{
        const b = document.querySelector('.live-photo');
        b.dispatchEvent(new Event('touchstart', {{bubbles: true}}));
        await new Promise((r) => setTimeout(r, 700));
        b.dispatchEvent(new Event('touchend', {{bubbles: true}}));
      }});
      out.longPressPlays = await state();
      await page.click('.live-photo__badge');
      await page.waitForFunction(() => document.querySelector('.live-photo').classList.contains('is-playing'), null, {{timeout: 8000}});
      out.buttonPlays = true;
      await page.waitForTimeout(400);
      out.badge = await page.evaluate(() => {{
        const badge = document.querySelector('.live-photo__badge');
        return {{pressed: badge.getAttribute('aria-pressed'), light: getComputedStyle(badge).backgroundColor}};
      }});
      await page.click('.live-photo__badge');
      await page.waitForTimeout(300);
      out.secondClickStops = !(await state());
      out.lightboxOpened = !!(await page.$('.pswp--open'));
      await page.click('.live-photo__badge');
      await page.waitForFunction(() => document.querySelector('.live-photo').classList.contains('is-playing'), null, {{timeout: 8000}});
      await page.waitForFunction(() => !document.querySelector('.live-photo').classList.contains('is-playing'), null, {{timeout: 8000}});
      out.endsByItself = true;
      return out;
    }}""")
    t.check('hover does not play it', not manual['hoverPlays'], manual)
    t.check('long press does not play it', not manual['longPressPlays'], manual)
    t.check('the LIVE button plays it again', manual['buttonPlays'] and manual['badge']['pressed'] == 'true', manual)
    t.check('the button turns light while playing', manual['badge']['light'].startswith('rgba(255, 255, 255'), manual['badge'])
    t.check('a second click stops it', manual['secondClickStops'], manual)
    t.check('using the button does not open the lightbox', not manual['lightboxOpened'], manual)
    t.check('a clip that finishes goes back to the still', manual['endsByItself'])

    reduced = t.run(head + """
      await page.emulateMedia({reducedMotion: 'reduce'});
      """ + GOTO_POST + """
      await page.locator('.live-photo').scrollIntoViewIfNeeded();
      await page.waitForTimeout(1500);
      const auto = await page.evaluate(() => document.querySelector('.live-photo').classList.contains('is-playing'));
      await page.click('.live-photo__badge');
      await page.waitForFunction(() => document.querySelector('.live-photo').classList.contains('is-playing'), null, {timeout: 8000});
      await page.emulateMedia({reducedMotion: 'no-preference'});
      return {auto};
    """ + "}")
    t.check('reduced motion: no automatic play, the button still works', not reduced['auto'], reduced)

    print('lightbox')
    box = t.run(head + GOTO_POST + """
      const stem = await page.evaluate(() => document.querySelector('.live-photo img').src.split('/').pop().split('.')[0]);
      await page.locator('.live-photo img').click();
      await page.waitForSelector('.pswp--open');
      await page.waitForFunction((stem) => [...document.querySelectorAll('img.pswp__img')]
        .some((i) => i.src.includes(stem) && i.naturalWidth > 0), stem);
      return await page.evaluate((stem) => {
        const img = [...document.querySelectorAll('img.pswp__img')].find((i) => i.src.includes(stem));
        return {src: img.src, w: img.naturalWidth};
      }, stem);
    """ + "}")
    t.check('lightbox shows the full-size file, not a variant', '/_w/' not in box['src'] and box['src'].endswith('.jpg') and box['w'] == 1333, box)

    print('admin library')
    admin = t.run(head + f"""
      await page.goto(BASE + '/login');
      await page.fill('input[name=username]', 'admin');
      await page.fill('input[name=password]', {json.dumps(PASSWORD)});
      await page.click('input[type=submit], button[type=submit]');
      await page.goto(BASE + '/admin/images');
      // Hold the request back so the waiting state can be inspected.
      let posts = 0;
      page.on('request', (r) => {{ if (r.method() === 'POST' && r.url().endsWith('/admin/images/upload')) posts += 1; }});
      await page.route('**/admin/images/upload', async (route) => {{ await new Promise((r) => setTimeout(r, 1500)); await route.continue(); }});
      await page.setInputFiles('#image-files', [{json.dumps(str(t.work / 'IMG_7777.HEIC'))}, {json.dumps(str(t.work / 'IMG_7777.MOV'))}]);
      await page.click('.image-upload button[type=submit]');
      await page.waitForTimeout(500);
      const during = await page.evaluate(() => {{
        const status = document.querySelector('[data-upload-status]'), bar = status.querySelector('progress');
        return {{button: document.querySelector('.image-upload button').disabled,
                 label: document.querySelector('.image-upload button').textContent,
                 input: document.querySelector('#image-files').disabled,
                 busy: document.querySelector('.image-upload').getAttribute('aria-busy'),
                 visible: !status.hidden && status.getBoundingClientRect().height > 0,
                 hasBar: !!bar && !bar.hidden, text: status.innerText}};
      }});
      await page.screenshot({{path: {json.dumps(str(shots / 'uploading.png'))}}});
      await page.evaluate(() => document.querySelector('.image-upload').requestSubmit());
      await page.evaluate(() => document.querySelector('.image-upload').requestSubmit());
      await page.waitForSelector('.flash, [role=status]:has-text("已上传")', {{timeout: 15000}});
      await page.waitForSelector('.image-card');
      await page.unroute('**/admin/images/upload');
      await page.screenshot({{path: {json.dumps(str(shots / 'library.png'))}}});
      return await page.evaluate((extra) => ({{
        ...extra,
        flash: document.body.innerText.match(/已上传 \\d+ 张[^\\n]*/)?.[0],
        cards: document.querySelectorAll('.image-card').length,
        live: document.querySelectorAll('.image-card__live').length,
      }}), {{during, posts}});
    }}""")
    d = admin['during']
    t.check('while uploading the button and file field are locked', d['button'] and d['input'] and d['busy'] == 'true' and d['label'] == '上传中…', d)
    t.check('while uploading a status line with a progress bar is visible', d['visible'] and d['hasBar'] and ('上传' in d['text'] or '处理' in d['text']), d)
    t.check('submitting again while it is busy sends nothing more', admin['posts'] == 1, admin['posts'])
    t.check('pair upload reports one image and no failure', admin['flash'] == '已上传 1 张。', admin)
    t.check('both Live Photos are tagged in the library', admin['cards'] == 4 and admin['live'] == 2, admin)
    detail = t.run(head + """
      await page.click('.image-card:has(.image-card__live)');
      await page.waitForSelector('.image-detail__preview video');
      return await page.evaluate(async () => {
        const v = document.querySelector('.image-detail__preview video');
        await new Promise((r) => v.readyState >= 1 ? r() : v.addEventListener('loadedmetadata', r));
        return {controls: v.controls, w: v.videoWidth, dur: Math.round(v.duration)};
      });
    }""")
    t.check('detail page plays the stored clip', detail['controls'] and detail['w'] == 960 and detail['dur'] == 3, detail)


def main():
    if '--seed' in sys.argv:
        seed(sys.argv[sys.argv.index('--seed') + 1])
        return 0
    if not shutil.which('ffmpeg') or not shutil.which('npx'):
        print('ffmpeg and npx (Node) are required', file=sys.stderr)
        return 2

    work = Path(tempfile.mkdtemp(prefix='flog-e2e-'))
    database = f'sqlite:///{work / "e2e.db"}'
    env = {**os.environ, 'DATABASE_URL': database, 'TEST_DATABASE_URL': database,
           'UPLOAD_FOLDER': str(work / 'uploads'),
           'SECRET_KEY': 'e2e-secret-key-e2e-secret-key-1234',
           'FLASK_DEBUG': '0', 'FLASK_APP': 'flog.py'}
    server = None
    runner = None
    try:
        subprocess.run([sys.executable, __file__, '--seed', str(work)], cwd=ROOT,
                       env=env, check=True, stdout=subprocess.DEVNULL)
        port = free_port()
        server = subprocess.Popen(
            [sys.executable, '-m', 'flask', 'run', '--no-reload', '--port', str(port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        base = f'http://127.0.0.1:{port}'
        wait_for(base + '/login')
        runner = Runner(work, base, '--headed' in sys.argv)
        scenarios(runner)
    finally:
        if runner:
            runner.pw('close')
        if server:
            os.killpg(server.pid, signal.SIGTERM)
        if '--keep' in sys.argv:
            print(f'kept {work}')
        else:
            shutil.rmtree(work, ignore_errors=True)
    failed = runner.failures if runner else ['setup']
    print(f"\n{'all checks passed' if not failed else str(len(failed)) + ' failed: ' + ', '.join(failed)}")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
