import io
import os
import uuid

import sqlalchemy as sa
from lxml import html as lxml_html

from app import db
from app.models import Image, Post
from tests.conftest import login, make_image

PNG = make_image()


def name():
    return f'{uuid.uuid4().hex}.png'


def add_image(application, owner=None, title='Photo', note=None,
              original='photo.png', size=2048, filename=None):
    with application.app_context():
        image = Image(filename=filename or name(), original_name=original,
                      title=title, note=note, size=size, user_id=owner)
        db.session.add(image)
        db.session.commit()
        return image.id, image.filename


def page(client, path):
    return lxml_html.fromstring(client.get(path).get_data(as_text=True))


def card_titles(document):
    return [t.strip() for t in document.xpath(
        '//*[contains(@class,"image-card__title")]/text()')]


def files(*specs):
    return [(io.BytesIO(data), filename) for filename, data in specs]


# --- library list ------------------------------------------------------------

def test_library_lists_images_with_size_and_usage(client, application, users):
    _, filename = add_image(application, users['author'], title='Sunset',
                            size=2048)
    folder = application.config['UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, filename), 'wb') as handle:
        handle.write(PNG)
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = f'![s](/files/{filename})'
        db.session.commit()
    login(client, 'author')
    html = client.get('/admin/images').get_data(as_text=True)
    assert 'Sunset' in html
    assert '2.0 KB' in html
    assert '被 1 处引用' in html
    assert f'/files/{filename}' in html


def test_library_search_matches_title_note_and_original_name(
        client, application, users):
    add_image(application, users['author'], title='Sunset')
    add_image(application, users['author'], title='Other', note='a quiet harbour')
    add_image(application, users['author'], title='Third', original='IMG_0042.png')
    login(client, 'author')
    assert card_titles(page(client, '/admin/images?q=sun')) == ['Sunset']
    assert card_titles(page(client, '/admin/images?q=HARBOUR')) == ['Other']
    assert card_titles(page(client, '/admin/images?q=img_00')) == ['Third']


def test_library_members_see_only_their_own_images(client, application, users):
    add_image(application, users['author'], title='Mine')
    add_image(application, users['other'], title='Theirs')
    add_image(application, None, title='Ownerless')
    login(client, 'author')
    assert card_titles(page(client, '/admin/images')) == ['Mine']
    client.post('/logout')
    login(client, 'admin')
    assert sorted(card_titles(page(client, '/admin/images'))) == [
        'Mine', 'Ownerless', 'Theirs']


def test_opening_the_library_registers_untracked_files(
        client, application, users):
    folder = application.config['UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    untracked = name()
    with open(os.path.join(folder, untracked), 'wb') as handle:
        handle.write(PNG)
    login(client, 'admin')
    assert client.get('/admin/images').status_code == 200
    with application.app_context():
        assert db.session.scalar(sa.select(Image.filename)) == untracked


def test_library_marks_missing_files(client, application, users):
    add_image(application, users['author'], title='Gone')
    login(client, 'author')
    document = page(client, '/admin/images')
    assert document.xpath('//*[contains(@class,"image-card__missing")]')


def test_library_requires_login(client):
    response = client.get('/admin/images')
    assert response.status_code == 302 and '/login' in response.headers['Location']


# --- library upload ------------------------------------------------------------

def test_library_upload_creates_rows_and_summarises(client, application, users):
    login(client, 'author')
    response = client.post('/admin/images/upload', data={
        'images': files(('a.png', PNG), ('b.png', PNG), ('bad.png', b'nope')),
    }, content_type='multipart/form-data', follow_redirects=True)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '已上传 2 张' in html
    assert 'bad.png' in html
    with application.app_context():
        rows = db.session.scalars(sa.select(Image)).all()
        assert len(rows) == 2 and all(r.user_id == users['author'] for r in rows)


def test_library_upload_without_files_flashes_an_error(client, users):
    login(client, 'author')
    response = client.post('/admin/images/upload', data={},
                           content_type='multipart/form-data',
                           follow_redirects=True)
    assert '请选择要上传的图片' in response.get_data(as_text=True)


def test_library_upload_rejects_missing_csrf(client, application, users):
    login(client, 'author')
    application.config['WTF_CSRF_ENABLED'] = True
    try:
        response = client.post('/admin/images/upload', data={
            'images': files(('a.png', PNG))}, content_type='multipart/form-data')
        assert response.status_code == 400
    finally:
        application.config['WTF_CSRF_ENABLED'] = False
    with application.app_context():
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Image)) == 0


