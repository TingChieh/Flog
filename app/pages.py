from dataclasses import dataclass
import re
import unicodedata

import sqlalchemy as sa
import sqlalchemy.orm as so

from app import db
from app.content import normalize_body_format, prepare_content_source
from app.models import Page, PageRedirect, PodcastShow, get_podcast_show


PAGE_CONTENT = 'content'
RESERVED_SLUGS = frozenset({
    'admin', 'login', 'logout', 'register', 'reset-password', 'post', 'user',
    'static', 'files', 'upload', 'rss', 'index', 'search',
    'messages', 'notifications', 'categories', 'category', 'archive',
    'podcast',
})


class PageValidationError(ValueError):
    pass


def normalize_slug(value):
    normalized = unicodedata.normalize('NFKD', value or '')
    ascii_value = normalized.encode('ascii', 'ignore').decode('ascii').lower()
    slug = re.sub(r'[^a-z0-9]+', '-', ascii_value).strip('-')
    if not slug:
        raise PageValidationError('Slug must contain letters or numbers.')
    if slug in RESERVED_SLUGS:
        raise PageValidationError('This slug is reserved by the system.')
    if len(slug) > 120:
        raise PageValidationError('Slug must be 120 characters or fewer.')
    return slug


def _validate_page_identity(kind, module_key):
    if kind != PAGE_CONTENT:
        raise PageValidationError('Unknown page kind.')
    if module_key is not None:
        raise PageValidationError('Content pages cannot have a module key.')


def _redirect_for_slug(slug):
    return db.session.scalar(
        sa.select(PageRedirect).where(PageRedirect.slug == slug))


def _validate_slug_available(page, slug):
    query = sa.select(Page).where(Page.slug == slug)
    if page.id is not None:
        query = query.where(Page.id != page.id)
    with db.session.no_autoflush:
        if db.session.scalar(query) is not None:
            raise PageValidationError('This slug is already in use.')
        redirect = _redirect_for_slug(slug)
    if redirect is not None and redirect.page_id != page.id:
        raise PageValidationError('This slug is already in use.')
    return redirect


def save_page(page, values):
    title = (values.get('title', page.title) or '').strip()
    if not title:
        raise PageValidationError('Title is required.')
    if len(title) > 120:
        raise PageValidationError('Title must be 120 characters or fewer.')

    slug = normalize_slug(values.get('slug', page.slug))
    kind = values.get('kind', page.kind or PAGE_CONTENT)
    module_key = values.get('module_key', page.module_key)
    _validate_page_identity(kind, module_key)
    reclaimed_redirect = _validate_slug_available(page, slug)

    summary = values.get('summary', page.summary)
    summary = (summary or '').strip() or None
    if summary is not None and len(summary) > 300:
        raise PageValidationError('Summary must be 300 characters or fewer.')

    old_slug = page.slug
    if reclaimed_redirect is not None:
        db.session.delete(reclaimed_redirect)
        db.session.flush()

    page.title = title
    page.slug = slug
    page.summary = summary
    page.kind = kind
    page.module_key = module_key
    page.is_published = bool(values.get(
        'is_published', page.is_published if page.id is not None else False))
    page.show_in_nav = bool(values.get(
        'show_in_nav', page.show_in_nav if page.id is not None else False))
    page.comments_enabled = bool(values.get(
        'comments_enabled',
        page.comments_enabled if page.id is not None else False))
    page.nav_order = int(values.get(
        'nav_order', page.nav_order if page.id is not None else 0) or 0)
    page.body_format = normalize_body_format(
        values.get('body_format', page.body_format))
    page.body = prepare_content_source(
        values.get('body', page.body), page.body_format)

    db.session.add(page)
    if old_slug and old_slug != slug:
        existing = _redirect_for_slug(old_slug)
        if existing is None:
            db.session.add(PageRedirect(slug=old_slug, page=page))
        elif existing.page_id != page.id:
            raise PageValidationError('The previous slug is already in use.')
    db.session.flush()
    return page


def delete_content_page(page):
    if page.kind != PAGE_CONTENT:
        raise PageValidationError('Module pages cannot be deleted.')
    db.session.execute(sa.delete(PageRedirect).where(
        PageRedirect.page_id == page.id))
    db.session.delete(page)


def page_for_public_slug(slug):
    try:
        normalized = normalize_slug(slug)
    except PageValidationError:
        return None
    page = db.session.scalar(sa.select(Page).where(
        Page.slug == normalized, Page.is_published.is_(True)))
    if page is not None:
        return page, False
    redirect = db.session.scalar(sa.select(PageRedirect).join(Page).where(
        PageRedirect.slug == normalized, Page.is_published.is_(True)))
    if redirect is None:
        return None
    return redirect.page, True


@dataclass(frozen=True)
class NavigationEntry:
    kind: str
    title: str
    slug: str | None
    nav_order: int
    sort_id: int


def nav_sort_key(kind, nav_order, title, sort_id):
    """Order custom pages and built-in modules together in the site menu."""
    return (nav_order, 0 if kind == 'page' else 1, title or '', sort_id or 0)


def visible_navigation_pages():
    # The menu only needs titles and slugs, not every page's full body.
    return db.session.scalars(sa.select(Page).options(so.defer(Page.body)).where(
        Page.is_published.is_(True), Page.show_in_nav.is_(True)
    ).order_by(Page.nav_order, Page.title, Page.id)).all()


def visible_navigation_items():
    """Return visible pages and enabled built-in navigation links in menu order."""
    items = [
        NavigationEntry('page', page.title, page.slug, page.nav_order, page.id)
        for page in visible_navigation_pages()
    ]
    show = db.session.get(PodcastShow, 1)
    if show is not None and show.enabled and show.show_in_nav:
        items.append(NavigationEntry('podcast', '播客', None, show.nav_order, show.id))
    items.sort(key=lambda item: nav_sort_key(
        item.kind, item.nav_order, item.title, item.sort_id))
    return items


def move_nav_item(kind, target_id, direction):
    """Move a page or built-in module one place up or down the navigation order.

    Items often share the same nav_order, so the whole order is first
    renumbered 0..n-1 in the order it is shown, then neighbours are swapped.
    Returns False when the item is already at that end.
    """
    pages = db.session.scalars(sa.select(Page).order_by(
        Page.nav_order, Page.title, Page.id)).all()
    show = get_podcast_show()
    db.session.flush()
    items = [
        ('page', item, nav_sort_key('page', item.nav_order, item.title, item.id))
        for item in pages
    ] + [
        ('podcast', show, nav_sort_key('podcast', show.nav_order, '播客', show.id))
    ]
    items.sort(key=lambda entry: entry[2])
    index = next(
        i for i, (item_kind, obj, _) in enumerate(items)
        if item_kind == kind and (kind == 'podcast' or obj.id == target_id)
    )
    target = index - 1 if direction == 'up' else index + 1
    if not 0 <= target < len(items):
        return False
    items[index], items[target] = items[target], items[index]
    for position, (_, obj, _) in enumerate(items):
        if obj.nav_order != position:
            obj.nav_order = position
    return True


def move_page(page, direction):
    return move_nav_item('page', page.id, direction)
