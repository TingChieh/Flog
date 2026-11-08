"""Build the data behind the emoji picker: groups, Chinese names and search keywords.

The picker inserts plain emoji characters and every system draws them its own way, so no
images are involved. Both inputs are downloaded separately, see docs/superpowers/plans/2026-11-06-emoji.md:

    python -I scripts/build_emoji.py --emoji-test FILE --cldr-zh FILE

Standard library only. Output goes to app/static (--out to change):
    emoji-data.js    the picker's groups, names and keywords
"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ZWJ = '‍'
VS16 = '️'
SKIN_TONES = {chr(cp) for cp in range(0x1F3FB, 0x1F400)}
SKIPPED_GROUPS = {'Component', 'Flags'}
GROUP_LABELS = {
    'Smileys & Emotion': '表情',
    'People & Body': '人物',
    'Animals & Nature': '动物与自然',
    'Food & Drink': '食物',
    'Travel & Places': '旅行',
    'Activities': '活动',
    'Objects': '物品',
    'Symbols': '符号',
}
_LINE = re.compile(
    r'^(?P<cps>[0-9A-F ]+?)\s*;\s*(?P<status>[\w-]+)\s*#\s*\S+\s+E[\d.]+\s+(?P<name>.+)$')


def strip_selector(chars):
    return chars.replace(VS16, '')


def key_of(chars):
    return '-'.join(f'{ord(c):x}' for c in strip_selector(chars))


def parse_emoji_test(text):
    """Fully-qualified emoji worth offering: (chars, group, name)."""
    group = None
    entries = []
    for line in text.splitlines():
        if line.startswith('# group:'):
            group = line.split(':', 1)[1].strip()
            continue
        match = _LINE.match(line)
        if not match or match['status'] != 'fully-qualified':
            continue
        if group in SKIPPED_GROUPS or group not in GROUP_LABELS:
            continue
        chars = ''.join(chr(int(cp, 16)) for cp in match['cps'].split())
        if ZWJ in chars or any(c in SKIN_TONES for c in chars):
            continue
        entries.append((chars, group, match['name'].strip()))
    return entries


def parse_cldr(xml_text):
    """{key: (short name, [keywords])} from a CLDR annotations file."""
    names, keywords = {}, {}
    for node in ET.fromstring(xml_text).iter('annotation'):
        key = key_of(node.get('cp', ''))
        text = (node.text or '').strip()
        if node.get('type') == 'tts':
            names[key] = text
        else:
            keywords[key] = [word.strip() for word in text.split('|') if word.strip()]
    return {key: (names.get(key), keywords.get(key, [])) for key in set(names) | set(keywords)}


def build(emoji_test, cldr_zh, out_dir):
    entries = parse_emoji_test(Path(emoji_test).read_text(encoding='utf-8'))
    annotations = parse_cldr(Path(cldr_zh).read_text(encoding='utf-8'))

    groups = {}
    for chars, group, name in entries:
        zh_name, words = annotations.get(key_of(chars), (None, []))
        item = [chars, zh_name or name, ' '.join([*words, name.lower()])]
        groups.setdefault(group, []).append(item)

    data = {'groups': [
        {'id': group.lower().replace(' & ', '-').replace(' ', '-'),
         'label': GROUP_LABELS[group], 'items': items}
        for group, items in groups.items()]}
    out_dir = Path(out_dir)
    (out_dir / 'emoji-data.js').write_text(
        'window.FlogEmoji = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n',
        encoding='utf-8')
    return {'emoji': len(entries)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--emoji-test', required=True, type=Path)
    parser.add_argument('--cldr-zh', required=True, type=Path)
    parser.add_argument('--out', type=Path, default=Path(__file__).parents[1] / 'app' / 'static')
    args = parser.parse_args(argv)
    result = build(args.emoji_test, args.cldr_zh, args.out)
    print(f"wrote {result['emoji']} emoji")


if __name__ == '__main__':
    main()
