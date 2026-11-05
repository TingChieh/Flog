import pytest

from app.content import render_content


@pytest.mark.parametrize('language,label', [
    ('python', 'Python'), ('javascript', 'JavaScript'), ('js', 'JavaScript'),
    ('typescript', 'TypeScript'), ('ts', 'TypeScript'), ('html', 'HTML'),
    ('css', 'CSS'), ('sql', 'SQL'), ('bash', 'Bash'), ('sh', 'Bash'),
    ('shell', 'Bash'), ('json', 'JSON'), ('unknownlang', 'unknownlang'),
    ('mermaid', 'Mermaid'),
])
def test_fenced_code_has_friendly_language_label(application, language, label):
    with application.app_context():
        html = str(render_content(f'```{language}\nexample\n```', 'markdown'))
    assert f'data-language-label="{label}"' in html


@pytest.mark.parametrize('fence', ['```', '```text'])
def test_code_without_a_language_has_no_label_or_class(application, fence):
    with application.app_context():
        html = str(render_content(f'{fence}\nplain <b>text</b>\n```', 'markdown'))
    assert '<pre><code>plain &lt;b&gt;text&lt;/b&gt;\n</code></pre>' in html
    assert 'data-language-label' not in html


@pytest.mark.parametrize('language,source', [
    ('python', 'print("hello")'), ('javascript', 'const x = 1;'),
    ('typescript', 'const x: number = 1;'), ('html', '<p>Hello</p>'),
    ('css', 'body { color: red; }'), ('sql', 'SELECT * FROM posts;'),
    ('bash', 'echo hello'), ('json', '{"key": true}'),
])
def test_fenced_code_is_highlighted_with_language(application, language, source):
    with application.app_context():
        html = str(render_content(f'```{language}\n{source}\n```', 'markdown'))
    assert '<pre><code' in html
    assert f'language-{language}' in html
    assert '<span class=' in html


def test_unknown_language_and_code_injection_remain_text(application):
    with application.app_context():
        html = str(render_content('```unknownlang\n<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n```\n\n<img src=x onerror=alert(2)>\n<script>alert(3)</script>', 'markdown'))
    assert 'language-unknownlang' in html
    assert '&lt;script&gt;' in html
    assert '&lt;img' in html
    assert '<script' not in html
    assert 'onerror=alert(2)' not in html


def test_classes_are_restricted_to_highlighting_markup(application):
    with application.app_context():
        html = str(render_content('<p class="evil" onclick="alert(1)">text</p><span class="evil" onmouseover="alert(1)">x</span>', 'markdown'))
    assert 'class="evil"' not in html
    assert 'onclick' not in html
    assert 'onmouseover' not in html
