"""Uploaded images: validation, compression, storage and the database records."""
import io
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

import sqlalchemy as sa
from flask import current_app, url_for
from PIL import Image as PILImage, ImageOps
from werkzeug.utils import secure_filename

from app import db
from app.models import Image, Page, Post, PostDraft


IMAGE_NAME_RE = re.compile(r'^[0-9a-f]{32}\.(?:png|jpe?g|gif)$')
USAGE_RE = re.compile(r'/files/([0-9a-f]{32}\.(?:png|jpe?g|gif))')
ALLOWED_SIGNATURES = {
    '.gif': (b'GIF87a', b'GIF89a'),
    '.jpg': (b'\xff\xd8\xff',),
    '.jpeg': (b'\xff\xd8\xff',),
    '.png': (b'\x89PNG\r\n\x1a\n',),
}


# Uploads are shrunk to fit this box and re-encoded; nothing is ever upscaled.
MAX_EDGE = 2000
# Refuse to decode anything bigger than this (decompression-bomb guard).
MAX_PIXELS = 100_000_000
JPEG_QUALITY = 82
# A PNG at least this big with this many colours is a photo saved losslessly.
PHOTO_PNG_MIN_BYTES = 300 * 1024
PHOTO_COLOR_LIMIT = 65536
# ...and is stored as a JPEG only when that is at most this fraction of the PNG.
PHOTO_JPEG_MAX_RATIO = 0.5
# Resized copies are made on first request under <uploads>/_w/<width>/<stem>.webp
# (the path Caddy can serve straight from disk). Only these widths exist, so
# the cache cannot be grown by asking for arbitrary sizes.
VARIANT_WIDTHS = (480, 800, 1200, 1600)
VARIANT_QUALITY = 80
VARIANT_FOLDER = '_w'
VARIANT_SOURCE_EXTENSIONS = ('.png', '.jpg', '.jpeg')
STEM_RE = re.compile(r'^[0-9a-f]{32}$')
# Layout width of the article column; tells the browser which candidate to fetch.
VARIANT_SIZES = '(max-width: 760px) 100vw, 760px'
DECODE_ERRORS = (OSError, ValueError, PILImage.DecompressionBombError)


class ImageUploadError(ValueError):
    pass


class Processed(NamedTuple):
    data: bytes
    extension: str
    width: int
    height: int


def upload_folder():
    return Path(current_app.config['UPLOAD_FOLDER'])


def _encode_jpeg(image, icc_profile):
    if image.mode not in ('RGB', 'L'):
        image = image.convert('RGB')
    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=JPEG_QUALITY, optimize=True,
               progressive=True, icc_profile=icc_profile)
    return buffer.getvalue()


def _encode_png(image, icc_profile):
    buffer = io.BytesIO()
    image.save(buffer, 'PNG', optimize=True, icc_profile=icc_profile)
    return buffer.getvalue()


def _reencode(source, raw, extension, max_edge, convert):
    image = ImageOps.exif_transpose(source)
    resized = max(image.size) > max_edge
    image.thumbnail((max_edge, max_edge), PILImage.Resampling.LANCZOS)
    icc_profile = source.info.get('icc_profile')

    if source.format == 'JPEG':
        return Processed(_encode_jpeg(image, icc_profile), extension, *image.size)

    png = _encode_png(image, icc_profile)
    if not resized and len(png) >= len(raw):
        return Processed(raw, extension, *source.size)
    if (convert and image.mode in ('RGB', 'L') and len(png) >= PHOTO_PNG_MIN_BYTES
            and image.getcolors(PHOTO_COLOR_LIMIT) is None):
        jpeg = _encode_jpeg(image, icc_profile)
        if len(jpeg) <= len(png) * PHOTO_JPEG_MAX_RATIO:
            return Processed(jpeg, '.jpg', *image.size)
    return Processed(png, extension, *image.size)


