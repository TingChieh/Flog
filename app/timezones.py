"""Dates are stored in UTC and shown in the site's display time zone."""
from datetime import timezone
from zoneinfo import ZoneInfo

from flask import current_app


def display_zone():
    return ZoneInfo(current_app.config['DISPLAY_TIMEZONE'])


def to_display(value):
    """A naive value is taken as UTC; the result is aware, in the display zone."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(display_zone())
