"""Headers that keep browsers strict with what this site sends.

- ``nosniff``: an upload is only ever handled as the type it is served with.
- ``SAMEORIGIN``: other sites cannot frame a page (the admin included) to
  trick clicks on it.
- ``strict-origin-when-cross-origin``: other sites learn where a visitor came
  from, never the full address (search terms, reset and unsubscribe links).
- ``Permissions-Policy``: disable camera, microphone and geolocation APIs.

A header a view set itself is left alone.
"""
from app import app

HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'SAMEORIGIN',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
}


@app.after_request
def set_security_headers(response):
    for name, value in HEADERS.items():
        response.headers.setdefault(name, value)
    return response