# --- picker JSON ---------------------------------------------------------------

def test_picker_returns_visible_images_newest_first(client, application, users):
    first_id, first = add_image(application, users['author'], title='First')
    second_id, second = add_image(application, users['author'], title='Second')
    add_image(application, users['other'], title='Theirs')
    login(client, 'author')
    payload = client.get('/admin/images/picker').get_json()
    assert [i['title'] for i in payload['images']] == ['Second', 'First']
    assert payload['images'][0] == {
        'id': second_id, 'title': 'Second', 'url': f'/files/{second}',
        'thumb': f'/files/{second}', 'size': 2048}


def test_picker_filters_and_limits(client, application, users):
    for index in range(65):
        add_image(application, users['author'], title=f'Shot {index:02d}')
    add_image(application, users['author'], title='Unique')
    login(client, 'author')
    assert len(client.get('/admin/images/picker').get_json()['images']) == 60
    found = client.get('/admin/images/picker?q=uniq').get_json()['images']
    assert [i['title'] for i in found] == ['Unique']


def test_picker_requires_login(client):
    assert client.get('/admin/images/picker').status_code == 302


# --- navigation ------------------------------------------------------------------

def test_navigation_has_an_images_link_for_everyone(client, users):
    for who in ('author', 'admin'):
        login(client, who)
        document = page(client, '/admin/images')
        links = document.xpath(
            '//nav[@aria-label="管理导航"]//a[normalize-space()="图片"]')
        assert links and links[0].get('href') == '/admin/images'
        current = {a.text_content().strip() for a in document.xpath(
            '//nav[@aria-label="管理导航"]//a[@aria-current="page"]')}
        assert current == {'图片'}
        client.post('/logout')


# --- detail and edit -----------------------------------------------------------