def process_image(raw, extension, max_edge=MAX_EDGE, convert=True):
    """Decode ``raw`` and return a smaller, metadata-free copy for the site.

    Photos are oriented, shrunk to ``max_edge`` and re-encoded; GIFs and
    animated images are stored untouched. A photo-like PNG becomes a JPEG
    unless ``convert`` is false, so the extension stays ``extension``. Bytes
    that do not decode raise ``ImageUploadError``.
    """
    try:
        source = PILImage.open(io.BytesIO(raw))
    except DECODE_ERRORS as exc:
        raise ImageUploadError('Image only!') from exc
    width, height = source.size
    if width * height > MAX_PIXELS:
        raise ImageUploadError('Image only!')
    try:
        source.load()
    except DECODE_ERRORS as exc:
        raise ImageUploadError('Image only!') from exc

    if source.format == 'GIF' or getattr(source, 'is_animated', False):
        return Processed(raw, extension, width, height)
    try:
        return _reencode(source, raw, extension, max_edge, convert)
    except DECODE_ERRORS:
        return Processed(raw, extension, width, height)


def read_dimensions(path):
    """Pixel size of the file at ``path``, or ``(None, None)``."""
    try:
        with PILImage.open(path) as image:
            return image.size
    except DECODE_ERRORS:
        return None, None


def save_uploaded_image(file, user):
    """Validate ``file``, compress it, store it under a random name and record it."""
    if file is None or not file.filename:
        raise ImageUploadError('No file selected.')

    original_name = secure_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    header = file.stream.read(16)
    file.stream.seek(0)
    if extension not in ALLOWED_SIGNATURES or not any(
            header.startswith(signature)
            for signature in ALLOWED_SIGNATURES[extension]):
        raise ImageUploadError('Image only!')

    processed = process_image(file.stream.read(), extension)

    folder = upload_folder()
    folder.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid4().hex}{processed.extension}'
    (folder / filename).write_bytes(processed.data)

    image = Image(
        filename=filename, original_name=original_name or filename,
        title=(Path(original_name).stem or filename)[:120],
        size=len(processed.data), width=processed.width,
        height=processed.height, user_id=user.id if user else None)
    db.session.add(image)
    db.session.commit()
    return image


def variant_widths(width):
    """The variant widths worth offering for an image ``width`` px wide."""
    return [candidate for candidate in VARIANT_WIDTHS if candidate < width]


def variant_srcset(filename, src, width):
    """A ``srcset`` for ``src`` (an uploaded image), or ``''`` when it has none."""
    stem, extension = os.path.splitext(filename)
    widths = variant_widths(width)
    if extension not in VARIANT_SOURCE_EXTENSIONS or not widths:
        return ''
    candidates = [f'/files/{VARIANT_FOLDER}/{w}/{stem}.webp {w}w' for w in widths]
    return ', '.join([*candidates, f'{src} {width}w'])


def thumbnail_url(image, width=480):
    """URL of ``image`` at ``width`` px when a smaller copy exists, else the original."""
    stem, extension = os.path.splitext(image.filename)
    if (width in VARIANT_WIDTHS and image.width and image.width > width
            and extension in VARIANT_SOURCE_EXTENSIONS):
        return url_for('variant_file', width=width, stem=stem)
    return url_for('uploaded_files', filename=image.filename)


def variant_path(stem, width):
    return upload_folder() / VARIANT_FOLDER / str(width) / f'{stem}.webp'


def make_variant(stem, width):
    """Path of the ``width`` px WebP copy of upload ``stem``, creating it if needed.

    Returns ``None`` when there is no such upload, it is not a resizable
    format, or it is already no wider than ``width``.
    """
    if width not in VARIANT_WIDTHS or not STEM_RE.match(stem):
        return None
    target = variant_path(stem, width)
    if target.is_file():
        return target
    source = next((path for extension in VARIANT_SOURCE_EXTENSIONS
                   if (path := upload_folder() / f'{stem}{extension}').is_file()),
                  None)
    if source is None:
        return None
    try:
        with PILImage.open(source) as opened:
            if opened.width * opened.height > MAX_PIXELS:
                return None
            icc_profile = opened.info.get('icc_profile')
            image = ImageOps.exif_transpose(opened)
        if image.width <= width:
            return None
        image = image.resize(
            (width, round(image.height * width / image.width)),
            PILImage.Resampling.LANCZOS)
        if image.mode not in ('RGB', 'RGBA'):
            has_alpha = 'A' in image.getbands() or 'transparency' in image.info
            image = image.convert('RGBA' if has_alpha else 'RGB')
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(f'{target.name}.{uuid4().hex}.tmp')
        try:
            image.save(partial, 'WEBP', quality=VARIANT_QUALITY, method=4,
                       icc_profile=icc_profile)
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
    except DECODE_ERRORS:
        return None
    return target


