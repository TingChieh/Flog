"""The podcast: its wording, episode audio, and the feed apps subscribe to.

Nothing here commits except where noted; the caller owns the transaction.
"""
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote
from uuid import uuid4

import mutagen
import sqlalchemy as sa
from feedgen.feed import FeedGenerator
from flask import Request, current_app, url_for
from flask_login import current_user
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from werkzeug.utils import secure_filename

from app import db
from app.content import render_content
from app.models import Episode, PodcastShow
from app.site_text import site_text

# The only wording the code supplies itself: everything else about the show
# (its name, description, author) is the owner's to write, so a fresh install
# carries nobody's show. Until it is written, the name and author come from
# the site's own name, and the description stays empty.
DEFAULT_CATEGORY = 'Society & Culture'
TITLE_SUFFIX = ' 播客'

# Audio lives next to the uploaded images, in its own folder.
AUDIO_FOLDER = 'audio'
AUDIO_NAME_RE = re.compile(r'^[0-9a-f]{32}\.(?:mp3|m4a)$')
# Extension -> the type the feed announces; Apple wants x-m4a for AAC in MP4.
AUDIO_TYPES = {'.mp3': 'audio/mpeg', '.m4a': 'audio/x-m4a'}


# Pages whose POST carries an episode's audio file.
AUDIO_UPLOAD_PATH = re.compile(r'/admin/podcast/(?:new|\d+/edit)')


class UploadRequest(Request):
    """A request whose size limit is higher for an admin uploading audio.

    The limit has to be known before anything reads the body, and Flask-WTF's
    CSRF check does that before any view runs, so it cannot be set in the view.
    Everyone else keeps ``MAX_CONTENT_LENGTH``.
    """

    @property
    def max_content_length(self):
        if self._explicit_limit is not None:
            return self._explicit_limit
        if self.method == 'POST' and AUDIO_UPLOAD_PATH.fullmatch(self.path) \
                and current_user.is_authenticated and current_user.is_admin:
            return current_app.config['PODCAST_AUDIO_MAX_MB'] * 1024 * 1024
        return current_app.config.get('MAX_CONTENT_LENGTH')

    @max_content_length.setter
    def max_content_length(self, value):
        self._explicit_limit = value

    _explicit_limit = None


class AudioUploadError(ValueError):
    """The file is not audio the podcast can serve; the message is shown."""


class AudioInfo(NamedTuple):
    filename: str
    size: int
    duration: int
    mime: str


def show_text():
    """The show's wording with blanks filled by the defaults."""
    show = db.session.get(PodcastShow, 1)

    def custom(name):
        return ((getattr(show, name, None) or '').strip()) or None

    site_name = site_text()['site_name']
    return {
        'title': custom('title') or f'{site_name}{TITLE_SUFFIX}',
        'title_set': custom('title') is not None,
        'description': custom('description') or '',
        'author': custom('author') or site_name,
        'author_set': custom('author') is not None,
        'owner_email': custom('owner_email'),
        'category': custom('category') or DEFAULT_CATEGORY,
        'cover_filename': custom('cover_filename'),
        'apple_url': custom('apple_url'),
        'xiaoyuzhou_url': custom('xiaoyuzhou_url'),
    }


def audio_folder():
    return Path(current_app.config['UPLOAD_FOLDER']) / AUDIO_FOLDER


def audio_path(filename):
    return audio_folder() / filename


def audio_url(episode, external=False):
    return url_for('uploaded_files',
                   filename=f'{AUDIO_FOLDER}/{episode.audio_filename}',
                   _external=external)


def _read_audio(path, extension):
    """Seconds of audio in ``path``, or an AudioUploadError if it is not that."""
    try:
        parsed = (MP3 if extension == '.mp3' else MP4)(path)
    except (mutagen.MutagenError, OSError, ValueError, EOFError) as exc:
        raise AudioUploadError('无法识别这个音频文件，请上传 MP3 或 M4A。') from exc
    length = getattr(parsed.info, 'length', 0) or 0
    if length <= 0:
        raise AudioUploadError('无法读取音频时长，文件可能已损坏。')
    return int(round(length))


