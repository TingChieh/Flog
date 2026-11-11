"""Long-lived caching for static files that never change under the same URL.

Flask sends every static file with ``Cache-Control: no-cache``, so a browser
asks the server about each one on every page view; with the article font split
into ~170 pieces that is a lot of round trips. Fonts and the versioned vendor
folders (``katex/0.19.0`` and so on) are safe to keep for a year.

The site's own CSS and scripts change in place, so ``url_for`` gives them a
``?v=`` fingerprint of their content: a URL carrying the current fingerprint is
kept for a year too, and an edit changes the URL. The bare URL keeps
revalidating.
"""
import hashlib
import re
from pathlib import Path

from flask import request

from app import app

LONG_LIVED = re.compile(
    r'^(fonts/.+\.(woff2|ttf)|vendor/(katex|mermaid|vditor)/\d[\w.]*/.+)$')
ONE_YEAR = 'public, max-age=31536000, immutable'
STATIC = Path(app.static_folder).resolve()
# (filename, mtime, size) -> fingerprint; a changed file gets a new key.
_fingerprints = {}


def fingerprint(filename):
    """A short hash of the static file's content, or None if there is no such file."""
    path = (STATIC / filename).resolve()
    if not path.is_relative_to(STATIC) or not path.is_file():
        return None
    stat = path.stat()
    key = (filename, stat.st_mtime_ns, stat.st_size)
    if key not in _fingerprints:
        _fingerprints[key] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    return _fingerprints[key]


@app.url_defaults
def fingerprint_static_urls(endpoint, values):
    if endpoint != 'static' or 'v' in values:
        return
    filename = values.get('filename', '')
    if LONG_LIVED.match(filename):
        return
    version = fingerprint(filename)
    if version:
        values['v'] = version


@app.after_request
def cache_versioned_static_files(response):
    if request.endpoint != 'static' or response.status_code not in (200, 304):
        return response
    filename = request.view_args.get('filename', '')
    version = request.args.get('v')
    if LONG_LIVED.match(filename) or (version and version == fingerprint(filename)):
        response.headers['Cache-Control'] = ONE_YEAR
    return response
