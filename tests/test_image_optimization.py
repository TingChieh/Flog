import io
from pathlib import Path

import pytest
import sqlalchemy as sa
from PIL import Image as PILImage

from app import db
from app.content import render_article, render_content
from app.images import (MAX_EDGE, ImageUploadError, make_variant,
                        optimize_existing_images, process_image, read_dimensions, sync_untracked_images,
                        thumbnail_url, variant_srcset)
from app.models import Image
from tests.conftest import login, make_image


def decode(data):
    return PILImage.open(io.BytesIO(data))


def upload(client, data, name='photo.png'):
    return client.post('/upload', data={'post': (io.BytesIO(data), name)},
                       content_type='multipart/form-data')


def stored(application, url):
    return (Path(application.config['UPLOAD_FOLDER']) / Path(url).name)


# --- process_image -------------------------------------------------------------

def test_large_images_are_shrunk_to_the_max_edge():
    result = process_image(make_image('JPEG', (3000, 1500)), '.jpg')

    assert (result.width, result.height) == (MAX_EDGE, MAX_EDGE // 2)
    assert decode(result.data).size == (result.width, result.height)
    assert result.extension == '.jpg'


def test_small_images_are_never_upscaled():
    result = process_image(make_image('JPEG', (40, 30)), '.jpeg')

    assert (result.width, result.height) == (40, 30)
    assert result.extension == '.jpeg'


def test_jpeg_exif_is_stripped_and_orientation_applied():
    source = PILImage.new('RGB', (40, 20), 'red')
    exif = source.getexif()
    exif[274] = 6                       # rotate 90° when displayed
    exif[0x010F] = 'SecretCamera'
    buffer = io.BytesIO()
    source.save(buffer, 'JPEG', exif=exif)

    result = process_image(buffer.getvalue(), '.jpg')

    assert (result.width, result.height) == (20, 40)
    assert not decode(result.data).getexif()


def test_cmyk_jpeg_is_converted_for_the_web():
    result = process_image(make_image('JPEG', (16, 16), mode='CMYK'), '.jpg')

    assert decode(result.data).mode == 'RGB'


def test_big_png_is_recompressed_and_keeps_transparency():
    raw = make_image('PNG', (2400, 600), mode='RGBA')

    result = process_image(raw, '.png')

    assert result.extension == '.png'
    assert (result.width, result.height) == (2000, 500)
    assert decode(result.data).mode == 'RGBA'


def test_photo_like_png_is_stored_as_a_much_smaller_jpeg():
    raw = make_image('PNG', (800, 600), photo=True)
    assert len(raw) > 300 * 1024

    result = process_image(raw, '.png')

    assert result.extension == '.jpg'
    assert decode(result.data).format == 'JPEG'
    assert len(result.data) < len(raw) / 2


def test_flat_png_stays_png():
    result = process_image(make_image('PNG', (1200, 800)), '.png')

    assert result.extension == '.png'
    assert decode(result.data).format == 'PNG'


def test_png_with_alpha_never_becomes_a_jpeg():
    result = process_image(
        make_image('PNG', (800, 600), mode='RGBA', noise=True), '.png')

    assert result.extension == '.png'


def test_png_that_does_not_shrink_is_kept_byte_for_byte():
    raw = make_image('PNG', (8, 8), optimize=True)

    assert process_image(raw, '.png').data == raw


def test_gif_and_animated_images_are_left_untouched():
    frames = [PILImage.new('RGB', (10, 10), color) for color in ('red', 'blue')]
    buffer = io.BytesIO()
    frames[0].save(buffer, 'GIF', save_all=True, append_images=frames[1:])
    gif = buffer.getvalue()
    assert process_image(gif, '.gif').data == gif

    buffer = io.BytesIO()
    frames[0].save(buffer, 'PNG', save_all=True, append_images=frames[1:])
    apng = buffer.getvalue()
    assert process_image(apng, '.png').data == apng


@pytest.mark.parametrize('raw, extension', [
    (b'\x89PNG\r\n\x1a\n' + b'0' * 20, '.png'),
    (b'\xff\xd8\xff\xe0' + b'0' * 20, '.jpg'),
    (make_image('PNG', (400, 300), noise=True)[:5000], '.png'),
])
def test_undecodable_bytes_are_rejected(raw, extension):
    with pytest.raises(ImageUploadError, match='Image only!'):
        process_image(raw, extension)


def test_decompression_bombs_are_rejected(monkeypatch):
    monkeypatch.setattr('app.images.MAX_PIXELS', 100)

    with pytest.raises(ImageUploadError):
        process_image(make_image('PNG', (20, 20)), '.png')


# --- upload endpoint -------------------------------------------------------------

def test_upload_stores_the_compressed_file_and_its_dimensions(
        client, application, users):
    login(client, 'author')
    raw = make_image('JPEG', (3000, 2000), noise=True)

    response = upload(client, raw, 'IMG_0001.JPG')

    assert response.status_code == 200
    url = response.get_json()['url']
    data = stored(application, url).read_bytes()
    assert len(data) < len(raw)
    with application.app_context():
        image = db.session.scalar(sa.select(Image))
        assert (image.width, image.height) == (2000, 1333)
        assert image.size == len(data)
        assert image.original_name == 'IMG_0001.JPG'


def test_upload_of_a_photo_png_changes_the_extension_in_the_url(
        client, application, users):
    login(client, 'author')

    response = upload(client, make_image('PNG', (800, 600), photo=True), 'shot.png')

    url = response.get_json()['url']
    assert url.endswith('.jpg')
    with application.app_context():
        assert db.session.scalar(sa.select(Image)).filename == Path(url).name


def test_upload_rejects_a_signature_only_fake(client, application, users):
    login(client, 'author')

    response = upload(client, b'\x89PNG\r\n\x1a\n' + b'0' * 20)

    assert response.status_code == 400
    assert response.get_json()['error']['message'] == 'Image only!'
    assert not list(Path(application.config['UPLOAD_FOLDER']).glob('*'))


def test_sync_records_dimensions_of_untracked_files(application):
    folder = Path(application.config['UPLOAD_FOLDER'])
    folder.mkdir(parents=True)
    (folder / f'{"a" * 32}.png').write_bytes(make_image('PNG', (30, 20)))
    (folder / f'{"b" * 32}.png').write_bytes(b'garbage')

    with application.app_context():
        assert sync_untracked_images() == 2
        rows = {row.filename[0]: (row.width, row.height)
                for row in db.session.scalars(sa.select(Image))}
    assert rows == {'a': (30, 20), 'b': (None, None)}
    assert read_dimensions(folder / f'{"a" * 32}.png') == (30, 20)


# --- delivery --------------------------------------------------------------------

def test_uploaded_files_are_cached_for_a_year_and_immutable(
        client, application, users):
    login(client, 'author')
    url = upload(client, make_image()).get_json()['url']

    response = client.get(url)

    assert response.status_code == 200
    cache = response.headers['Cache-Control']
    assert 'public' in cache and 'max-age=31536000' in cache
    assert 'immutable' in cache


# --- rendered markup -------------------------------------------------------------

def add_image(application, name, width=640, height=480):
    with application.app_context():
        db.session.add(Image(filename=name, original_name=name, title=name,
                             size=1, width=width, height=height))
        db.session.commit()


def test_rendered_images_are_lazy_and_get_their_pixel_size(application):
    name = f'{"c" * 32}.jpg'
    add_image(application, name)

    with application.test_request_context():
        markdown = render_content(f'![cat](/files/{name})', 'markdown')
        article, _ = render_article(f'![cat](/files/{name})', 'markdown')
        legacy = render_content(f'<img src="/files/{name}" alt="cat">', 'html')

    for rendered in (markdown, article, legacy):
        assert 'loading="lazy"' in rendered
        assert 'decoding="async"' in rendered
        assert 'width="640"' in rendered and 'height="480"' in rendered
        assert 'style="--w:640;--h:480"' in rendered


def test_unknown_and_external_images_are_lazy_without_a_size(application):
    unknown = f'{"d" * 32}.png'

    with application.test_request_context():
        rendered = render_content(
            f'![a](/files/{unknown}) ![b](https://example.com/x.png)', 'markdown')

    assert rendered.count('loading="lazy"') == 2
    assert 'width=' not in rendered and 'height=' not in rendered
    assert '--w' not in rendered


def test_sizes_the_author_wrote_are_not_overridden(application):
    name = f'{"e" * 32}.png'
    add_image(application, name)

    with application.test_request_context():
        rendered = render_content(
            f'<img src="/files/{name}" width="100">', 'html')

    assert 'width="100"' in rendered and 'height=' not in rendered
    assert '--w' not in rendered


def test_stylesheet_reserves_the_final_box_and_fades_photos_in():
    css = Path('app/static/style.css').read_text()

    assert 'aspect-ratio: var(--w) / var(--h);' in css
    assert 'calc(var(--max-h) * var(--w) / var(--h))' in css
    assert '.live-photo[style*="--w"]' in css
    assert 'img[data-loading]' in css and '@keyframes image-in' in css


def test_search_and_feed_text_skip_the_image_pass(application):
    with application.test_request_context():
        rendered = render_content('![a](/files/x.png)', 'markdown', images=False)

    assert 'loading' not in rendered


# --- variants ----------------------------------------------------------------------

STEM = 'ab' * 16


def put_upload(application, data, extension='.jpg', stem=STEM):
    folder = Path(application.config['UPLOAD_FOLDER'])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{stem}{extension}').write_bytes(data)
    return folder


def test_variant_is_a_resized_webp_made_once(application):
    folder = put_upload(application, make_image('JPEG', (2000, 1000), photo=True))

    with application.app_context():
        path = make_variant(STEM, 800)
        modified = path.stat().st_mtime_ns
        assert make_variant(STEM, 800) == path

    assert path == folder / '_w' / '800' / f'{STEM}.webp'
    assert path.stat().st_mtime_ns == modified
    with decode(path.read_bytes()) as variant:
        assert variant.format == 'WEBP' and variant.size == (800, 400)
    assert not list(path.parent.glob('*.tmp'))


def test_variant_keeps_transparency(application):
    image = PILImage.new('RGBA', (1000, 500), (30, 120, 200, 0))
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    put_upload(application, buffer.getvalue(), '.png')

    with application.app_context():
        path = make_variant(STEM, 480)

    assert decode(path.read_bytes()).mode == 'RGBA'


@pytest.mark.parametrize('stem, width', [
    (STEM, 777),                 # not an offered width
    (STEM, 1600),                # not smaller than the 1000 px original
    ('c' * 32, 480),             # no such upload
    ('../' + STEM, 480),         # not a stored name
])
def test_variant_refuses_bad_requests(application, stem, width):
    put_upload(application, make_image('JPEG', (1000, 500)))

    with application.app_context():
        assert make_variant(stem, width) is None


def test_gifs_have_no_variants(application):
    put_upload(application, make_image('GIF', (1000, 500)), '.gif')

    with application.app_context():
        assert make_variant(STEM, 480) is None


def test_variant_route_serves_and_caches(client, application):
    put_upload(application, make_image('JPEG', (1000, 500)))

    response = client.get(f'/files/_w/480/{STEM}.webp')

    assert response.status_code == 200
    assert response.mimetype == 'image/webp'
    assert 'immutable' in response.headers['Cache-Control']
    assert decode(response.data).size == (480, 240)


@pytest.mark.parametrize('path', [
    f'/files/_w/777/{STEM}.webp',
    f'/files/_w/1600/{STEM}.webp',
    f'/files/_w/480/{"c" * 32}.webp',
    '/files/_w/480/not-a-name.webp',
])
def test_variant_route_404s_for_anything_else(client, application, path):
    put_upload(application, make_image('JPEG', (1000, 500)))

    assert client.get(path).status_code == 404


def test_variant_srcset_lists_smaller_copies_then_the_original():
    name = f'{STEM}.jpg'

    assert variant_srcset(name, f'/files/{name}', 1000) == (
        f'/files/_w/480/{STEM}.webp 480w, /files/_w/800/{STEM}.webp 800w, '
        f'/files/{name} 1000w')
    assert variant_srcset(name, f'/files/{name}', 480) == ''
    assert variant_srcset(f'{STEM}.gif', f'/files/{STEM}.gif', 5000) == ''


def test_rendered_images_get_a_srcset_when_variants_exist(application):
    name = f'{STEM}.jpg'
    add_image(application, name, width=1000, height=500)
    small = f'{"f" * 32}.jpg'
    add_image(application, small, width=300, height=200)

    with application.test_request_context():
        rendered = render_content(
            f'![a](/files/{name}) ![b](/files/{small}) '
            f'![c](https://example.com/files/{name})', 'markdown')

    assert rendered.count('srcset=') == 1
    assert f'/files/_w/480/{STEM}.webp 480w' in rendered
    assert f'/files/{name} 1000w' in rendered
    assert 'sizes="(max-width: 760px) 100vw, 760px"' in rendered


def test_thumbnail_url_prefers_a_variant_only_when_it_exists(application):
    with application.test_request_context():
        big = Image(filename=f'{STEM}.jpg', width=1000, height=500)
        small = Image(filename=f'{STEM}.jpg', width=300, height=200)
        legacy = Image(filename=f'{STEM}.jpg')
        gif = Image(filename=f'{STEM}.gif', width=1000, height=500)

        assert thumbnail_url(big) == f'/files/_w/480/{STEM}.webp'
        assert thumbnail_url(small) == f'/files/{STEM}.jpg'
        assert thumbnail_url(legacy) == f'/files/{STEM}.jpg'
        assert thumbnail_url(gif) == f'/files/{STEM}.gif'


def test_deleting_an_image_removes_its_variants(client, application, users):
    login(client, 'author')
    url = upload(client, make_image('JPEG', (1000, 500), photo=True),
                 'a.jpg').get_json()['url']
    assert client.get(url.replace('/files/', '/files/_w/480/').replace('.jpg', '.webp')
                      ).status_code == 200
    variant = Path(application.config['UPLOAD_FOLDER']) / '_w' / '480' / (
        Path(url).stem + '.webp')
    assert variant.is_file()
    with application.app_context():
        image_id = db.session.scalar(sa.select(Image.id))

    client.post(f'/admin/images/{image_id}/delete')

    assert not variant.exists() and not stored(application, url).exists()


def test_admin_library_and_picker_use_thumbnails(client, application, users):
    login(client, 'author')
    url = upload(client, make_image('JPEG', (1000, 500), photo=True),
                 'a.jpg').get_json()['url']
    thumb = url.replace('/files/', '/files/_w/480/').replace('.jpg', '.webp')

    assert thumb in client.get('/admin/images').get_data(as_text=True)
    assert client.get('/admin/images/picker').get_json()['images'][0]['thumb'] == thumb


# --- backfilling older uploads -----------------------------------------------------

def add_row(application, data, extension='.jpg', stem=STEM, **fields):
    put_upload(application, data, extension, stem)
    with application.app_context():
        db.session.add(Image(filename=f'{stem}{extension}', original_name='o',
                             title='t', size=len(data), **fields))
        db.session.commit()


def test_optimize_fills_in_missing_dimensions_and_registers_strays(application):
    add_row(application, make_image('JPEG', (300, 200)))
    put_upload(application, make_image('PNG', (30, 20)), '.png', 'c' * 32)
    with application.app_context():
        db.session.add(Image(filename=f'{"d" * 32}.png', original_name='gone',
                             title='gone', size=1))
        db.session.commit()

        stats = optimize_existing_images()

        assert (stats.untracked, stats.dimensions, stats.recompressed,
                stats.missing) == (1, 1, 0, 1)
        sizes = {row.filename[0]: (row.width, row.height)
                 for row in db.session.scalars(sa.select(Image))}
    assert sizes == {'a': (300, 200), 'c': (30, 20), 'd': (None, None)}


def test_optimize_leaves_files_alone_without_recompress(application):
    raw = make_image('JPEG', (3000, 2000), photo=True)
    add_row(application, raw)

    with application.app_context():
        optimize_existing_images()

    assert (Path(application.config['UPLOAD_FOLDER']) / f'{STEM}.jpg'
            ).read_bytes() == raw


def test_recompress_shrinks_in_place_keeping_name_and_format(application):
    raw = make_image('JPEG', (3000, 2000), photo=True, quality=95)
    add_row(application, raw)
    variant = Path(application.config['UPLOAD_FOLDER']) / '_w' / '480' / f'{STEM}.webp'
    variant.parent.mkdir(parents=True)
    variant.write_bytes(b'stale')

    with application.app_context():
        stats = optimize_existing_images(recompress=True)
        row = db.session.scalar(sa.select(Image))
        stored_bytes = (Path(application.config['UPLOAD_FOLDER'])
                        / f'{STEM}.jpg').read_bytes()

    assert stats.recompressed == 1 and stats.saved_bytes == len(raw) - len(stored_bytes)
    assert decode(stored_bytes).size == (2000, 1333)
    assert (row.size, row.width, row.height) == (len(stored_bytes), 2000, 1333)
    assert not variant.exists()


def test_recompress_never_changes_the_extension(application):
    add_row(application, make_image('PNG', (800, 600), photo=True), '.png')

    with application.app_context():
        optimize_existing_images(recompress=True)
        row = db.session.scalar(sa.select(Image))

    assert row.filename.endswith('.png')
    assert decode((Path(application.config['UPLOAD_FOLDER']) / row.filename
                   ).read_bytes()).format == 'PNG'


def test_recompress_skips_files_that_would_barely_shrink(application):
    raw = process_image(make_image('JPEG', (400, 300), photo=True), '.jpg').data
    add_row(application, raw)

    with application.app_context():
        stats = optimize_existing_images(recompress=True)

    assert stats.recompressed == 0


def test_cli_command_reports_what_it_did(application):
    add_row(application, make_image('JPEG', (300, 200)))

    result = application.test_cli_runner().invoke(args=['images', 'optimize'])

    assert result.exit_code == 0
    assert 'recorded sizes for 1' in result.output
