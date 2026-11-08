from pathlib import Path

from lxml import html as lxml_html

STYLESHEET = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'style.css'
SERIF_STACK = "'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif"


def get_page(client, path, **kwargs):
    response = client.get(path, **kwargs)
    return response, lxml_html.fromstring(response.get_data(as_text=True))


def test_every_page_loads_the_article_fonts_once(client, users):
    home = client.get('/').get_data(as_text=True)
    article = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    assert home.count('fonts/article-fonts.css') == 1
    assert article.count('fonts/article-fonts.css') == 1


def test_latin_brand_font_is_preloaded(client):
    page = lxml_html.fromstring(client.get('/').get_data(as_text=True))
    preload = page.xpath('//link[@rel="preload"][@as="font"]')
    assert preload
    assert preload[0].get('href').endswith('fonts/source-serif-4-normal-latin.woff2')
    assert preload[0].get('crossorigin') is not None


def test_brand_and_menu_links_use_the_serif_stack():
    css = STYLESHEET.read_text()
    assert f'.public-site .site-brand {{ font-family: {SERIF_STACK};' in css
    assert f'.public-site .site-nav__links a {{ font-family: {SERIF_STACK};' in css


def test_desktop_breakpoint_shows_links_inline():
    css = STYLESHEET.read_text()
    assert '@media (width >= 1200px)' in css
    block = css[css.index('@media (width >= 1200px)'):]
    assert '.public-site .nav-toggle { display: none; }' in block
    assert '.public-site .site-nav__menu[hidden]' in block
    # Bootstrap's [hidden] rule is !important, so the override must be too.
    assert 'display: flex !important;' in block


from app import db
from app.models import User


def assert_public_form(page, label):
    assert not page.xpath('//header[contains(@class, "hero--page")]')
    assert page.xpath('//section[contains(@class, "form-shell") and contains(@class, "public-page")]')
    assert page.xpath(f'//div[@class="public-label"][normalize-space()="{label}"]')
    assert len(page.xpath('//h1')) == 1


def test_password_reset_pages_use_public_form_shell(client, application, users):
    response, page = get_page(client, '/reset_password_request')
    assert response.status_code == 200
    assert_public_form(page, '账号')
    with application.app_context():
        token = db.session.get(User, users['author']).get_reset_password_token()
    response, page = get_page(client, f'/reset_password/{token}')
    assert response.status_code == 200
    assert_public_form(page, '账号')


def assert_public_list(page, label):
    assert not page.xpath('//header[contains(@class, "hero--page")]')
    assert page.xpath('//section[contains(@class, "content-section") and contains(@class, "public-page")]')
    assert page.xpath(f'//div[@class="public-label"][normalize-space()="{label}"]')
    assert not page.xpath('//ul[contains(@class, "pagination")]')


def test_category_page_is_laid_out_like_the_archive(client, users):
    response, page = get_page(client, '/category/1')
    assert response.status_code == 200
    assert not page.xpath('//header[contains(@class, "hero--page")]')
    assert page.xpath('//section[contains(@class, "content-section") and contains(@class, "archive")]')
    assert page.xpath('//div[@class="public-label"][normalize-space()="分类"]')
    assert page.xpath('//h1[@id="page-title"]/text()') == ['General']
    assert page.xpath('//ul[contains(@class, "archive-list")]//a[contains(@class, "archive-entry__title")]')


from app.models import Post


def test_500_page_matches_the_404_structure(application):
    from app.errors import internal_error
    with application.test_request_context('/'):
        body, status = internal_error(RuntimeError('boom'))
    page = lxml_html.fromstring(body)
    assert status == 500
    assert not page.xpath('//header[contains(@class, "hero--page")]')
    assert page.xpath('//section[contains(@class, "public-error")]')
    assert page.xpath('//p[@class="public-label"][normalize-space()="500"]')


def test_new_public_page_strings_are_chinese(client, application, users):
    _, reset = get_page(client, '/reset_password_request')
    assert reset.xpath('//div[@class="public-label"]')[0].text_content() == '账号'


def test_site_ignores_the_browser_language(client, users):
    for language in ('en', 'es', 'zh'):
        page = lxml_html.fromstring(
            client.get('/archive', headers={'Accept-Language': language}).get_data(as_text=True))
        assert page.get('lang') == 'zh'
        assert page.xpath('//h1/text()') == ['归档']
