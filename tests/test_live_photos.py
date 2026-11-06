import io
import json
import subprocess
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from PIL import Image as PILImage

from app import db
from app.admin.images import pair_uploads
from app.content import render_content
from app.live_photos import (VideoError, extract_embedded_video,
                             has_heif_signature, transcode_video)
from app.models import Image
from tests.conftest import login, make_heic, make_image, make_video, needs_ffmpeg

FAKE_MP4 = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom' + b'v' * 500


def post_files(client, *files):
    return client.post('/admin/images/upload', data={
        'images': [(io.BytesIO(data), name) for name, data in files],
    }, content_type='multipart/form-data', follow_redirects=True)


def probe(path):
    out = subprocess.run(
        [shutil.which('ffprobe'), '-v', 'error', '-print_format', 'json',
         '-show_streams', '-show_format', str(path)],
        capture_output=True, check=True).stdout
    return json.loads(out)


def folder(application):
    return Path(application.config['UPLOAD_FOLDER'])


# --- pure helpers ---------------------------------------------------------------

def test_heif_signature_needs_a_known_brand():
    assert has_heif_signature(b'\x00\x00\x00\x1cftypheic\x00\x00\x00\x00')
    assert not has_heif_signature(b'\x00\x00\x00\x1cftypmp42\x00\x00\x00\x00')
    assert not has_heif_signature(b'\x89PNG\r\n\x1a\n' + b'0' * 8)


def test_embedded_video_found_through_micro_video_offset():
    still = make_image('JPEG', (16, 16))
    xmp = (f'<x:xmpmeta GCamera:MicroVideo="1" '
           f'GCamera:MicroVideoOffset="{len(FAKE_MP4)}"/>').encode()

    assert extract_embedded_video(still + xmp + FAKE_MP4) == FAKE_MP4


def test_embedded_video_found_through_the_container_directory():
    still = make_image('JPEG', (16, 16))
    xmp = (
        '<Container:Directory><rdf:Seq>'
        '<rdf:li><Container:Item Item:Mime="image/jpeg" Item:Semantic="Primary" Item:Length="0"/></rdf:li>'
        f'<rdf:li><Container:Item Item:Mime="video/mp4" Item:Semantic="MotionPhoto" Item:Length="{len(FAKE_MP4)}"/></rdf:li>'
        '</rdf:Seq></Container:Directory>').encode()

    assert extract_embedded_video(still + xmp + FAKE_MP4) == FAKE_MP4


def test_no_embedded_video_in_an_ordinary_or_lying_jpeg():
    still = make_image('JPEG', (16, 16))

    assert extract_embedded_video(still) is None
    lying = still + b'GCamera:MicroVideoOffset="999999999"' + FAKE_MP4
    assert extract_embedded_video(lying) is None
    not_mp4 = still + b'GCamera:MicroVideoOffset="20"' + b'x' * 20
    assert extract_embedded_video(not_mp4) is None


def test_pair_uploads_matches_by_base_name_ignoring_case():
    def f(name):
        return SimpleNamespace(filename=name)

    pairs, orphans = pair_uploads([
        f('IMG_1.HEIC'), f('img_1.mov'), f('solo.png'),
        f('lonely.mov'), f('a.jpg'), f('a.png'), f('a.mp4')])

    assert [(s.filename, v and v.filename) for s, v in pairs] == [
        ('IMG_1.HEIC', 'img_1.mov'), ('solo.png', None),
        ('a.jpg', None), ('a.png', None)]
    assert sorted(o.filename for o in orphans) == ['a.mp4', 'lonely.mov']


# --- ffmpeg ------------------------------------------------------------------------

@needs_ffmpeg
def test_transcode_makes_a_small_silent_h264_mp4(application, tmp_path):
    source = make_video(tmp_path, '.mov', size='1920x1080', seconds=2)
    target = tmp_path / 'out.mp4'

    with application.app_context():
        target.write_bytes(transcode_video(source))

    info = probe(target)
    streams = info['streams']
    assert [s['codec_type'] for s in streams] == ['video']
    assert streams[0]['codec_name'] == 'h264'
    assert streams[0]['pix_fmt'] == 'yuv420p'
    assert (streams[0]['width'], streams[0]['height']) == (960, 540)


@needs_ffmpeg
def test_transcode_rejects_garbage(application):
    with application.app_context(), pytest.raises(VideoError):
        transcode_video(FAKE_MP4)


