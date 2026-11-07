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


def from_display(value):
    """The inverse of ``to_display`` for a naive local time: naive UTC, as stored."""
    if value is None:
        return None
    return value.replace(tzinfo=display_zone()).astimezone(
        timezone.utc).replace(tzinfo=None)


def later_update(published, updated):
    """The update time in the display zone, if it falls on a later day than the publish time.

    An edit on the day of publishing is not worth announcing, so it gives None.
    """
    if updated is None:
        return None
    local = to_display(updated)
    return local if local.date() > to_display(published).date() else None
