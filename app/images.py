"""Uploaded images: validation, storage and the database records."""
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

import sqlalchemy as sa
from flask import current_app
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


class ImageUploadError(ValueError):
    pass


def upload_folder():
    return Path(current_app.config['UPLOAD_FOLDER'])


def save_uploaded_image(file, user):
    """Validate ``file``, store it under a random name and record it."""
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

    folder = upload_folder()
    folder.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid4().hex}{extension}'
    path = folder / filename
    file.save(path)

    image = Image(
        filename=filename, original_name=original_name or filename,
        title=(Path(original_name).stem or filename)[:120],
        size=path.stat().st_size, user_id=user.id if user else None)
    db.session.add(image)
    db.session.commit()
    return image


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
        db.session.add(Image(
            filename=path.name, original_name=path.name, title=path.stem,
            size=stat.st_size,
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