def test_transcode_reports_a_missing_ffmpeg(application, monkeypatch):
    from app.live_photos import FfmpegMissing
    monkeypatch.setattr('app.live_photos.shutil.which', lambda name: None)
    application.config['FFMPEG'] = None

    with application.app_context(), pytest.raises(FfmpegMissing):
        transcode_video(FAKE_MP4)


# --- HEIC stills ----------------------------------------------------------------------

def test_heic_upload_is_stored_as_a_jpeg(client, application, users):
    login(client, 'author')

    response = client.post('/upload', data={
        'post': (io.BytesIO(make_heic()), 'IMG_0001.HEIC')},
        content_type='multipart/form-data')

    assert response.status_code == 200
    url = response.get_json()['url']
    assert url.endswith('.jpg')
    with PILImage.open(folder(application) / Path(url).name) as stored:
        assert stored.format == 'JPEG' and stored.size == (64, 32)
    with application.app_context():
        image = db.session.scalar(sa.select(Image))
        assert (image.width, image.height) == (64, 32)
        assert image.original_name == 'IMG_0001.HEIC'


def test_heic_extension_needs_a_heic_signature(client, application, users):
    login(client, 'author')

    response = client.post('/upload', data={
        'post': (io.BytesIO(make_image()), 'fake.heic')},
        content_type='multipart/form-data')

    assert response.status_code == 400


# --- uploading a pair --------------------------------------------------------------------

@needs_ffmpeg
def test_still_and_clip_upload_as_one_live_photo(client, application, users, tmp_path):
    login(client, 'author')
    clip = make_video(tmp_path)

    response = post_files(client, ('IMG_0001.HEIC', make_heic()),
                          ('IMG_0001.MOV', clip))

    html = response.get_data(as_text=True)
    assert '已上传 1 张' in html and '张失败' not in html
    with application.app_context():
        image = db.session.scalar(sa.select(Image))
        assert image.filename.endswith('.jpg')
        assert image.video_filename == Path(image.filename).stem + '.mp4'
        assert probe(folder(application) / image.video_filename)[
            'streams'][0]['codec_name'] == 'h264'
        assert db.session.scalar(sa.select(sa.func.count(Image.id))) == 1


@needs_ffmpeg
def test_clip_is_served_with_range_support_and_long_cache(
        client, application, users, tmp_path):
    login(client, 'author')
    post_files(client, ('a.jpg', make_image('JPEG', (64, 48))),
               ('a.mov', make_video(tmp_path)))
    with application.app_context():
        name = db.session.scalar(sa.select(Image.video_filename))

    whole = client.get(f'/files/{name}')
    part = client.get(f'/files/{name}', headers={'Range': 'bytes=0-99'})

    assert whole.status_code == 200 and whole.mimetype == 'video/mp4'
    assert 'immutable' in whole.headers['Cache-Control']
    assert part.status_code == 206 and len(part.data) == 100


def test_a_clip_without_a_still_is_reported(client, application, users):
    login(client, 'author')

    html = post_files(client, ('lonely.mov', FAKE_MP4)).get_data(as_text=True)

    assert '已上传 0 张' in html and '缺少同名的图片' in html
    with application.app_context():
        assert db.session.scalar(sa.select(sa.func.count(Image.id))) == 0


def test_a_broken_clip_fails_the_pair_without_leaving_files(
        client, application, users):
    login(client, 'author')

    html = post_files(client, ('a.png', make_image()),
                      ('a.mov', FAKE_MP4)).get_data(as_text=True)

    assert '已上传 0 张' in html and 'a.png' in html
    assert not any(folder(application).glob('*'))


def test_a_clip_that_is_not_a_video_is_refused(client, application, users):
    login(client, 'author')

    html = post_files(client, ('a.png', make_image()),
                      ('a.mov', b'plain text, not a video')).get_data(as_text=True)

    assert 'Live Photo 的视频无法识别' in html


def test_missing_ffmpeg_fails_the_pair_with_a_clear_message(
        client, application, users, monkeypatch):
    monkeypatch.setattr('app.live_photos.shutil.which', lambda name: None)
    application.config['FFMPEG'] = None
    login(client, 'author')

    html = post_files(client, ('a.png', make_image()),
                      ('a.mov', FAKE_MP4)).get_data(as_text=True)

    assert '未安装 ffmpeg' in html
    assert not any(folder(application).glob('*'))


