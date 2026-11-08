"""Python-Markdown extensions: math and task lists."""
import re
import xml.etree.ElementTree as etree

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor
from markupsafe import escape


# $$ ... $$ on its own lines (multi-line) or on a single line.
BLOCK_MATH = re.compile(
    r'^\$\$[ \t]*\n(?P<multi>.+?)\n\$\$[ \t]*$|^\$\$(?P<single>[^\n]+?)\$\$[ \t]*$',
    re.MULTILINE | re.DOTALL)
# $...$ : the opening $ is followed by a non-space, the closing $ follows a
# non-space and is not followed by a digit, so prices such as "$5 and $6"
# stay text. Backslash escapes (\$) never open or close a formula.
INLINE_MATH = re.compile(
    r'(?<![\\$])\$(?![\s$])((?:\\.|[^$\\\n])+?)(?<![\s\\])\$(?![\d$])')
CODE_SPAN = re.compile(r'(`+)(?:(?!\1).)+?\1')
INDENTED = re.compile(r'^(?: {4}|\t)')


class MathPreprocessor(Preprocessor):
    """Protect formulas from Markdown by moving them into the HTML stash."""

    def _block(self, match):
        tex = (match.group('multi') or match.group('single')).strip()
        html = f'<p class="math math-block">{escape(tex)}</p>'
        return f'\n\n{self.md.htmlStash.store(html)}\n\n'

    def _inline(self, match):
        html = f'<span class="math math-inline">{escape(match.group(1))}</span>'
        return self.md.htmlStash.store(html)

    def _inline_line(self, line):
        if INDENTED.match(line) or '$' not in line:
            return line
        out, last = [], 0
        for code in CODE_SPAN.finditer(line):
            out.append(INLINE_MATH.sub(self._inline, line[last:code.start()]))
            out.append(code.group(0))
            last = code.end()
        out.append(INLINE_MATH.sub(self._inline, line[last:]))
        return ''.join(out)

    def run(self, lines):
        text = BLOCK_MATH.sub(self._block, '\n'.join(lines))
        return [self._inline_line(line) for line in text.split('\n')]


class MathExtension(Extension):
    def extendMarkdown(self, md):
        # Typora writes a literal dollar sign as "\$"; Python-Markdown would keep the backslash.
        if '$' not in md.ESCAPED_CHARS:
            md.ESCAPED_CHARS.append('$')
        # After the fenced code preprocessor (25) has stashed code blocks.
        md.preprocessors.register(MathPreprocessor(md), 'flog_math', 20)


LIST_MARKER = re.compile(r'^( *)(?:[*+-]|\d{1,9}[.)])( +|$)')
FENCE = re.compile(r'^ *(`{3,}|~{3,})')


class ListIndentPreprocessor(Preprocessor):
    """Accept CommonMark list continuation indents.

    Python-Markdown only keeps a paragraph or sub-list inside a list item when
    it is indented by a multiple of four spaces, while CommonMark (and the
    Vditor editor) indent to the item's content column, e.g. three spaces
    under "1. ". Lines indented between the content column and the next
    multiple of four are moved to that multiple. A list marker that directly
    follows such a continuation paragraph gets a blank line before it, since
    Python-Markdown would otherwise read it as paragraph text.
    """

    def run(self, lines):
        out, items, fence_delta = [], [], None
        blank_before = False
        in_block = False  # last line is a continuation block of a list item
        for line in lines:
            if fence_delta is not None:
                fence = FENCE.match(line)
                out.append(self._shift(line, fence_delta))
                if fence:
                    fence_delta = None
                continue
            if not line.strip():
                out.append(line)
                blank_before = True
                continue
            indent = len(line) - len(line.lstrip(' '))
            while items and indent < items[-1]:
                items.pop()
            depth = len(items)
            delta = 0
            if depth and items[-1] <= indent < 4 * depth:
                delta = 4 * depth - indent
            marker = LIST_MARKER.match(line)
            if marker and in_block and not blank_before:
                out.append('')
            out.append(self._shift(line, delta))
            if marker:
                in_block = False
            elif depth and indent >= items[-1]:
                in_block = in_block or blank_before
            else:
                in_block = False
            blank_before = False
            if FENCE.match(line):
                fence_delta = delta
                continue
            if marker:
                width = len(marker.group(0)) - len(marker.group(1))
                spaces = len(marker.group(2))
                # Five or more spaces after the marker is an indented code
                # block inside the item: its content column is one space in.
                items.append(indent + width - (spaces if spaces > 4 else 0)
                             + (1 if spaces > 4 else 0))
        return out

    @staticmethod
    def _shift(line, delta):
        return ' ' * delta + line if delta > 0 else line


class ListIndentExtension(Extension):
    def extendMarkdown(self, md):
        # After whitespace normalisation (30), before fenced code (25).
        md.preprocessors.register(ListIndentPreprocessor(md), 'flog_list_indent', 27)


TASK_MARKER = re.compile(r'^\[([ xX])\][ \t]+')


class TaskListTreeprocessor(Treeprocessor):
    """Turn leading "[ ]" / "[x]" in list items into read-only checkboxes."""

    def _convert(self, item):
        if item.text and TASK_MARKER.match(item.text):
            holder = item
        elif not (item.text or '').strip() and len(item) \
                and item[0].tag == 'p' and item[0].text \
                and TASK_MARKER.match(item[0].text):
            holder = item[0]
        else:
            return False
        marker = TASK_MARKER.match(holder.text)
        box = etree.Element('input', {'type': 'checkbox', 'disabled': 'disabled'})
        if marker.group(1) in 'xX':
            box.set('checked', 'checked')
        box.tail = ' ' + holder.text[marker.end():]
        holder.text = None
        holder.insert(0, box)
        item.set('class', 'task-list-item')
        return True

    def run(self, root):
        for lst in [e for e in root.iter() if e.tag in ('ul', 'ol')]:
            converted = [self._convert(item) for item in lst.findall('li')]
            if any(converted):
                lst.set('class', 'task-list')


class TaskListExtension(Extension):
    def extendMarkdown(self, md):
        # Inline parsing (20) has produced the final item text by now.
        md.treeprocessors.register(TaskListTreeprocessor(md), 'flog_tasklist', 15)
