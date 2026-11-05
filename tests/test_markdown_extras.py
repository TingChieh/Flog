import pytest
from lxml import html as lxml_html

from app.content import render_content
from app.security import sanitize_html


def render(source, body_format='markdown'):
    return str(render_content(source, body_format))


def tree(source):
    return lxml_html.fragment_fromstring(render(source), create_parent='div')


# --- math ---------------------------------------------------------------------

def test_inline_math_is_protected_from_markdown(application):
    with application.app_context():
        html = render('Euler: $a_1 + b_2 * c_3$ done')
    assert '<span class="math math-inline">a_1 + b_2 * c_3</span>' in html
    assert '<em>' not in html


def test_math_keeps_backslashes_and_carets(application):
    with application.app_context():
        html = render(r'$\LaTeX$ and $a^n+b^n=c^n$')
    assert r'<span class="math math-inline">\LaTeX</span>' in html
    assert '<span class="math math-inline">a^n+b^n=c^n</span>' in html


def test_block_math_spans_lines_and_is_its_own_block(application):
    source = 'before\n\n$$\n\\sum_{q=0}^{\\infty} x_q\n\\frac{a}{b}\n$$\n\nafter'
    with application.app_context():
        root = tree(source)
    blocks = root.xpath('//p[@class="math math-block"]')
    assert len(blocks) == 1
    assert blocks[0].text_content().strip() == \
        '\\sum_{q=0}^{\\infty} x_q\n\\frac{a}{b}'
    assert [p.text_content() for p in root.xpath('./p[not(@class)]')] == [
        'before', 'after']


def test_math_is_html_escaped(application):
    with application.app_context():
        html = render('$a<b>c$ and\n\n$$x<y$$')
    assert '<span class="math math-inline">a&lt;b&gt;c</span>' in html
    assert '<b>' not in html
    assert 'x&lt;y' in html


@pytest.mark.parametrize('source', [
    'it costs $5 and $6 today',
    'it costs $ 5 $ today',
    'price $20 and $30',
    '$x$5 stays plain text',
    r'escaped \$a\$ stays text',
    'lonely $ sign',
])
def test_prices_and_stray_dollars_are_not_math(application, source):
    with application.app_context():
        html = render(source)
    assert 'math' not in html


def test_math_in_code_is_left_alone(application):
    source = 'inline `$a_1$` code\n\n```\n$$\nx\n$$\n$y$\n```\n\n    $z$\n'
    with application.app_context():
        html = render(source)
    assert 'math' not in html
    assert '<code>$a_1$</code>' in html
    assert '$y$' in html


def test_math_is_not_applied_to_html_bodies(application):
    with application.app_context():
        assert 'math' not in render('<p>$a_1$</p>', 'html')


def test_math_markup_survives_the_sanitizer_but_other_classes_do_not(application):
    with application.app_context():
        html = render('<span class="math math-inline">x</span> <span class="evil">y</span>')
    assert 'class="math math-inline"' in html
    assert 'class="evil"' not in html


# --- task lists --------------------------------------------------------------------

def test_task_list_items_become_read_only_checkboxes(application):
    with application.app_context():
        root = tree('- [ ] 刷B站\n- [x] 起床\n- [X] 写代码')
    items = root.xpath('//ul[@class="task-list"]/li[@class="task-list-item"]')
    assert len(items) == 3
    boxes = [li.xpath('./input')[0] for li in items]
    assert all(b.get('type') == 'checkbox' and b.get('disabled') is not None
               for b in boxes)
    assert [b.get('checked') is not None for b in boxes] == [False, True, True]
    assert [li.text_content().strip() for li in items] == [
        '刷B站', '起床', '写代码']


def test_loose_and_nested_task_lists_work(application):
    source = '- [ ] one\n\n- [x] two\n\n- plain\n    - [ ] nested\n'
    with application.app_context():
        root = tree(source)
    assert len(root.xpath('//input[@type="checkbox"]')) == 3
    assert len(root.xpath('//li[@class="task-list-item"]')) == 3
    assert not root.xpath('//li[normalize-space(text())="plain"][@class]')


def test_task_markers_elsewhere_are_plain_text(application):
    with application.app_context():
        root = tree('- item [ ] later\n- [ ]no space\n- [] empty\n\npara [x] text')
    assert not root.xpath('//input')
    assert 'task-list' not in render('- item [ ] later')


