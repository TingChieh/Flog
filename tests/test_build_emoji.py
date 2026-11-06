import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'build_emoji.py'

EMOJI_TEST = """\
# group: Smileys & Emotion
# subgroup: face-smiling
1F600                                                  ; fully-qualified     # 😀 E1.0 grinning face
263A FE0F                                              ; fully-qualified     # ☺️ E0.6 smiling face
263A                                                   ; unqualified         # ☺ E0.6 smiling face

# group: People & Body
# subgroup: hand-fingers-open
1F44B                                                  ; fully-qualified     # 👋 E0.6 waving hand
1F44B 1F3FB                                            ; fully-qualified     # 👋🏻 E1.0 waving hand: light skin tone
1F468 200D 1F469 200D 1F467                            ; fully-qualified     # 👨‍👩‍👧 E2.0 family: man, woman, girl

# group: Component
# subgroup: skin-tone
1F3FB                                                  ; component           # 🏻 E1.0 light skin tone

# group: Symbols
# subgroup: keycap
0031 FE0F 20E3                                         ; fully-qualified     # 1️⃣ E0.6 keycap: 1
2764 FE0F                                              ; fully-qualified     # ❤️ E0.6 red heart

# group: Flags
# subgroup: country-flag
1F1E8 1F1F3                                            ; fully-qualified     # 🇨🇳 E0.6 flag: China
"""

CLDR_ZH = """\
<?xml version="1.0" encoding="UTF-8" ?>
<ldml><annotations>
<annotation cp="😀">脸 | 笑 | 开心</annotation>
<annotation cp="😀" type="tts">嘻嘻笑</annotation>
<annotation cp="☺">脸 | 微笑</annotation>
<annotation cp="☺" type="tts">微笑</annotation>
<annotation cp="❤">心 | 爱</annotation>
<annotation cp="❤" type="tts">红心</annotation>
</annotations></ldml>
"""


def load_script():
    spec = importlib.util.spec_from_file_location('build_emoji', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_noto(tmp_path, names):
    noto = tmp_path / 'noto'
    (noto / '2D' / 'png' / '72').mkdir(parents=True, exist_ok=True)
    for name in names:
        (noto / '2D' / 'png' / '72' / name).write_text(f'png {name}')
    (noto / 'LICENSE').write_text('Apache License fixture')
    return noto


def run_build(tmp_path, names, **kwargs):
    build = load_script().build
    noto = make_noto(tmp_path, names)
    emoji_test = tmp_path / 'emoji-test.txt'
    emoji_test.write_text(EMOJI_TEST)
    cldr = tmp_path / 'zh.xml'
    cldr.write_text(CLDR_ZH)
    out = tmp_path / 'out'
    return build(noto, emoji_test, cldr, out, **kwargs), out


ALL_SVGS = ['emoji_u1f600.png', 'emoji_u263a.png', 'emoji_u1f44b.png',
            'emoji_u0031_20e3.png', 'emoji_u2764.png']


def read_data(out):
    text = (out / 'emoji-data.js').read_text()
    prefix = 'window.FlogEmoji = '
    assert text.startswith(prefix) and text.rstrip().endswith(';')
    return json.loads(text[len(prefix):].rstrip().rstrip(';'))


def test_copies_selected_images_under_stripped_keys(tmp_path):
    result, out = run_build(tmp_path, ALL_SVGS)
    copied = sorted(p.name for p in (out / 'emoji' / 'noto').glob('*.png'))
    assert copied == ['1f44b.png', '1f600.png', '263a.png', '2764.png', '31-20e3.png']
    assert result['copied'] == 5
    assert result['missing'] == []


def test_skips_flags_components_skin_tones_and_zwj_sequences(tmp_path):
    _, out = run_build(tmp_path, ALL_SVGS + [
        'emoji_u1f44b_1f3fb.png', 'emoji_u1f468_200d_1f469_200d_1f467.png',
        'emoji_u1f1e8_1f1f3.png', 'emoji_u1f3fb.png'])
    keys = (out / 'emoji-keys.js').read_text()
    for skipped in ('1f44b-1f3fb', '1f468', '1f1e8', '1f3fb'):
        assert skipped not in keys
    assert not list((out / 'emoji' / 'noto').glob('1f1e8*'))


def test_finds_files_named_with_or_without_the_variation_selector(tmp_path):
    result, out = run_build(tmp_path, [
        'emoji_u1f600.png', 'emoji_u263a_fe0f.png', 'emoji_u1f44b.png',
        'emoji_u0031_fe0f_20e3.png', 'emoji_u2764.png'])
    assert result['missing'] == []
    assert (out / 'emoji' / 'noto' / '263a.png').read_text() == 'png emoji_u263a_fe0f.png'


def test_missing_images_are_reported_and_left_out_of_the_data(tmp_path):
    result, out = run_build(tmp_path, ['emoji_u1f600.png'])
    assert '👋' in ''.join(result['missing'])
    data = read_data(out)
    chars = [item[0] for group in data['groups'] for item in group['items']]
    assert chars == ['😀']
    assert (out / 'emoji-keys.js').read_text().strip() == 'window.FlogEmojiKeys = "1f600";'


def test_data_groups_use_chinese_labels_and_keep_the_fully_qualified_char(tmp_path):
    _, out = run_build(tmp_path, ALL_SVGS)
    groups = read_data(out)['groups']
    assert [g['label'] for g in groups] == ['表情', '人物', '符号']
    smileys = {item[0]: item for item in groups[0]['items']}
    assert '☺️' in smileys
    assert smileys['😀'][1] == '嘻嘻笑'
    assert '开心' in smileys['😀'][2] and 'grinning face' in smileys['😀'][2]


def test_names_fall_back_to_english_when_cldr_has_no_entry(tmp_path):
    _, out = run_build(tmp_path, ALL_SVGS)
    keycap = [item for g in read_data(out)['groups'] for item in g['items']
              if item[0].startswith('1')][0]
    assert keycap[1] == 'keycap: 1'


def test_license_and_notice_are_written(tmp_path):
    _, out = run_build(tmp_path, ALL_SVGS)
    assert (out / 'emoji' / 'noto' / 'LICENSE').read_text() == 'Apache License fixture'
    notice = (out / 'emoji' / 'noto' / 'NOTICE').read_text()
    assert 'Noto Emoji' in notice and 'Apache License' in notice


def test_total_size_over_the_budget_fails_before_writing(tmp_path):
    with pytest.raises(SystemExit):
        run_build(tmp_path, ALL_SVGS, max_bytes=10)


def test_rebuilding_replaces_stale_files(tmp_path):
    _, out = run_build(tmp_path, ALL_SVGS)
    stale = out / 'emoji' / 'noto' / 'dead.png'
    stale.write_text('stale')
    run_build(tmp_path, ALL_SVGS)
    assert not stale.exists()


def test_license_comes_from_the_artwork_not_the_font(tmp_path):
    noto = make_noto(tmp_path, ['emoji_u1f600.png'])
    (noto / '2D' / 'svg').mkdir(parents=True)
    (noto / '2D' / 'svg' / 'LICENSE').write_text('Apache License artwork')
    (noto / 'LICENSE').write_text('SIL Open Font License')
    emoji_test = tmp_path / 'emoji-test.txt'
    emoji_test.write_text(EMOJI_TEST)
    cldr = tmp_path / 'zh.xml'
    cldr.write_text(CLDR_ZH)
    out = tmp_path / 'out'

    load_script().build(noto, emoji_test, cldr, out)

    assert (out / 'emoji' / 'noto' / 'LICENSE').read_text() == 'Apache License artwork'
