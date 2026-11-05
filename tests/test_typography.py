from pathlib import Path
import re

STYLESHEET = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'style.css'
SERIF = "'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif"


def rules(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    for match in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        yield match.group(1).strip(), match.group(2)


def bodies(css, selector):
    return [body for sel, body in rules(css)
            if selector in [s.strip() for s in sel.split(',')]]


def test_one_serif_token_is_the_base_font_of_the_site_and_the_admin():
    css = STYLESHEET.read_text()
    assert f'--font-serif: {SERIF};' in bodies(css, ':root')[0]
    base = bodies(css, 'body.public-site')[0]
    assert 'font-family: var(--font-serif);' in base
    assert '--bs-body-font-family: var(--font-serif);' in base


def test_no_editorial_rule_switches_back_to_the_system_sans():
    css = STYLESHEET.read_text()
    offenders = [
        sel for sel, body in rules(css)
        if 'font-family: var(--system-font)' in body
        and re.search(r'\.public-site|\.admin-|\.search-dialog|\.site-footer|\.publication', sel)
    ]
    assert offenders == []


def test_titles_and_list_text_have_no_sans_tracking_left_over():
    css = STYLESHEET.read_text()
    for selector in ('.public-site .editorial-post__title',
                     '.public-site .archive-year',
                     '.admin-workspace__header h1',
                     '.admin-list__main strong'):
        body = ''.join(bodies(css, selector))
        assert body, selector
        assert 'letter-spacing: -.04em' not in body
        assert 'letter-spacing: -.035em' not in body
        assert 'font-family: var(--system-font)' not in body


def test_georgia_only_serif_variants_are_gone():
    css = STYLESHEET.read_text()
    for selector in ('.public-site .public-page .page-body',
                     '.public-site .public-page .empty-state'):
        body = bodies(css, selector)[0]
        assert 'Georgia, \'Noto Serif SC\'' not in body
        assert 'font-family: var(--font-serif);' in body


def test_search_dialog_is_editorial():
    css = STYLESHEET.read_text()
    dialog = ''.join(bodies(css, '.search-dialog'))
    assert 'border-radius: 16px;' in dialog
    assert 'background: var(--surface);' in dialog
    title = bodies(css, '.search-dialog__header h2')[-1]
    assert 'font-size: 22px;' in title and 'font-weight: 600;' in title
    field = bodies(css, '.search-dialog input')[-1]
    assert 'font: inherit;' in field and 'font-size: 18px;' in field
    assert 'var(--page-bg)' not in field
    selected = ''.join(bodies(css, '.search-dialog__results a.is-selected'))
    assert 'border-left: 2px solid var(--text-primary);' in selected
    assert 'outline: 2px solid var(--link-color)' not in selected


def test_footer_text_is_one_family_one_weight():
    css = STYLESHEET.read_text()
    logout = bodies(css, '.site-footer .btn-link')
    assert any('font-weight: 400;' in b and 'text-decoration: underline;' in b for b in logout)


def test_publication_controls_share_one_size_and_alignment():
    css = STYLESHEET.read_text()
    controls = bodies(css, '.publication-controls')[-1]
    assert 'font-size: 14px;' in controls and 'align-items: center;' in controls
    for selector in ('.publication-status', '.draft-save-status'):
        assert 'font-size: inherit;' in bodies(css, selector)[-1] or \
            'font-size: inherit;' in ''.join(
                b for sel, b in rules(css)
                if selector in [s.strip() for s in sel.split(',')])


def test_search_input_hides_the_native_blue_clear_button():
    css = STYLESHEET.read_text()
    assert bodies(css, '.search-dialog input[type="search"]::-webkit-search-cancel-button')


def test_publication_switch_and_update_button_are_spaced_in_their_form():
    css = STYLESHEET.read_text()
    forms = ''.join(bodies(css, '.publication-controls form'))
    assert 'display: flex;' in forms and 'gap: 16px;' in forms and 'align-items: center;' in forms


def test_full_screen_search_dialog_on_phones_keeps_square_corners():
    css = STYLESHEET.read_text()
    tail = css[css.index('/* Typography: search dialog'):]
    mobile = tail[tail.index('@media (max-width: 576px)'):]
    assert 'border-radius: 0;' in mobile.split('}')[0]


def test_article_and_comment_headings_use_the_same_weight_as_list_titles():
    css = STYLESHEET.read_text()
    for selector in ('.article-body h1', '.article-body h2', '.comments-section__heading h2'):
        assert any('font-weight: 700;' in b for b in bodies(css, selector)), selector