def put_file(application, filename, data=PNG):
    folder = application.config['UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    with open(path, 'wb') as handle:
        handle.write(data)
    return path


def test_detail_shows_preview_url_and_usages(client, application, users):
    image_id, filename = add_image(application, users['author'], title='Sunset',
                                   note='golden hour')
    put_file(application, filename)
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = f'![s](/files/{filename})'
        db.session.commit()
    login(client, 'author')
    document = page(client, f'/admin/images/{image_id}')
    html = lxml_html.tostring(document, encoding='unicode')
    assert f'/files/{filename}' in html
    assert document.xpath('//input[@name="title"]/@value') == ['Sunset']
    assert 'golden hour' in document.xpath('string(//textarea[@name="note"])')
    edit = document.xpath(f'//a[@href="/admin/posts/{users["post"]}/edit"]')
    assert edit and 'Test' in edit[0].text_content()
    assert document.xpath(f'//a[@href="/admin/images/{image_id}/delete"]')


def test_detail_without_usages_says_so(client, application, users):
    image_id, filename = add_image(application, users['author'])
    login(client, 'author')
    assert '尚未被引用' in client.get(
        f'/admin/images/{image_id}').get_data(as_text=True)


def test_edit_saves_title_and_note(client, application, users):
    image_id, _ = add_image(application, users['author'], title='Old')
    login(client, 'author')
    response = client.post(f'/admin/images/{image_id}', data={
        'title': 'New title', 'note': 'A note'})
    assert response.status_code == 302
    with application.app_context():
        image = db.session.get(Image, image_id)
        assert (image.title, image.note) == ('New title', 'A note')


def test_empty_title_falls_back_to_the_original_name(client, application, users):
    image_id, _ = add_image(application, users['author'], title='Old',
                            original='Holiday.png')
    login(client, 'author')
    client.post(f'/admin/images/{image_id}', data={'title': '  ', 'note': ''})
    with application.app_context():
        image = db.session.get(Image, image_id)
        assert image.title == 'Holiday'
        assert image.note is None


def test_edit_rejects_overlong_values(client, application, users):
    image_id, _ = add_image(application, users['author'], title='Old')
    login(client, 'author')
    for data in ({'title': 'x' * 121, 'note': ''}, {'title': 'ok', 'note': 'n' * 501}):
        assert client.post(f'/admin/images/{image_id}', data=data).status_code == 200
    with application.app_context():
        assert db.session.get(Image, image_id).title == 'Old'


def test_members_cannot_touch_other_peoples_images(client, application, users):
    theirs, _ = add_image(application, users['other'], title='Theirs')
    ownerless, _ = add_image(application, None, title='Nobody')
    login(client, 'author')
    for image_id in (theirs, ownerless):
        for path in (f'/admin/images/{image_id}', f'/admin/images/{image_id}/delete'):
            assert client.get(path).status_code == 403, path
            assert client.post(path, data={'title': 'x'}).status_code == 403, path
    assert client.get('/admin/images/9999').status_code == 404
    assert client.get('/admin/images/9999/delete').status_code == 404
    with application.app_context():
        assert db.session.get(Image, theirs).title == 'Theirs'


def test_admin_manages_any_image_including_ownerless(client, application, users):
    image_id, _ = add_image(application, None, title='Nobody')
    login(client, 'admin')
    assert client.get(f'/admin/images/{image_id}').status_code == 200
    assert client.post(f'/admin/images/{image_id}', data={
        'title': 'Named', 'note': ''}).status_code == 302


def test_detail_requires_login(client, application, users):
    image_id, _ = add_image(application, users['author'])
    assert client.get(f'/admin/images/{image_id}').status_code == 302


# --- delete -----------------------------------------------------------------------

def test_delete_unused_image_removes_file_and_row(client, application, users):
    image_id, filename = add_image(application, users['author'])
    path = put_file(application, filename)
    login(client, 'author')
    assert '没有文章或页面在使用' in client.get(
        f'/admin/images/{image_id}/delete').get_data(as_text=True)
    response = client.post(f'/admin/images/{image_id}/delete', data={})
    assert response.status_code == 302
    assert not os.path.exists(path)
    with application.app_context():
        assert db.session.get(Image, image_id) is None


def test_delete_in_use_image_requires_force(client, application, users):
    image_id, filename = add_image(application, users['author'])
    path = put_file(application, filename)
    with application.app_context():
        post = db.session.get(Post, users['post'])
        post.body = f'![s](/files/{filename})'
        db.session.commit()
    login(client, 'author')

    confirm = client.get(f'/admin/images/{image_id}/delete').get_data(as_text=True)
    assert '会失效' in confirm and 'name="force"' in confirm

    blocked = client.post(f'/admin/images/{image_id}/delete', data={})
    assert blocked.status_code == 200
    assert os.path.exists(path)
    with application.app_context():
        assert db.session.get(Image, image_id) is not None

    forced = client.post(f'/admin/images/{image_id}/delete', data={'force': 'y'})
    assert forced.status_code == 302
    assert not os.path.exists(path)
    with application.app_context():
        assert db.session.get(Image, image_id) is None


def test_delete_tolerates_a_missing_file(client, application, users):
    image_id, _ = add_image(application, users['author'])
    login(client, 'author')
    assert client.post(f'/admin/images/{image_id}/delete', data={}).status_code == 302
    with application.app_context():
        assert db.session.get(Image, image_id) is None


def test_delete_and_edit_reject_missing_csrf(client, application, users):
    image_id, filename = add_image(application, users['author'])
    path = put_file(application, filename)
    login(client, 'author')
    application.config['WTF_CSRF_ENABLED'] = True
    try:
        assert client.post(f'/admin/images/{image_id}/delete', data={}).status_code == 400
        assert client.post(f'/admin/images/{image_id}', data={
            'title': 'x', 'note': ''}).status_code == 400
    finally:
        application.config['WTF_CSRF_ENABLED'] = False
    assert os.path.exists(path)
    with application.app_context():
        assert db.session.get(Image, image_id).title == 'Photo'


# --- editor wiring -----------------------------------------------------------------

def test_editors_carry_the_library_url_and_load_the_picker_script(
        client, application, users):
    with application.app_context():
        from app.models import Page
        db.session.add(Page(title='P', slug='p', kind='content', body='x',
                            body_format='markdown'))
        db.session.commit()
        page_id = db.session.scalar(sa.select(Page.id))
        db.session.get(Post, users['post']).body_format = 'markdown'
        db.session.commit()
    login(client, 'admin')
    for path in ('/admin/posts/new', '/admin/pages/new',
                 f'/admin/pages/{page_id}/edit',
                 f'/admin/posts/{users["post"]}/edit'):
        document = page(client, path)
        form = document.xpath('//form[@data-image-upload-url]')
        assert form, path
        assert form[0].get('data-image-library-url') == '/admin/images/picker', path
        scripts = [src.split('?')[0] for src in document.xpath('//script/@src')]
        picker = [i for i, s in enumerate(scripts) if s.endswith('/image-picker.js')]
        editor = [i for i, s in enumerate(scripts) if s.endswith('/markdown-editor.js')]
        assert picker and editor and picker[0] < editor[0], path


# --- the library's script uploads set by set -------------------------------------

JSON = {'Accept': 'application/json'}


def test_json_upload_reports_counts_without_redirecting_or_flashing(
        client, application, users):
    login(client, 'author')
    response = client.post('/admin/images/upload', data={
        'images': files(('a.png', PNG), ('bad.png', b'nope')),
    }, content_type='multipart/form-data', headers=JSON)

    assert response.status_code == 200
    assert response.get_json() == {
        'saved': 1, 'failed': ['bad.png：不是有效的 gif/jpg/png/heic 图片']}
    with client.session_transaction() as session:
        assert not session.get('_flashes')
    with application.app_context():
        assert db.session.scalar(sa.select(sa.func.count(Image.id))) == 1


def test_json_upload_without_files_is_a_bad_request(client, users):
    login(client, 'author')
    response = client.post('/admin/images/upload', data={},
                           content_type='multipart/form-data', headers=JSON)
    assert response.status_code == 400


def test_json_upload_still_needs_a_login(client):
    response = client.post('/admin/images/upload', data={
        'images': files(('a.png', PNG))},
        content_type='multipart/form-data', headers=JSON)
    assert response.status_code in (302, 401)


def test_form_post_without_the_json_header_keeps_flash_and_redirect(
        client, users):
    login(client, 'author')
    response = client.post('/admin/images/upload', data={
        'images': files(('a.png', PNG))}, content_type='multipart/form-data')
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert any('已上传 1 张' in message for _, message in session['_flashes'])


def test_the_uploaded_count_becomes_one_flash_on_a_clean_url(client, users):
    login(client, 'author')

    first = client.get('/admin/images?uploaded=3')
    assert first.status_code == 302
    assert first.headers['Location'].endswith('/admin/images')

    page = client.get(first.headers['Location']).get_data(as_text=True)
    assert '已上传 3 张。' in page
    assert '已上传 3 张。' not in client.get('/admin/images').get_data(as_text=True)


def test_library_page_wires_up_the_progress_scripts(client, users):
    login(client, 'author')
    page = client.get('/admin/images').get_data(as_text=True)

    assert 'data-image-upload' in page and 'data-upload-status' in page
    assert '/static/upload-progress.js' in page and '/static/image-upload.js' in page


def test_avatar_and_editor_pages_load_the_progress_helper(client, users):
    login(client, 'author')
    assert '/static/upload-progress.js' in client.get(
        '/admin/account/avatar').get_data(as_text=True)
    assert 'data-upload-lock' in client.get(
        '/admin/account/avatar').get_data(as_text=True)
    editor = client.get('/admin/posts/new').get_data(as_text=True)
    assert editor.index('upload-progress.js') < editor.index('markdown-editor.js')
