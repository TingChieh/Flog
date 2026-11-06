"""Long-lived caching for static files that never change under the same URL.

Flask sends every static file with ``Cache-Control: no-cache``, so a browser
asks the server about each one on every page view; with the article font split
into ~170 pieces that is a lot of round trips. Fonts and the versioned vendor
folders (``katex/0.19.0`` and so on) are safe to keep for a year. The site's own
CSS and scripts keep revalidating, so an edit shows up on the next load.
"""
import re

from flask import request

from app import app

LONG_LIVED = re.compile(
    r'^(fonts/.+\.(woff2|ttf)|vendor/(katex|mermaid|vditor)/\d[\w.]*/.+)$')
ONE_YEAR = 'public, max-age=31536000, immutable'


@app.after_request
def cache_versioned_static_files(response):
    if (request.endpoint == 'static' and response.status_code in (200, 304)
            and LONG_LIVED.match(request.view_args.get('filename', ''))):
        response.headers['Cache-Control'] = ONE_YEAR
    return response
