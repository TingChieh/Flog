import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


basedir = Path(__file__).resolve().parent
load_dotenv(dotenv_path=basedir / '.env', override=False)


def resolve_project_path(value):
    """Resolve a relative path against the project root."""
    path = Path(value)
    return str(path if path.is_absolute() else basedir / path)


def env_list(name):
    return [value.strip() for value in os.environ.get(name, '').split(',')
            if value.strip()]


def analytics_id(name, pattern):
    """An optional analytics ID; anything that is not well formed is ignored."""
    value = os.environ.get(name, '').strip()
    return value if re.fullmatch(pattern, value) else None


def display_timezone():
    """Zone used to show dates; the site is Chinese, so China time by default."""
    name = os.environ.get('DISPLAY_TIMEZONE', '').strip() or 'Asia/Shanghai'
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return 'Asia/Shanghai'
    return name


def trusted_proxy_hops():
    """How many reverse proxies sit in front of the app (Caddy: 1).

    Only that many X-Forwarded-For entries, counted from the right, are trusted,
    so a visitor cannot make up their own address. 0 means no proxy.
    """
    value = os.environ.get('TRUSTED_PROXY_HOPS', '').strip()
    return int(value) if value.isdigit() and int(value) <= 5 else 1


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', f'sqlite:///{basedir / "instance" / "flog.sqlite3"}')
    _isolation_level = os.environ.get('DB_ISOLATION_LEVEL', '').strip()
    if _isolation_level and _isolation_level not in {
            'READ COMMITTED', 'READ UNCOMMITTED', 'REPEATABLE READ',
            'SERIALIZABLE', 'AUTOCOMMIT'}:
        raise ValueError('Invalid DB_ISOLATION_LEVEL')
    SQLALCHEMY_ENGINE_OPTIONS = (
        {'isolation_level': _isolation_level} if _isolation_level else {})
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', '465'))
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    ADMINS = env_list('ADMIN_EMAILS')
    ADMIN_EMAILS = ADMINS
    LANGUAGES = ['zh']
    POSTS_PER_PAGE = 10
    SEARCH_QUERY_MAX_LENGTH = 200
    POST_VIEW_WINDOW_SECONDS = 24 * 60 * 60
    TRUSTED_PROXY_HOPS = trusted_proxy_hops()
    # Likes one network address (hashed) may leave on a single post.
    LIKES_PER_IP_PER_POST = 3
    # Comments one network address (hashed) may leave, and the quickest a
    # reader could plausibly fill the form in.
    COMMENTS_PER_MINUTE_PER_IP = 3
    COMMENTS_PER_HOUR_PER_IP = 20
    COMMENTS_MIN_FILL_SECONDS = 3
    DISPLAY_TIMEZONE = display_timezone()
    BABEL_DEFAULT_TIMEZONE = DISPLAY_TIMEZONE
    GTM_ID = analytics_id('GTM_ID', r'GTM-[A-Z0-9]{4,20}')
    GA_MEASUREMENT_ID = analytics_id('GA_MEASUREMENT_ID', r'G-[A-Z0-9]{4,20}')
    UPLOAD_FOLDER = resolve_project_path(os.environ.get(
        'UPLOAD_FOLDER', str(basedir / 'instance' / 'uploads')))
    # Live Photo clips are transcoded with ffmpeg; empty means look on PATH.
    FFMPEG = os.environ.get('FFMPEG_PATH')
    # Keep the request guard high enough for camera exports and article
    # screenshots while still bounding multipart requests.
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
