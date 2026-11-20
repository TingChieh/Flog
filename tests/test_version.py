"""Tests for application version detection and admin visibility."""
from lxml import html as lxml_html

from app.version import app_version, git_commit, version_info
from tests.conftest import login


def test_app_version_reads_pyproject_and_handles_missing_file(tmp_path):
    assert app_version() == '1.0.0'
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion = "2.3.4"\n', encoding='utf-8')
    assert app_version(tmp_path) == '2.3.4'
    assert app_version(tmp_path / 'empty') == '0.0.0'


def test_git_commit_resolves_loose_ref_packed_ref_detached_and_missing(tmp_path):
    assert git_commit(tmp_path) is None

    # Detached HEAD
    detached = tmp_path / 'detached'
    (detached / '.git').mkdir(parents=True)
    (detached / '.git' / 'HEAD').write_text('a1b2c3d4e5f60708090a0b0c0d0e0f1011121314\n')
    assert git_commit(detached) == 'a1b2c3d'

    # Loose ref
    loose = tmp_path / 'loose'
    (loose / '.git' / 'refs' / 'heads').mkdir(parents=True)
    (loose / '.git' / 'HEAD').write_text('ref: refs/heads/main\n')
    (loose / '.git' / 'refs' / 'heads' / 'main').write_text('deadbeef1234567890\n')
    assert git_commit(loose) == 'deadbee'

    # Packed ref
    packed = tmp_path / 'packed'
    (packed / '.git').mkdir(parents=True)
    (packed / '.git' / 'HEAD').write_text('ref: refs/heads/main\n')
    (packed / '.git' / 'packed-refs').write_text(
        '# pack-refs with: peeled\n'
        'cafebabe1234567890 refs/heads/main\n'
    )
    assert git_commit(packed) == 'cafebab'


def test_version_is_shown_in_admin_and_omitted_on_public_pages(client, users):
    expected = version_info()['label']
    assert expected is not None and expected.startswith('v1.0.0')

    public = client.get('/').get_data(as_text=True)
    assert 'data-app-version' not in public

    login(client, 'admin')
    for path in ('/admin/', '/admin/settings'):
        doc = lxml_html.fromstring(client.get(path).get_data(as_text=True))
        nodes = doc.xpath('//*[@data-app-version]')
        assert len(nodes) == 2  # sidebar + mobile drawer
        assert all(node.text_content().strip() == f'Flog {expected}' for node in nodes)

    client.post('/logout')
    login(client, 'author')
    member_doc = lxml_html.fromstring(client.get('/admin/').get_data(as_text=True))
    assert any(
        node.text_content().strip() == f'Flog {expected}'
        for node in member_doc.xpath('//*[@data-app-version]')
    )
