"""Public URL and SEO metadata helpers (single source of truth for head tags and feeds)."""
from typing import Any

from flask import current_app, request, url_for

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
        return 'noindex, nofollow'
    return None


def seo_context() -> dict[str, str | None]:
    endpoint = request.endpoint
    return {
        'canonical_url': canonical_url(),
        'robots': robots_directive(),
        'og_type': 'article' if endpoint == 'post' else 'website',
    }
