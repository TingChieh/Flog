from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'vendor' / 'vditor' / '4.0.1'
EXPECTED = {
    'dist/index.min.js',
    'dist/index.css',
    'dist/js/lute/lute.min.js',
    'dist/js/i18n/zh_CN.js',
    'dist/js/icons/ant.js',
    'dist/css/content-theme/light.css',
    'dist/css/content-theme/dark.css',
    'dist/js/highlight.js/styles/github.min.css',
    'LICENSE',
    'README.md',
}


def vendored_files():
    return {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file()}


def test_exactly_the_needed_vditor_files_are_vendored():
    assert vendored_files() == EXPECTED
    for name in EXPECTED:
        assert (ROOT / name).stat().st_size > 0, name


def test_vditor_license_and_provenance_are_recorded():
    assert 'MIT' in (ROOT / 'LICENSE').read_text()
    readme = (ROOT / 'README.md').read_text()
    assert '4.0.1' in readme
    assert 'sha512-' in readme


def test_no_optional_renderers_are_vendored():
    # highlight.js, mermaid, katex, mathjax, echarts ... would add ~20 MB.
    for name in ('mermaid', 'katex', 'mathjax', 'echarts'):
        assert not (ROOT / 'dist' / 'js' / name).exists()
    assert not list((ROOT / 'dist' / 'js' / 'highlight.js').glob('*.js'))
    assert sum((ROOT / n).stat().st_size for n in EXPECTED) < 5 * 1024 * 1024


def test_editor_script_makes_no_external_requests():
    script = (Path(__file__).resolve().parents[1] / 'app' / 'static'
              / 'markdown-editor.js').read_text()
    assert 'http://' not in script and 'https://' not in script
