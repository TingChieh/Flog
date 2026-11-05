import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_article_fonts_are_self_hosted():
    templates = ROOT / 'app' / 'templates'
    for template in templates.rglob('*.html'):
        content = template.read_text().lower()
        assert 'fonts.googleapis.com' not in content
        assert 'fonts.gstatic.com' not in content

    css = (ROOT / 'app' / 'static' / 'fonts' / 'article-fonts.css').read_text()
    assert 'fonts.googleapis.com' not in css.lower()
    assert 'fonts.gstatic.com' not in css.lower()
    assert 'font-display: swap' in css
    assert "font-family: 'Noto Serif SC'" in css
    assert "font-family: 'Source Serif 4'" in css
    urls = re.findall(r'url\(["\']?([^"\')]+)', css)
    assert urls
    assert all((ROOT / 'app' / 'static' / 'fonts' / url).is_file() for url in urls)
    assert 'unicode-range:' in css
