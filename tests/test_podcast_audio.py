import io
from pathlib import Path

import pytest
from werkzeug.datastructures import FileStorage

from app.podcast import (AudioUploadError, apply_audio, format_duration,
                         remove_audio, save_uploaded_audio, store_audio)
from app.models import Episode
from tests.conftest import make_mp3, needs_ffmpeg


def upload(name, data):
    return FileStorage(stream=io.BytesIO(data), filename=name)


def audio_files(application):
    folder = Path(application.config['UPLOAD_FOLDER']) / 'audio'
    return sorted(folder.glob('*')) if folder.is_dir() else []


def test_an_mp3_is_stored_under_a_random_name_and_measured(application):
    info = save_uploaded_audio(upload('Aisaka EP005.MP3', make_mp3(3)))

    assert info.filename.endswith('.mp3') and len(info.filename) == 36
    assert 'EP005' not in info.filename
    assert info.mime == 'audio/mpeg'
    assert info.duration == 3
    assert info.size == len(make_mp3(3))
    assert [p.name for p in audio_files(application)] == [info.filename]


@needs_ffmpeg
def test_an_m4a_is_accepted_and_announced_as_x_m4a(application, tmp_path):
    import shutil
    import subprocess
    path = tmp_path / 'tone.m4a'
    subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i',
                    'sine=duration=2', '-c:a', 'aac', str(path)], check=True)

    info = save_uploaded_audio(upload('tone.m4a', path.read_bytes()))

    assert info.filename.endswith('.m4a')
    assert info.mime == 'audio/x-m4a'
    assert info.duration == 2


@pytest.mark.parametrize('name', ['talk.wav', 'talk.mp3.exe', 'talk', 'a.png'])
def test_other_file_types_are_refused(application, name):
    with pytest.raises(AudioUploadError):
        save_uploaded_audio(upload(name, make_mp3(1)))
    assert audio_files(application) == []


def test_a_file_that_is_not_really_audio_is_refused_and_not_kept(application):
    with pytest.raises(AudioUploadError):
        save_uploaded_audio(upload('fake.mp3', b'this is not audio' * 100))
    assert audio_files(application) == []


def test_no_file_selected_is_refused(application):
    with pytest.raises(AudioUploadError):
        save_uploaded_audio(None)
    with pytest.raises(AudioUploadError):
        save_uploaded_audio(upload('', b''))


def test_store_audio_copies_a_file_from_disk(application, tmp_path):
    source = tmp_path / 'EP.mp3'
    source.write_bytes(make_mp3(2))

    info = store_audio(source)

    assert source.exists()
    assert info.duration == 2
    assert len(audio_files(application)) == 1


def test_apply_audio_reports_the_file_it_replaces(application):
    first = save_uploaded_audio(upload('a.mp3', make_mp3(1)))
    second = save_uploaded_audio(upload('b.mp3', make_mp3(2)))
    episode = Episode()

    assert apply_audio(episode, first) is None
    assert apply_audio(episode, second) == first.filename
    assert (episode.audio_filename, episode.audio_duration) == (second.filename, 2)


def test_remove_audio_only_touches_audio_names(application):
    info = save_uploaded_audio(upload('a.mp3', make_mp3(1)))
    other = Path(application.config['UPLOAD_FOLDER']) / 'keep.txt'
    other.write_text('keep')

    remove_audio('../keep.txt')
    remove_audio(info.filename)

    assert other.exists()
    assert audio_files(application) == []


def test_durations_read_like_a_player():
    assert format_duration(0) == '0:00'
    assert format_duration(95) == '1:35'
    assert format_duration(2016) == '33:36'
    assert format_duration(7547) == '2:05:47'