def _check_extension(name):
    extension = Path(secure_filename(name or '')).suffix.lower()
    if extension not in AUDIO_TYPES:
        raise AudioUploadError('只支持 MP3 和 M4A 音频。')
    return extension


def store_audio(source):
    """Copy the audio file at ``source`` into the audio folder under a random name."""
    source = Path(source)
    extension = _check_extension(source.name)
    duration = _read_audio(source, extension)
    folder = audio_folder()
    folder.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid4().hex}{extension}'
    shutil.copyfile(source, folder / filename)
    return AudioInfo(filename, source.stat().st_size, duration,
                     AUDIO_TYPES[extension])


def save_uploaded_audio(file):
    """Validate an uploaded file, store it under a random name and describe it."""
    if file is None or not file.filename:
        raise AudioUploadError('请选择音频文件。')
    extension = _check_extension(file.filename)
    folder = audio_folder()
    folder.mkdir(parents=True, exist_ok=True)
    filename = f'{uuid4().hex}{extension}'
    path = folder / filename
    try:
        file.save(path)
        duration = _read_audio(path, extension)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return AudioInfo(filename, path.stat().st_size, duration,
                     AUDIO_TYPES[extension])


def remove_audio(filename):
    if filename and AUDIO_NAME_RE.match(filename):
        audio_path(filename).unlink(missing_ok=True)


def apply_audio(episode, info):
    """Point ``episode`` at stored audio.

    Returns the file it had before, which the caller deletes once the change
    is committed.
    """
    previous = episode.audio_filename
    episode.audio_filename = info.filename
    episode.audio_size = info.size
    episode.audio_duration = info.duration
    episode.audio_mime = info.mime
    return previous


def import_episode(*, number, title, audio_path, published_at, summary=None,
                   body=None, cover_path=None, legacy_path=None,
                   feed_guid=None, is_published=True):
    """Create an episode from files on disk (used by ``flask podcast add``).

    ``published_at`` is naive UTC. Nothing is committed.
    """
    from werkzeug.datastructures import FileStorage
    from app.images import save_uploaded_image

    info = store_audio(audio_path)
    episode = Episode(
        number=number, title=title, summary=summary, body=body,
        published_at=published_at, legacy_path=legacy_path,
        feed_guid=feed_guid, is_published=is_published,
        comments_enabled=True)
    apply_audio(episode, info)
    if cover_path:
        with open(cover_path, 'rb') as stream:
            image = save_uploaded_image(
                FileStorage(stream=stream, filename=Path(cover_path).name),
                None)
        episode.cover_filename = image.filename
    db.session.add(episode)
    return episode


def delete_episode(episode):
    """Remove the episode and its comments.

    Returns its audio file, which the caller deletes once this is committed.
    """
    db.session.delete(episode)
    return episode.audio_filename


class FeedProblem(NamedTuple):
    text: str
    # Where in the admin it is fixed, and what the link says.
    endpoint: str
    action: str


def feed_problems():
    """What would make Apple or 小宇宙 reject the feed, in plain words."""
    show = show_text()
    problems = []
    if not show['title_set']:
        problems.append(FeedProblem(
            '还没有给节目起名：现在用的是网站名加“播客”。',
            'admin.podcast_show', '去节目设置起名'))
    if not show['description']:
        problems.append(FeedProblem(
            '还没有节目简介：订阅 App 里会显示它。',
            'admin.podcast_show', '去节目设置写简介'))
    if not show['owner_email']:
        problems.append(FeedProblem(
            '还没有填联系邮箱：Apple 和小宇宙需要它来验证你是节目的主人。',
            'admin.podcast_show', '去节目设置填写'))
    if not show['cover_filename']:
        problems.append(FeedProblem(
            '还没有节目封面：Apple 要求正方形封面，1400 到 3000 像素。',
            'admin.podcast_show', '去节目设置上传'))
    if not db.session.scalar(sa.select(sa.func.count()).select_from(
            published_episodes().subquery())):
        problems.append(FeedProblem(
            '还没有已发布的单集。', 'admin.new_episode', '新建单集'))
    return problems


