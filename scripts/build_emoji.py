"""Build the emoji set the site ships: Noto 72px PNGs plus the data the scripts read.

Usage (all three inputs are downloaded separately, see docs/superpowers/plans/2026-11-06-emoji.md):

    python -I scripts/build_emoji.py --noto DIR --emoji-test FILE --cldr-zh FILE

Standard library only. Output goes to app/static (--out to change):
    emoji/noto/<key>.png, LICENSE, NOTICE   the images
    emoji-keys.js                           which emoji can be swapped for an image
    emoji-data.js                           the picker's groups, names and keywords
"""
import argparse
import json
import re
import shutil
import sys
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
DEFAULT_MAX_BYTES = 8_000_000
NOTICE = """\
The emoji images in this directory come from Noto Emoji
(https://github.com/googlefonts/noto-emoji), Copyright Google Inc.,
licensed under the Apache License, Version 2.0. See LICENSE.

The images (the 72px PNGs) are copied unmodified and renamed after their code points.
Run scripts/build_emoji.py to regenerate them.
"""
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


def image_dir(noto_dir):
    """Noto's 72px PNGs: big enough for 2x screens at the sizes the site shows."""
    path = Path(noto_dir) / '2D' / 'png' / '72'
    if not path.is_dir():
        sys.exit(f'no 2D/png/72 directory under {noto_dir}')
    return path


def find_image(noto_dir, chars):
    """Noto names files emoji_u<hex>_<hex>.png, sometimes with the FE0F kept."""
    for variant in (chars, strip_selector(chars)):
        name = '_'.join(f'{ord(c):04x}' for c in variant)
        path = image_dir(noto_dir) / f'emoji_u{name}.png'
        if path.is_file():
            return path
    return None


def find_license(noto_dir):
    """The artwork is Apache 2.0 (kept beside the SVGs); the checkout's root
    LICENSE is the font's OFL."""
    beside_artwork = Path(noto_dir) / '2D' / 'svg' / 'LICENSE'
    return beside_artwork if beside_artwork.is_file() else Path(noto_dir) / 'LICENSE'


def build(noto_dir, emoji_test, cldr_zh, out_dir, max_bytes=DEFAULT_MAX_BYTES):
    entries = parse_emoji_test(Path(emoji_test).read_text(encoding='utf-8'))
    annotations = parse_cldr(Path(cldr_zh).read_text(encoding='utf-8'))

    chosen, missing = [], []
    for chars, group, name in entries:
        image = find_image(noto_dir, chars)
        if image is None:
            missing.append(chars)
        else:
            chosen.append((chars, group, name, image))

    total = sum(image.stat().st_size for *_, image in chosen)
    if total > max_bytes:
        sys.exit(f'{total} bytes of images is over the {max_bytes} byte budget; '
                 'narrow the groups instead of raising the budget')

    out_dir = Path(out_dir)
    images = out_dir / 'emoji' / 'noto'
    if images.exists():
        shutil.rmtree(images)
    images.mkdir(parents=True)
    groups = {}
    for chars, group, name, image in chosen:
        key = key_of(chars)
        shutil.copyfile(image, images / f'{key}.png')
        zh_name, words = annotations.get(key, (None, []))
        item = [chars, zh_name or name, ' '.join([*words, name.lower()])]
        groups.setdefault(group, []).append(item)

    shutil.copyfile(find_license(noto_dir), images / 'LICENSE')
    (images / 'NOTICE').write_text(NOTICE, encoding='utf-8')
    keys = ' '.join(key_of(chars) for chars, *_ in chosen)
    (out_dir / 'emoji-keys.js').write_text(
        f'window.FlogEmojiKeys = "{keys}";\n', encoding='utf-8')
    data = {'groups': [
        {'id': group.lower().replace(' & ', '-').replace(' ', '-'),
         'label': GROUP_LABELS[group], 'items': items}
        for group, items in groups.items()]}
    (out_dir / 'emoji-data.js').write_text(
        'window.FlogEmoji = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n',
        encoding='utf-8')
    return {'copied': len(chosen), 'missing': missing, 'bytes': total}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--noto', required=True, type=Path, help='a checkout of googlefonts/noto-emoji')
    parser.add_argument('--emoji-test', required=True, type=Path)
    parser.add_argument('--cldr-zh', required=True, type=Path)
    parser.add_argument('--out', type=Path, default=Path(__file__).parents[1] / 'app' / 'static')
    parser.add_argument('--max-bytes', type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)
    result = build(args.noto, args.emoji_test, args.cldr_zh, args.out, args.max_bytes)
    print(f"copied {result['copied']} images, {result['bytes']} bytes")
    if result['missing']:
        print(f"{len(result['missing'])} emoji have no Noto image: {''.join(result['missing'])}")


if __name__ == '__main__':
    main()