def remove_variants(filename):
    """Delete every cached copy of the upload ``filename``."""
    stem = os.path.splitext(filename)[0]
    for path in (upload_folder() / VARIANT_FOLDER).glob(f'*/{stem}.webp'):
        path.unlink(missing_ok=True)


# A stored file is rewritten in place only if that makes it this much smaller.
RECOMPRESS_MAX_RATIO = 0.9


class OptimizeStats(NamedTuple):
    untracked: int = 0
    dimensions: int = 0
    recompressed: int = 0
    saved_bytes: int = 0
    missing: int = 0


def _replace_file(path, data):
    partial = path.with_name(f'{path.name}.{uuid4().hex}.tmp')
    try:
        partial.write_bytes(data)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def optimize_existing_images(recompress=False):
    """Bring images that predate the upload pipeline up to date.

    Registers stray files and fills in missing pixel sizes. With
    ``recompress`` it also shrinks and re-encodes stored files that would get
    clearly smaller, keeping each file's name and format so links keep working.
    """
    stats = OptimizeStats(untracked=sync_untracked_images())._asdict()
    folder = upload_folder()
    for image in db.session.scalars(sa.select(Image).order_by(Image.id)):
        path = folder / image.filename
        if not path.is_file():
            stats['missing'] += 1
            continue
        if recompress:
            raw = path.read_bytes()
            try:
                processed = process_image(
                    raw, path.suffix.lower(), convert=False)
            except ImageUploadError:
                processed = None
            if processed and len(processed.data) <= len(raw) * RECOMPRESS_MAX_RATIO:
                _replace_file(path, processed.data)
                remove_variants(image.filename)
                stats['recompressed'] += 1
                stats['saved_bytes'] += len(raw) - len(processed.data)
                image.size = len(processed.data)
                image.width, image.height = processed.width, processed.height
                continue
        if image.width is None or image.height is None:
            image.width, image.height = read_dimensions(path)
            if image.width is not None:
                stats['dimensions'] += 1
    db.session.commit()
    return OptimizeStats(**stats)


class Usage(NamedTuple):
    kind: str   # 'post', 'draft' or 'page'
    id: int     # id of the post or page to open in the editor
    title: str


def sync_untracked_images():
    """Register files in the upload folder that have no ``Image`` row."""
    folder = upload_folder()
    if not folder.is_dir():
        return 0
    known = set(db.session.scalars(sa.select(Image.filename)))
    added = 0
    for path in sorted(folder.iterdir()):
        if path.name in known or not IMAGE_NAME_RE.match(path.name) \
                or not path.is_file():
            continue
        stat = path.stat()
        width, height = read_dimensions(path)
        db.session.add(Image(
            filename=path.name, original_name=path.name, title=path.stem,
            size=stat.st_size, width=width, height=height,
            created_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc)))
        added += 1
    if added:
        db.session.commit()
    return added


def image_usage(filenames):
    """Map each filename to the posts, drafts and pages that embed it."""
    wanted = set(filenames)
    usage = {name: [] for name in wanted}

    def collect(kind, rows):
        for source_id, title, body in rows:
            for name in set(USAGE_RE.findall(body or '')) & wanted:
                usage[name].append(Usage(kind, source_id, title))

    collect('post', db.session.execute(
        sa.select(Post.id, Post.title, Post.body).order_by(Post.id)))
    collect('draft', db.session.execute(
        sa.select(PostDraft.post_id, Post.title, PostDraft.body)
        .join(Post, Post.id == PostDraft.post_id).order_by(Post.id)))
    collect('page', db.session.execute(
        sa.select(Page.id, Page.title, Page.body).order_by(Page.id)))
    return usage


def visible_images(user):
    """A select of the images ``user`` may see, newest first."""
    query = sa.select(Image).order_by(Image.created_at.desc(), Image.id.desc())
    if not user.is_admin:
        query = query.where(Image.user_id == user.id)
    return query