def format_duration(seconds):
    seconds = int(seconds or 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f'{hours}:{minutes:02d}:{secs:02d}'
    return f'{minutes}:{secs:02d}'


def published_episodes():
    return sa.select(Episode).where(Episode.is_published.is_(True))


def podcast_enabled():
    show = db.session.get(PodcastShow, 1)
    return show is not None and show.enabled


def podcast_in_nav():
    """Whether the blog menu links to the podcast."""
    show = db.session.get(PodcastShow, 1)
    return show is not None and show.enabled and show.show_in_nav


def latest_episodes():
    return published_episodes().order_by(
        Episode.published_at.desc(), Episode.number.desc())


def public_episode_or_404(number):
    return db.first_or_404(published_episodes().where(Episode.number == number))


def next_episode_number():
    highest = db.session.scalar(sa.select(sa.func.max(Episode.number)))
    return (highest or 0) + 1


def episode_by_legacy_path(path):
    """The published episode that lived at ``path`` on the old site, if any."""
    wanted = unquote(path).rstrip('/')
    for episode in db.session.scalars(published_episodes().where(
            Episode.legacy_path.is_not(None))):
        if unquote(episode.legacy_path).rstrip('/') == wanted:
            return episode
    return None


def cover_url(filename, external=False):
    """Address of an uploaded cover image; None when there is none."""
    if not filename:
        return None
    return url_for('uploaded_files', filename=filename, _external=external)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def build_feed():
    """The RSS feed podcast apps read; only published episodes appear."""
    show = show_text()
    feed_url = url_for('podcast_feed', _external=True)
    home_url = url_for('podcast_index', _external=True)
    fg = FeedGenerator()
    fg.load_extension('podcast')
    fg.title(show['title'])
    fg.link(href=feed_url, rel='self')
    # feedgen uses the last registered link for the RSS channel link.
    fg.link(href=home_url, rel='alternate')
    description = show['description'] or show['title']
    fg.description(description)
    fg.language('zh-cn')
    fg.podcast.itunes_author(show['author'])
    fg.podcast.itunes_summary(description)
    fg.podcast.itunes_explicit('no')
    fg.podcast.itunes_category(show['category'])
    if show['owner_email']:
        fg.podcast.itunes_owner(name=show['author'], email=show['owner_email'])
    cover = cover_url(show['cover_filename'], external=True)
    if cover:
        fg.podcast.itunes_image(cover)
        fg.image(cover, title=show['title'], link=home_url)

    episodes = db.session.scalars(latest_episodes()).all()
    # feedgen stamps "now" by default, which would change the ETag every second.
    fg.lastBuildDate(max((_aware(e.published_at) for e in episodes),
                         default=datetime(1970, 1, 1, tzinfo=timezone.utc)))
    for episode in episodes:
        entry = fg.add_entry(order='append')
        permalink = url_for('podcast_episode', number=episode.number,
                            _external=True)
        entry.title(episode.title)
        entry.link(href=permalink)
        entry.guid(episode.feed_guid or permalink,
                   permalink=not episode.feed_guid)
        description = episode.summary or ''
        entry.description(description or episode.title)
        if episode.body:
            entry.content(str(render_content(
                episode.body, 'markdown', images=False)), type='CDATA')
        entry.pubDate(_aware(episode.published_at))
        entry.enclosure(audio_url(episode, external=True),
                        str(episode.audio_size), episode.audio_mime)
        entry.podcast.itunes_duration(episode.audio_duration)
        entry.podcast.itunes_episode(episode.number)
        entry.podcast.itunes_episode_type('full')
        episode_cover = cover_url(episode.cover_filename, external=True)
        if episode_cover:
            entry.podcast.itunes_image(episode_cover)
    return fg.rss_str(pretty=True)


def legacy_redirect_target(path, args):
    """Where a request for ``path`` on the old podcast site should go.

    Returns a path on this site; the home page of the podcast when the old
    address is not known.
    """
    if path.rstrip('/') in ('/feed', '/feed/podcast') or 'feed' in args:
        return url_for('podcast_feed')
    episode = episode_by_legacy_path(path)
    if episode is not None:
        return url_for('podcast_episode', number=episode.number)
    return url_for('podcast_index')