@needs_ffmpeg
def test_android_motion_photo_keeps_its_embedded_clip(
        client, application, users, tmp_path):
    clip = make_video(tmp_path, '.mp4')
    still = make_image('JPEG', (64, 48))
    xmp = f'<x GCamera:MicroVideoOffset="{len(clip)}"/>'.encode()
    login(client, 'author')

    response = client.post('/upload', data={
        'post': (io.BytesIO(still + xmp + clip), 'PXL_1.jpg')},
        content_type='multipart/form-data')

    assert response.status_code == 200
    with application.app_context():
        image = db.session.scalar(sa.select(Image))
        assert image.video_filename
        assert (folder(application) / image.video_filename).is_file()
        # the uploaded still no longer carries the clip
        assert b'ftyp' not in (folder(application) / image.filename).read_bytes()


def test_motion_photo_without_ffmpeg_still_saves_the_photo(
        client, application, users, monkeypatch):
    monkeypatch.setattr('app.live_photos.shutil.which', lambda name: None)
    application.config['FFMPEG'] = None
    xmp = f'<x GCamera:MicroVideoOffset="{len(FAKE_MP4)}"/>'.encode()
    login(client, 'author')

    response = client.post('/upload', data={
        'post': (io.BytesIO(make_image('JPEG', (64, 48)) + xmp + FAKE_MP4), 'a.jpg')},
        content_type='multipart/form-data')

    assert response.status_code == 200
    with application.app_context():
        assert db.session.scalar(sa.select(Image)).video_filename is None


# --- management --------------------------------------------------------------------------

def add_live(application, stem='a' * 32):
    folder(application).mkdir(parents=True, exist_ok=True)
    (folder(application) / f'{stem}.jpg').write_bytes(make_image('JPEG', (64, 48)))
    (folder(application) / f'{stem}.mp4').write_bytes(FAKE_MP4)
    with application.app_context():
        image = Image(filename=f'{stem}.jpg', original_name='o', title='t',
                      size=1, width=64, height=48, video_filename=f'{stem}.mp4')
        db.session.add(image)
        db.session.commit()
        return image.id


def test_library_marks_live_photos_and_detail_plays_the_clip(
        client, application, users):
    image_id = add_live(application)
    login(client, 'admin')

    assert 'image-card__live' in client.get('/admin/images').get_data(as_text=True)
    detail = client.get(f'/admin/images/{image_id}').get_data(as_text=True)
    assert f'<video src="/files/{"a" * 32}.mp4"' in detail


def test_deleting_a_live_photo_removes_the_clip_too(client, application, users):
    image_id = add_live(application)
    login(client, 'admin')

    client.post(f'/admin/images/{image_id}/delete')

    assert not list(folder(application).glob('*'))


# --- rendering ---------------------------------------------------------------------------

def test_live_photo_is_wrapped_so_the_script_can_play_it(application):
    add_live(application)
    stem = 'a' * 32

    with application.test_request_context():
        rendered = render_content(f'![sea](/files/{stem}.jpg)', 'markdown')

    assert (f'<span class="live-photo" data-live-video="/files/{stem}.mp4">'
            f'<img') in rendered
    assert ('<button type="button" class="live-photo__badge" '
            'aria-label="播放 Live Photo">LIVE</button></span>') in rendered
    assert 'width="64"' in rendered and 'loading="lazy"' in rendered


def test_text_around_a_live_photo_survives_the_wrapping(application):
    add_live(application)
    stem = 'a' * 32

    with application.test_request_context():
        rendered = render_content(
            f'<p>before <img src="/files/{stem}.jpg"> after</p>', 'html')

    assert rendered.startswith('<p>before <span class="live-photo"')
    assert rendered.endswith('</span> after</p>')


def test_ordinary_and_external_images_are_not_wrapped(application):
    add_live(application)
    stem = 'a' * 32

    with application.test_request_context():
        rendered = render_content(
            f'![x](https://example.com/files/{stem}.jpg) ![y](/files/{"b" * 32}.png)',
            'markdown')

    assert 'live-photo' not in rendered


def test_feed_and_search_text_stay_plain(application):
    add_live(application)

    with application.test_request_context():
        rendered = render_content(f'![sea](/files/{"a" * 32}.jpg)', 'markdown',
                                  images=False)

    assert 'live-photo' not in rendered


def test_public_post_page_plays_live_photos(client, application, users):
    from app.models import Post
    stem = 'a' * 32
    add_live(application, stem)
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body, post.body_format = f'![sea](/files/{stem}.jpg)', 'markdown'
        db.session.commit()

    page = client.get(f'/post/{users["post"]}').get_data(as_text=True)

    assert f'data-live-video="/files/{stem}.mp4"' in page
    assert '/static/live-photo.js' in page
