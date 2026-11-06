from app.comment_markdown import render_comment


def test_allowed_formatting_is_rendered():
    html = str(render_comment('**b** *i* `c`\nsecond line'))
    assert '<strong>b</strong>' in html
    assert '<em>i</em>' in html
    assert '<code>c</code>' in html
    assert '<br>' in html


def test_quotes_lists_and_code_blocks():
    assert '<blockquote>' in str(render_comment('> quoted'))
    assert '<li>a</li>' in str(render_comment('- a\n- b'))
    assert '<pre><code>print(1)' in str(render_comment('```py\nprint(1)\n```'))


def test_raw_html_is_shown_as_text():
    html = str(render_comment('<script>alert(1)</script>Hello'))
    assert '<script' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;Hello' in html
    assert '<img' not in str(render_comment('<img src=x onerror=alert(1)>'))


def test_ampersands_and_comparisons_survive():
    html = str(render_comment('a & b <3 and 1 > 0'))
    assert 'a &amp; b &lt;3 and 1 &gt; 0' in html


def test_images_and_headings_are_not_allowed():
    assert '<img' not in str(render_comment('![x](http://example.com/x.png)'))
    html = str(render_comment('# Title'))
    assert '<h1' not in html and 'Title' in html


def test_links_are_marked_untrusted_and_open_elsewhere():
    html = str(render_comment('[x](https://example.com/a)'))
    assert 'href="https://example.com/a"' in html
    assert 'rel="nofollow ugc noopener"' in html
    assert 'target="_blank"' in html


def test_bare_urls_become_links_but_not_inside_code():
    assert 'href="https://example.com"' in str(render_comment('see https://example.com now'))
    assert '<a' not in str(render_comment('`https://example.com`'))


def test_dangerous_link_protocols_lose_their_href():
    html = str(render_comment('[x](javascript:alert(1))'))
    assert 'javascript:' not in html
    assert 'href=' not in html


def test_empty_text_renders_nothing():
    assert str(render_comment('')) == ''
    assert str(render_comment(None)) == ''
