"""Custom user avatars: validation and storage under ``<uploads>/avatars``."""
from pathlib import Path
from uuid import uuid4

from app import db
from app.images import (ALLOWED_SIGNATURES, ImageUploadError, process_image,
                        upload_folder)


AVATAR_MAX_BYTES = 2 * 1024 * 1024
# Avatars show at most ~120 px, so 256 px covers high-density screens.
AVATAR_EDGE = 256


class AvatarUploadError(ValueError):
    pass


def avatar_folder():
    return upload_folder() / 'avatars'


def remove_avatar_file(filename):
    """Delete a stored avatar; a missing file is not an error."""
    if filename:
        (avatar_folder() / Path(filename).name).unlink(missing_ok=True)


def save_avatar(file, user):
    """Validate ``file`` and make it ``user``'s avatar, replacing the old one."""
    if file is None or not file.filename:
        raise AvatarUploadError('请选择要上传的图片。')
    extension = Path(file.filename).suffix.lower()
    header = file.stream.read(16)
    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)
    if extension not in ALLOWED_SIGNATURES or not any(
            header.startswith(signature)
            for signature in ALLOWED_SIGNATURES[extension]):
        raise AvatarUploadError('不是有效的 gif/jpg/png 图片。')
    if size > AVATAR_MAX_BYTES:
        raise AvatarUploadError('头像不能超过 2 MB。')

    try:
        processed = process_image(
            file.stream.read(), extension, max_edge=AVATAR_EDGE)
    except ImageUploadError as exc:
        raise AvatarUploadError('不是有效的 gif/jpg/png 图片。') from exc

    folder = avatar_folder()
    folder.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid4().hex}{processed.extension}'
    (folder / filename).write_bytes(processed.data)
    previous, user.avatar_filename = user.avatar_filename, filename
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        remove_avatar_file(filename)
        raise
    remove_avatar_file(previous)


def clear_avatar(user):
    """Go back to the default avatar."""
    previous, user.avatar_filename = user.avatar_filename, None
    db.session.commit()
    remove_avatar_file(previous)