def test_task_item_keeps_inline_formatting(application):
    with application.app_context():
        root = tree('- [x] **bold** and `code`')
    li = root.xpath('//li')[0]
    assert li.xpath('./input[@checked]')
    assert li.xpath('./strong')[0].text == 'bold'
    assert li.xpath('./code')[0].text == 'code'


def test_sanitizer_only_allows_checkbox_inputs_without_handlers():
    assert 'input' not in sanitize_html('<input type="text" value="x">')
    assert 'type="password"' not in sanitize_html('<input type="password">')
    cleaned = sanitize_html('<input type="checkbox" checked onclick="alert(1)" name="n">')
    assert 'type="checkbox"' in cleaned and 'checked' in cleaned
    assert 'onclick' not in cleaned and 'name=' not in cleaned


# --- tables -----------------------------------------------------------------------------

TABLE = '| a | b | c |\n| :--- | :---: | ---: |\n| 1 | 2 | 3 |\n'


def test_table_alignment_is_preserved(application):
    with application.app_context():
        root = tree(TABLE)
    for row in root.xpath('//tr'):
        cells = row.xpath('./th|./td')
        assert [c.get('style') for c in cells] == [
            'text-align: left;', 'text-align: center;', 'text-align: right;']


def test_unaligned_columns_get_no_style(application):
    with application.app_context():
        root = tree('| a | b |\n| --- | --- |\n| 1 | 2 |\n')
    assert not root.xpath('//*[@style]')


@pytest.mark.parametrize('style', [
    'color: red', 'text-align: justify', 'text-align: center; color: red',
    'background: url(javascript:alert(1))', 'text-align:center;position:fixed',
])
def test_other_inline_styles_are_still_stripped(style):
    cleaned = sanitize_html(f'<table><tr><td style="{style}">x</td></tr></table>')
    assert 'style' not in cleaned


@pytest.mark.parametrize('value', ['left', 'center', 'right'])
def test_the_three_alignments_are_allowed_on_cells(value):
    cleaned = sanitize_html(
        f'<table><tr><th style="text-align:{value}">x</th><td style="text-align: {value};">y</td></tr></table>')
    assert cleaned.count('style=') == 2


def test_other_tags_may_not_carry_styles():
    assert 'style' not in sanitize_html('<p style="text-align:center">x</p>')


# --- mermaid ------------------------------------------------------------------------------

def test_mermaid_blocks_keep_their_source_in_a_code_block(application):
    with application.app_context():
        root = tree('```mermaid\ngraph TD\n  A["<b>x</b>"] --> B\n```')
    code = root.xpath('//pre/code[@class="language-mermaid"]')[0]
    assert code.get('data-language-label') == 'Mermaid'
    assert code.text_content() == 'graph TD\n  A["<b>x</b>"] --> B\n'
    assert not root.xpath('//b')


# --- list continuation indent (CommonMark style) ------------------------------

def test_three_space_list_continuation_stays_in_the_item(application):
    source = '1. first\n\n   detail one\n2. second\n\n   detail two\n'
    with application.app_context():
        root = tree(source)
    items = root.findall('.//ol/li')
    assert len(root.findall('.//ol')) == 1
    assert [li.findtext('p') for li in items] == ['first', 'second']
    assert [li.findall('p')[1].text for li in items] == ['detail one', 'detail two']


def test_ten_item_list_with_mixed_indent_is_one_list_without_code(application):
    source = ''.join(f'{n}. item {n}\n\n{" " * (4 if n >= 9 else 3)}note {n}\n'
                     for n in range(1, 12))
    with application.app_context():
        root = tree(source)
    assert len(root.findall('.//ol')) == 1
    assert len(root.findall('.//ol/li')) == 11
    assert root.find('.//pre') is None


def test_nested_bullets_under_numbered_item(application):
    source = '1. parent\n   - child a\n   - child b\n2. next\n'
    with application.app_context():
        root = tree(source)
    assert [li.text.strip() for li in root.findall('.//ol/li/ul/li')] == ['child a', 'child b']


def test_four_space_continuation_and_fences_are_unchanged(application):
    source = '- a\n\n    para\n\n```\n   keep\n```\n'
    with application.app_context():
        root = tree(source)
    assert root.find('.//ul/li').findall('p')[1].text == 'para'
    assert root.find('.//pre').text_content().strip() == 'keep'


def test_indented_code_after_a_list_is_still_code(application):
    with application.app_context():
        root = tree('- a\n\ntext\n\n    code\n')
    assert root.find('.//pre') is not None
