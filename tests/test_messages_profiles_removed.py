import pytest
from lxml import html as lxml_html

from tests.conftest import login


@pytest.mark.parametrize('path', [
    '/messages', '/user/author', '/user/author/popup', '/edit_profile',
    '/send_message/other', '/export_posts', '/notifications', '/test_redis',
])
def test_removed_urls_are_not_found(client, users, path):
    assert client.get(path).status_code == 404
    login(client, 'author')
    assert client.get(path).status_code == 404


def test_article_author_is_plain_text(client, users):
    body = client.get(f'/post/{users["post"]}').get_data(as_text=True)
    page = lxml_html.fromstring(body)
    header = page.xpath('//header[contains(@class, "article-header")]')[0]
    assert not header.xpath('.//a')
    assert header.xpath('.//img[contains(@class, "article-header__avatar")]')
    assert 'author' in header.text_content()
    assert 'user_popup' not in body


def test_base_template_has_no_popover_or_notification_scripts(client, users):
    login(client, 'author')
    body = client.get('/').get_data(as_text=True)
    for fragment in ('initialize_popovers', 'initialize_notifications',
                     'message_count', '/notifications', '-progress'):
        assert fragment not in body, fragment


from pathlib import Path


def test_removed_models_and_user_methods_are_gone():
    import app as flog
    import app.models as models
    for name in ('Message', 'Notification', 'Task'):
        assert not hasattr(models, name), name
    for name in ('unread_message_count', 'add_notification', 'launch_task',
                 'get_tasks_in_progress', 'get_task_in_progress'):
        assert not hasattr(models.User, name), name
    assert not hasattr(flog.app, 'task_queue')


def test_task_module_templates_and_rq_requirement_are_gone():
    root = Path(__file__).resolve().parents[1]
    assert not (root / 'app' / 'tasks.py').exists()
    assert not (root / 'app' / 'templates' / 'email' / 'export_posts.html').exists()
    assert not (root / 'app' / 'templates' / 'email' / 'export_posts.txt').exists()
    for name in ('requirements.in', 'requirements.txt'):
        lines = [line.split('==')[0].strip() for line in
                 (root / name).read_text().splitlines()
                 if line and not line.startswith(('#', ' '))]
        assert 'rq' not in lines, name
