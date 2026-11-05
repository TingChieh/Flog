from pathlib import Path

from lxml import html as lxml_html

from app import db
from app.models import Page, Post
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app' / 'static'
KATEX = 'vendor/katex/0.19.0'
MERMAID = 'vendor/mermaid/12.2.0'


def test_vendored_libraries_are_complete():
    for relative in (f'{KATEX}/katex.min.js', f'{KATEX}/katex.min.css',
                     f'{KATEX}/LICENSE', f'{KATEX}/README.md',
                     f'{MERMAID}/mermaid.min.js', f'{MERMAID}/LICENSE',
                     f'{MERMAID}/README.md', 'rich-content.js'):
        assert (STATIC / relative).is_file(), relative
    fonts = list((STATIC / KATEX / 'fonts').glob('*.woff2'))
    assert len(fonts) >= 19
    css = (STATIC / KATEX / 'katex.min.css').read_text()
    for font in fonts:
        assert font.name in css


def test_vendored_versions_are_recorded():
    assert '0.19.0' in (STATIC / KATEX / 'README.md').read_text()
    assert '12.2.0' in (STATIC / MERMAID / 'README.md').read_text()


def script_of(document):
    scripts = document.xpath('//script[contains(@src, "rich-content.js")]')
    assert len(scripts) == 1
    return scripts[0]


def check(script):
    assert script.get('defer') is not None
    assert script.get('data-katex-base') == f'/static/{KATEX}'
    assert script.get('data-mermaid-src') == f'/static/{MERMAID}/mermaid.min.js'
    assert (STATIC / MERMAID / 'mermaid.min.js').is_file()


def test_articles_and_pages_load_the_rich_content_script(
        client, application, users):
    with application.app_context():
        db.session.add(Page(title='P', slug='p', kind='content', body='x',
                            body_format='markdown', is_published=True))
        db.session.commit()
    for path in (f'/post/{users["post"]}', '/p'):
        document = lxml_html.fromstring(client.get(path).get_data(as_text=True))
        check(script_of(document))


def test_admin_page_preview_loads_it_too(client, application, users):
    with application.app_context():
        page = Page(title='P', slug='p', kind='content', body='x',
                    body_format='markdown', is_published=True)
        db.session.add(page)
        db.session.commit()
        page_id = page.id
    login(client, 'admin')
    document = lxml_html.fromstring(
        client.get(f'/admin/pages/{page_id}/preview').get_data(as_text=True))
    check(script_of(document))


def test_rendered_formulas_and_diagrams_reach_the_article_page(
        client, application, users):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body_format = 'markdown'
        post.body = 'Inline $a_1$.\n\n- [x] done\n\n```mermaid\ngraph TD\nA-->B\n```\n'
        db.session.commit()
    document = lxml_html.fromstring(
        client.get(f'/post/{users["post"]}').get_data(as_text=True))
    assert document.xpath('//span[@class="math math-inline"]')
    assert document.xpath('//li[@class="task-list-item"]/input[@checked]')
    assert document.xpath('//pre/code[@class="language-mermaid"]')
