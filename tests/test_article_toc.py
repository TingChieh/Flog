from urllib.parse import unquote
import shutil
import subprocess
from pathlib import Path

import pytest
from lxml import html

from app import db
from app.models import Post


def article(client, application, users, body, body_format='markdown'):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = body
        post.body_format = body_format
        db.session.commit()
    return html.fromstring(client.get(f"/post/{users['post']}").data)


def test_chinese_duplicate_and_symbol_headings_have_unique_links(client, application, users):
    page = article(client, application, users, '## 中文 标题\n\n### 中文 标题\n\n## 😀 ✨\n\n### 😀 ✨\n\n#### ignored')
    headings = page.xpath('//div[contains(@class,"article-body")]//*[self::h2 or self::h3]')
    ids = [h.get('id') for h in headings]
    assert ids == ['中文-标题', '中文-标题-2', 'section', 'section-2']
    links = page.xpath('(//nav[contains(@class,"article-toc")])[1]//a')
    assert [unquote(a.get('href')[1:]) for a in links] == ids
    assert [a.text_content() for a in links] == ['中文 标题', '中文 标题', '😀 ✨', '😀 ✨']


def test_existing_ids_are_preserved_and_reserved_before_generation(client, application, users):
    page = article(client, application, users, '## 重复\n\n## 自定义 {#重复}\n\n### Another {#legacy-anchor}\n\n## Again {#legacy-anchor-2}')
    assert [h.get('id') for h in page.xpath('//div[contains(@class,"article-body")]//*[self::h2 or self::h3]')] == ['重复-2', '重复', 'legacy-anchor', 'legacy-anchor-2']


def test_legacy_html_heading_ids_are_preserved(client, application, users):
    page = article(client, application, users, '<h2 id="old:anchor">Old</h2><h3 id="中文">中文</h3><h2>Third</h2>', 'html')
    assert [h.get('id') for h in page.xpath('//div[contains(@class,"article-body")]//*[self::h2 or self::h3]')] == ['old:anchor', '中文', 'third']


@pytest.mark.parametrize('body', ['', '# One\n\n## Two\n\n#### Four\n\n### Three', '## One\n\n## Two'])
def test_fewer_than_three_h2_h3_hide_toc(client, application, users, body):
    page = article(client, application, users, body)
    assert not page.xpath('//nav[contains(@class,"article-toc")]')


def test_heading_text_and_ids_cannot_inject_markup_or_attributes(client, application, users):
    page = article(client, application, users, '<h2 id="x&quot; onmouseover=&quot;alert(1)">Safe &lt;img src=x onerror=alert(1)&gt;</h2><h3 onclick="alert(2)">Next</h3><h2>Third</h2>', 'html')
    heading = page.xpath('//div[contains(@class,"article-body")]//h2')[0]
    assert heading.get('id') == 'x" onmouseover="alert(1)'
    assert heading.get('onmouseover') is None
    assert not page.xpath('//nav[contains(@class,"article-toc")]//img')
    assert not page.xpath('//div[contains(@class,"article-body")]//*[@onclick or @onmouseover or @onerror] | //nav[contains(@class,"article-toc")]//*[@onclick or @onmouseover or @onerror]')
    link = page.xpath('//nav[contains(@class,"article-toc")]//a')[0]
    assert unquote(link.get('href')[1:]) == heading.get('id')
    assert '<img' in link.text_content()


@pytest.mark.parametrize(('locale', 'title'), [('zh', '目录'), ('en', '目录')])
def test_toc_title_is_chinese_whatever_the_browser_language(client, application, users, locale, title):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = '## One\n\n### Two\n\n## Three'
        post.body_format = 'markdown'
        db.session.commit()
    page = html.fromstring(client.get(
        f"/post/{users['post']}", headers={'Accept-Language': locale}).data)
    assert page.xpath('//div[contains(@class,"article-toc__title")]/text()') == [title]
    assert page.xpath('//details[contains(@class,"article-toc-mobile")]/summary/text()') == [title]


def test_current_heading_updates_both_tocs_when_scrolling():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required to execute article JavaScript')
    script = Path('app/static/article-enhancements.js').resolve()
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
let tops = [0, 200, 400];
const sections = ['one', 'two', 'three'].map((id, i) => ({
  id, getBoundingClientRect: () => ({top: tops[i]})
}));
const links = [...sections, ...sections].map(section => ({
  attributes: {href: '#' + section.id},
  getAttribute(name) { return this.attributes[name]; },
  setAttribute(name, value) { this.attributes[name] = value; },
  removeAttribute(name) { delete this.attributes[name]; }
}));
const handlers = {};
const body = {querySelectorAll: () => sections};
const document = {
  querySelector(selector) { return selector === '.article-body' ? body : null; },
  querySelectorAll() { return links; },
  documentElement: {style: {setProperty() {}}}
};
const window = {addEventListener(name, handler) { handlers[name] = handler; }};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {
  document, window, requestAnimationFrame: callback => callback()
});
function current() { return links.filter(link => link.attributes['aria-current'] === 'location').map(link => link.attributes.href); }
assert.deepStrictEqual(current(), ['#one', '#one']);
tops = [-300, -100, 100];
handlers.scroll();
assert.deepStrictEqual(current(), ['#two', '#two']);
tops = [-500, -300, -100];
handlers.scroll();
assert.deepStrictEqual(current(), ['#three', '#three']);
"""
    subprocess.run([node, '-e', harness, str(script)], check=True)
