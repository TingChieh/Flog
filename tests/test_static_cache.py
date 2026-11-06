import pytest


@pytest.mark.parametrize('path', [
    '/static/fonts/source-serif-4-normal-latin.woff2',
    '/static/fonts/noto-serif-sc-000.woff2',
    '/static/fonts/SmileySans-Oblique.ttf',
    '/static/vendor/katex/0.19.0/katex.min.css',
    '/static/vendor/vditor/4.0.1/dist/index.min.js',
])
def test_fonts_and_versioned_vendor_files_are_cached_for_a_year(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'public, max-age=31536000, immutable'


def test_a_conditional_request_for_a_font_keeps_the_long_cache(client):
    path = '/static/fonts/source-serif-4-normal-latin.woff2'
    etag = client.get(path).headers['ETag']

    response = client.get(path, headers={'If-None-Match': etag})

    assert response.status_code == 304
    assert 'immutable' in response.headers['Cache-Control']


@pytest.mark.parametrize('path', [
    '/static/style.css',
    '/static/fonts/article-fonts.css',
    '/static/site.js',
    '/static/vendor/photoswipe/photoswipe.css',
])
def test_the_sites_own_files_and_unversioned_vendor_files_keep_revalidating(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert 'immutable' not in response.headers.get('Cache-Control', '')
    assert 'no-cache' in response.headers['Cache-Control']


def test_pages_are_not_cached_by_this_rule(client, users):
    assert 'immutable' not in client.get('/').headers.get('Cache-Control', '')
