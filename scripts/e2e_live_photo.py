#!/usr/bin/env python
"""Drive a real browser through the Live Photo and image-delivery features.

Seeds a throw-away database and upload folder, starts the app on a free port
and checks, in Chromium via Playwright CLI: layout, responsive variants,
hover / long-press playback, the lightbox and the admin upload form.

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
        live = upload(make_heic((2400, 1600), 'steelblue'), 'IMG_0001.HEIC', admin,
                      video=FileStorage(io.BytesIO(clip), filename='IMG_0001.MOV'))
        plain = upload(make_image('JPEG', (2400, 1200), photo=True), 'plain.jpg', admin)
        body = (f'开头。\n\n![海边](/files/{live.filename})\n\n中间。\n\n'
                f'![普通图](/files/{plain.filename})\n\n结尾。')
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
                badge: [Math.round(b.x - r.x), Math.round(b.y - r.y)],
                src: img.currentSrc, hasSize: !!(img.width && img.getAttribute('height')),
                lazy: img.loading,
                boxes: document.querySelectorAll('.live-photo').length};
      });
    }""")
    t.check('box is exactly the image and centred', layout['sameBox'] and layout['centred'], layout)
    t.check('LIVE badge sits top-left', layout['badge'] == [10, 10], layout['badge'])
    t.check('browser picked a WebP variant from srcset', '/files/_w/' in layout['src'] and layout['src'].endswith('.webp'), layout['src'])
    t.check('image is lazy with intrinsic size', layout['lazy'] == 'lazy' and layout['hasSize'])
    t.check('only the Live Photo is wrapped', layout['boxes'] == 1, layout['boxes'])

    print('playback')
    hover = t.run(head + GOTO_POST + f"""
      const box = page.locator('.live-photo');
      await box.scrollIntoViewIfNeeded();
      await box.hover();
      await page.waitForFunction(() => document.querySelector('.live-photo').classList.contains('is-playing'), null, {{timeout: 8000}});
      await page.waitForTimeout(400);   // let the 0.2 s fade finish
      const playing = await page.evaluate(() => {{
        const box = document.querySelector('.live-photo'), v = box.querySelector('video');
        const badge = box.querySelector('.live-photo__badge');
        const z = (el) => Number(getComputedStyle(el).zIndex) || 0;
        const r = box.getBoundingClientRect(), vr = v.getBoundingClientRect();
        return {{muted: v.muted, opacity: getComputedStyle(v).opacity, w: v.videoWidth,
                 covers: Math.abs(vr.width - r.width) < 1 && Math.abs(vr.height - r.height) < 1,
                 badgeOnTop: z(badge) > z(v) && Number(getComputedStyle(badge).opacity) > 0.3}};
      }});
      await box.screenshot({{path: {json.dumps(str(shots / 'playing.png'))}}});
      await page.mouse.move(5, 5);
      await page.waitForTimeout(500);
      const after = await page.evaluate(() => {{
        const box = document.querySelector('.live-photo'), v = box.querySelector('video');
        return {{playing: box.classList.contains('is-playing'), paused: v.paused, opacity: getComputedStyle(v).opacity}};
      }});
      return {{playing, after}};
    }}""")
    t.check('hover plays a muted clip over the still', hover['playing']['muted'] and hover['playing']['opacity'] == '1' and hover['playing']['covers'], hover['playing'])
    t.check('clip is the transcoded 960px one', hover['playing']['w'] == 960, hover['playing'])
    t.check('LIVE badge stays visible while playing', hover['playing']['badgeOnTop'])
    t.check('leaving stops and hides the clip', not hover['after']['playing'] and hover['after']['paused'] and hover['after']['opacity'] == '0', hover['after'])

    touch = t.run(head + GOTO_POST + """
      return await page.evaluate(async () => {
        const box = document.querySelector('.live-photo'), img = box.querySelector('img');
        const fire = (name) => box.dispatchEvent(new Event(name, {bubbles: true}));
        const wait = (ms) => new Promise((r) => setTimeout(r, ms));
        const click = () => { let hit = false; const f = () => { hit = true; };
          img.addEventListener('click', f, {once: true});
          img.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
          img.removeEventListener('click', f); return hit; };
        const out = {};
        fire('touchstart'); await wait(120); out.early = box.classList.contains('is-playing');
        await wait(600); out.held = box.classList.contains('is-playing');
        fire('touchend'); out.released = !box.classList.contains('is-playing');
        out.clickSwallowed = !click();
        await wait(800); out.laterClickPasses = click();
        fire('touchstart'); fire('touchmove'); await wait(600);
        out.scrollCancels = !box.classList.contains('is-playing'); fire('touchend');
        return out;
      });
    }""")
    t.check('long press plays after a delay, not at once', not touch['early'] and touch['held'], touch)
    t.check('releasing stops it', touch['released'])
    t.check('releasing does not open the lightbox, a later tap can', touch['clickSwallowed'] and touch['laterClickPasses'], touch)
    t.check('scrolling cancels a press', touch['scrollCancels'])

    print('lightbox')
    box = t.run(head + GOTO_POST + """
      await page.locator('.live-photo img').click();
      await page.waitForSelector('.pswp--open');
      await page.waitForFunction(() => document.querySelector('.pswp__img') && document.querySelector('.pswp__img').naturalWidth > 0);
      return await page.evaluate(() => {
        const img = document.querySelector('.pswp__img');
        return {src: img.src, w: img.naturalWidth};
      });
    }""")
    t.check('lightbox shows the full-size file, not a variant', '/_w/' not in box['src'] and box['src'].endswith('.jpg') and box['w'] == 2000, box)

    print('admin library')
    admin = t.run(head + f"""
      await page.goto(BASE + '/login');
      await page.fill('input[name=username]', 'admin');
      await page.fill('input[name=password]', {json.dumps(PASSWORD)});
      await page.click('input[type=submit], button[type=submit]');
      await page.goto(BASE + '/admin/images');
      await page.setInputFiles('#image-files', [{json.dumps(str(t.work / 'IMG_7777.HEIC'))}, {json.dumps(str(t.work / 'IMG_7777.MOV'))}]);
      await page.click('.image-upload button[type=submit]');
      await page.waitForSelector('.image-card');
      await page.screenshot({{path: {json.dumps(str(shots / 'library.png'))}}});
      return await page.evaluate(() => ({{
        flash: document.body.innerText.match(/已上传 \\d+ 张[^\\n]*/)?.[0],
        cards: document.querySelectorAll('.image-card').length,
        live: document.querySelectorAll('.image-card__live').length,
      }}));
    }}""")
    t.check('pair upload reports one image and no failure', admin['flash'] == '已上传 1 张。', admin)
    t.check('both Live Photos are tagged in the library', admin['cards'] == 3 and admin['live'] == 2, admin)
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
