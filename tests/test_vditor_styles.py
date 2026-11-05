from pathlib import Path
import re

STYLESHEET = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'style.css'
MARKER = '/* Vditor: the editor follows the site tokens. */'
SERIF_STACK = "'Source Serif 4', 'Noto Serif SC', 'Songti SC', Georgia, serif"


def vditor_section(css):
    start = css.index(MARKER)
    end = css.find('\n/* ', start + len(MARKER))
    return css[start:] if end == -1 else css[start:end]


def rule_bodies(css, selector):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
    return [m.group(2) for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css)
            if selector in [s.strip() for s in m.group(1).split(',')]]


def test_old_easymde_and_codemirror_rules_are_gone():
    css = STYLESHEET.read_text()
    for name in ('EasyMDEContainer', 'CodeMirror', 'editor-toolbar',
                 'editor-preview', 'markdown-editor--dragging'):
        assert name not in css, name


def test_vditor_colours_come_from_the_site_tokens():
    block = vditor_section(STYLESHEET.read_text())
    variables = rule_bodies(block, '.admin-form .vditor')[0]
    for pair in (
        '--border-color: var(--border);',
        '--textarea-background-color: var(--surface);',
        '--textarea-text-color: var(--text-primary);',
        '--toolbar-icon-color: var(--text-secondary);',
        '--toolbar-icon-hover-color: var(--text-primary);',
        '--ir-link-color: var(--link-color);',
        '--panel-background-color: var(--surface);',
    ):
        assert pair in variables, pair
    # no hard-coded editor palette leaks through
    assert '#' not in re.sub(r'--[a-z-]+: var\([^)]*\);', '', variables).replace('}', '')


def test_editing_area_uses_the_serif_body_font():
    block = vditor_section(STYLESHEET.read_text())
    body = rule_bodies(block, '.admin-form .vditor-reset')[0]
    assert f'font-family: {SERIF_STACK};' in body
    assert 'color: var(--text-primary);' in body


def test_toolbar_keeps_its_dropdowns_and_wysiwyg_entry_is_hidden():
    block = vditor_section(STYLESHEET.read_text())
    # overflow clipping on the toolbar would cut off the heading and mode panels
    assert 'overflow' not in ''.join(rule_bodies(block, '.admin-form .vditor-toolbar'))
    assert '@media (width <= 768px)' in block
    assert 'button[data-mode="wysiwyg"]' in block


def test_content_theme_colours_are_overridden_with_site_tokens():
    block = vditor_section(STYLESHEET.read_text())
    assert 'background-color: var(--surface-muted);' in rule_bodies(
        block, '.admin-form .vditor-reset code:not(.hljs):not(.highlight-chroma)')[0]
    assert 'border: 1px solid var(--border);' in rule_bodies(
        block, '.admin-form .vditor-reset table td')[0]
    assert 'background-color: var(--border);' in rule_bodies(
        block, '.admin-form .vditor-reset hr')[0]
    assert 'background-color: transparent;' in rule_bodies(
        block, '.admin-form .vditor-reset table tr')[0]


def test_editor_blocks_keep_the_pre_wrap_of_the_editing_surface():
    # The global "p { white-space: normal }" otherwise breaks the caret on Enter.
    section = vditor_section(STYLESHEET.read_text())
    bodies = rule_bodies(section, '.admin-form .vditor-reset p')
    assert any('white-space: inherit' in body for body in bodies)
