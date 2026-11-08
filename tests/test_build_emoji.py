import importlib.util
import json
from pathlib import Path

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


def run_build(tmp_path):
    emoji_test = tmp_path / 'emoji-test.txt'
    emoji_test.write_text(EMOJI_TEST)
    cldr = tmp_path / 'zh.xml'
    cldr.write_text(CLDR_ZH)
    out = tmp_path / 'out'
    out.mkdir()
    return load_script().build(emoji_test, cldr, out), out


def read_data(out):
    text = (out / 'emoji-data.js').read_text()
    prefix = 'window.FlogEmoji = '
    assert text.startswith(prefix) and text.rstrip().endswith(';')
    return json.loads(text[len(prefix):].rstrip().rstrip(';'))


def test_skips_flags_components_skin_tones_and_zwj_sequences(tmp_path):
    result, out = run_build(tmp_path)
    chars = [item[0] for group in read_data(out)['groups'] for item in group['items']]
    assert chars == ['😀', '☺️', '👋', '1️⃣', '❤️']
    assert result['emoji'] == 5


def test_writes_only_the_picker_data(tmp_path):
    _, out = run_build(tmp_path)
    assert [p.name for p in out.iterdir()] == ['emoji-data.js']


def test_data_groups_use_chinese_labels_and_keep_the_fully_qualified_char(tmp_path):
    _, out = run_build(tmp_path)
    groups = read_data(out)['groups']
    assert [g['label'] for g in groups] == ['表情', '人物', '符号']
    smileys = {item[0]: item for item in groups[0]['items']}
    assert '☺️' in smileys
    assert smileys['😀'][1] == '嘻嘻笑'
    assert '开心' in smileys['😀'][2] and 'grinning face' in smileys['😀'][2]


def test_names_fall_back_to_english_when_cldr_has_no_entry(tmp_path):
    _, out = run_build(tmp_path)
    keycap = [item for g in read_data(out)['groups'] for item in g['items']
              if item[0].startswith('1')][0]
    assert keycap[1] == 'keycap: 1'
