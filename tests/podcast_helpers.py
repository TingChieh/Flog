from datetime import datetime

from app import db
from app.models import Episode, PodcastShow
from tests.conftest import make_mp3


def add_episode(folder, number=1, title='第一集', published=True, **values):
    """An episode whose audio really exists under ``folder``/audio."""
    audio = folder / 'audio'
    audio.mkdir(parents=True, exist_ok=True)
    filename = f'{number:032x}.mp3'
    data = make_mp3(3)
    (audio / filename).write_bytes(data)
    values.setdefault('summary', '一段摘要')
    values.setdefault('body', '## 时间轴\n\n- [00:10] 开场')
    values.setdefault('published_at', datetime(2022, 1, 29, 8, 0))
    episode = Episode(
        number=number, title=title, audio_filename=filename,
        audio_size=len(data), audio_duration=3, audio_mime='audio/mpeg',
        is_published=published, **values)
    db.session.add(episode)
    db.session.commit()
    return episode.id


def set_show(**values):
    show = db.session.get(PodcastShow, 1) or PodcastShow(id=1)
    for key, value in values.items():
        setattr(show, key, value)
    db.session.add(show)
    db.session.commit()
