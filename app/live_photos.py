"""Live Photo support: the companion video of a still and its web encoding.

A Live Photo is a still image plus a ~3 s clip. iPhones export them as a
``.HEIC``/``.JPG`` and a same-named ``.MOV``; Android "motion photos" are one
JPEG with an MP4 appended. Either way the site keeps the still as the normal
upload and the clip as ``<stem>.mp4`` next to it.
"""
import os
import re
import shutil
import subprocess
import tempfile

from flask import current_app


VIDEO_EXTENSIONS = ('.mov', '.mp4')
# Brands of the "ftyp" box that mark a HEIC/HEIF still.
HEIF_BRANDS = (b'heic', b'heix', b'heim', b'heis', b'hevc', b'hevx',
               b'mif1', b'msf1')
# The clip is cut to this length and fitted into this box; sound is dropped
# (autoplay is muted anyway) so the file stays small.
VIDEO_MAX_SECONDS = 5
VIDEO_MAX_EDGE = 960
VIDEO_CRF = 28
FFMPEG_TIMEOUT = 90

_MICRO_VIDEO_OFFSET = re.compile(rb'MicroVideoOffset\s*=\s*"(\d+)"')
_CONTAINER_ITEM = re.compile(rb'<Container:Item\b[^>]*>')
_ITEM_LENGTH = re.compile(rb'Item:Length\s*=\s*"(\d+)"')
# Camera apps put the XMP packet near the start of the file.
_XMP_SEARCH_BYTES = 256 * 1024


class VideoError(ValueError):
    """The clip could not be turned into a web video."""


class FfmpegMissing(VideoError):
    pass


def has_heif_signature(header):
    return header[4:8] == b'ftyp' and header[8:12] in HEIF_BRANDS


def has_video_signature(header):
    return header[4:8] == b'ftyp'


def video_filename(stem):
    return f'{stem}.mp4'


def ffmpeg_path():
    return current_app.config.get('FFMPEG') or shutil.which('ffmpeg')


def extract_embedded_video(raw):
    """The MP4 appended to an Android motion photo, or ``None``."""
    head = raw[:_XMP_SEARCH_BYTES]
    length = None
    match = _MICRO_VIDEO_OFFSET.search(head)
    if match:
        length = int(match.group(1))
    else:
        for tag in _CONTAINER_ITEM.findall(head):
            if b'MotionPhoto' in tag or b'video/mp4' in tag:
                found = _ITEM_LENGTH.search(tag)
                if found and int(found.group(1)) > 0:
                    length = int(found.group(1))
                    break
    if not length or length >= len(raw):
        return None
    video = raw[-length:]
    return video if has_video_signature(video[:12]) else None


def transcode_video(raw):
    """H.264 MP4 of ``raw`` that plays in every browser, as bytes."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise FfmpegMissing('ffmpeg is not installed')
    with tempfile.TemporaryDirectory() as work:
        source = os.path.join(work, 'in')
        target = os.path.join(work, 'out.mp4')
        with open(source, 'wb') as handle:
            handle.write(raw)
        command = [
            ffmpeg, '-nostdin', '-v', 'error', '-i', source,
            '-t', str(VIDEO_MAX_SECONDS), '-an',
            '-vf', (f'scale=min({VIDEO_MAX_EDGE}\\,iw):'
                    f'min({VIDEO_MAX_EDGE}\\,ih):'
                    'force_original_aspect_ratio=decrease:force_divisible_by=2'),
            '-c:v', 'libx264', '-preset', 'medium', '-crf', str(VIDEO_CRF),
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', target,
        ]
        try:
            subprocess.run(command, capture_output=True, timeout=FFMPEG_TIMEOUT,
                           check=True)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError) as exc:
            raise VideoError('video could not be converted') from exc
        with open(target, 'rb') as handle:
            data = handle.read()
    if not data:
        raise VideoError('video could not be converted')
    return data
