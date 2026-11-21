"""Public URL and SEO metadata helpers (single source of truth for head tags and feeds)."""
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

from flask import current_app, make_response, request, url_for
from lxml import html

from app.content import missing_uploaded_image
from app.models import Post
from app.site_text import site_text

NOINDEX = 'noindex, nofollow'

NON_INDEXABLE_ENDPOINTS = frozenset({
    'search',
    'login',
    'logout',
    'register',
    'reset_password_request',
    'reset_password',
    'comment_unsubscribe',
    'edit_post',
    'delete_post',
    'edit_category',
    'delete_category',
    'delete_post_comment',
    'upload',
})

CANONICAL_ENDPOINTS = frozenset({
    'index',
    'post',
    'archive',
    'categories',
    'posts_by_category',
    'public_page',
    'podcast_index',
    'podcast_episode',
})


def public_base_url() -> str:
    """Configured SITE_URL when set, otherwise the current request origin."""
    configured = (current_app.config.get('SITE_URL') or '').strip().rstrip('/')
    return configured or request.url_root.rstrip('/')


def public_url(endpoint: str, **values: Any) -> str:
    """Absolute public URL for ``endpoint`` using the canonical site origin."""
    path = url_for(endpoint, **values)
    return f'{public_base_url()}{path}'


def canonical_url() -> str | None:
    """Canonical URL for indexable public pages, or None for non-indexable pages."""
    endpoint = request.endpoint
    if request.blueprint == 'admin' or endpoint not in CANONICAL_ENDPOINTS:
        return None
    if endpoint == 'index':
        page = request.args.get('page', 1, type=int) or 1
        if page > 1:
            return f'{public_base_url()}/?page={page}'
        return f'{public_base_url()}/'
    view_args = request.view_args or {}
    return public_url(endpoint, **view_args)


def robots_directive() -> str | None:
    endpoint = request.endpoint
    if (request.blueprint == 'admin'
            or endpoint is None
            or endpoint in NON_INDEXABLE_ENDPOINTS):
        return NOINDEX
    return None


def preview_response(document: str):
    response = make_response(document)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Robots-Tag'] = NOINDEX
    return response


def seo_context() -> dict[str, Any]:
    endpoint = request.endpoint
    canonical = canonical_url()
    return {
        'canonical_url': canonical,
        'robots': robots_directive(),
        'og_type': 'article' if endpoint == 'post' else 'website',
        'image': {
            'url': public_url('static', filename='images/social-cover.png'),
            'alt': site_text()['site_name'], 'width': 1200, 'height': 630,
        } if canonical else None,
    }


def _article_image(article_html: str, canonical: str) -> dict[str, str] | None:
    if '<img' not in article_html:
        return None
    root = html.fragment_fromstring(article_html, create_parent='div')
    for image in root.iter('img'):
        src = image.get('src', '').strip()
        if not src or missing_uploaded_image(src):
            continue
        try:
            absolute = urljoin(canonical, src)
            parts = urlsplit(absolute)
            if parts.scheme not in ('http', 'https') or not parts.hostname:
                continue
        except ValueError:
            continue
        if not src.startswith('/') and not urlsplit(src).netloc:
            continue
        result = {'url': absolute, 'alt': image.get('alt', '')}
        for dimension in ('width', 'height'):
            value = image.get(dimension, '')
            if re.fullmatch(r'[1-9][0-9]{0,5}', value):
                result[dimension] = value
        return result
    return None


def _utc_iso(value: datetime) -> str:
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None
            else value.astimezone(timezone.utc)).isoformat()


def post_seo(post: Post, article_html: str, headline: str) -> dict[str, Any]:
    seo = seo_context()
    canonical = seo['canonical_url']
    if request.endpoint != 'post' or not post.is_published or not canonical:
        return seo
    seo['image'] = _article_image(article_html, canonical) or seo['image']
    seo['structured_data'] = {
        '@context': 'https://schema.org',
        '@type': 'BlogPosting',
        'headline': headline,
        'image': seo['image']['url'],
        'datePublished': _utc_iso(post.timestamp),
        'dateModified': _utc_iso(post.updated_at or post.timestamp),
        'author': {'@type': 'Person', 'name': post.author.username},
        'publisher': {'@type': 'Organization', 'name': site_text()['site_name']},
        'mainEntityOfPage': {'@type': 'WebPage', '@id': canonical},
        'url': canonical,
    }
    return seo
