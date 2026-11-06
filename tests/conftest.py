import io
import os

import pytest
from PIL import Image as PILImage, ImageChops
from sqlalchemy.engine import make_url


os.environ['SECRET_KEY'] = 'test-secret'
test_url = os.environ.get('TEST_DATABASE_URL', 'sqlite://')
parsed_url = make_url(test_url)
if parsed_url.get_backend_name() != 'sqlite':
    if (parsed_url.get_backend_name() not in ('mysql', 'mariadb')
            or parsed_url.host not in ('127.0.0.1', 'localhost', '::1')
            or not (parsed_url.database or '').lower().endswith('test')):
        raise RuntimeError('TEST_DATABASE_URL must name a local MySQL test database ending in test')
os.environ['DATABASE_URL'] = test_url
os.environ['ADMIN_EMAILS'] = 'admin@example.com'
os.environ['MAIL_SERVER'] = ''

from app import app, db  # noqa: E402
from app.models import Category, Post, SiteSettings, User  # noqa: E402


@pytest.fixture()
def application(tmp_path):
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        UPLOAD_FOLDER=str(tmp_path / 'uploads'),
    )
    with app.app_context():
        db.create_all()
        db.session.add(SiteSettings(id=1))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(application):
    return application.test_client()


@pytest.fixture()
def users(application):
    with application.app_context():
        admin = User(username='admin', email='admin@example.com', role='admin')
        admin.set_password('password')
        author = User(username='author', email='author@example.com')
        author.set_password('password')
        other = User(username='other', email='other@example.com')
        other.set_password('password')
        category = Category(name='General')
        db.session.add_all([admin, author, other, category])
        db.session.commit()
        post = Post(title='Test', body='<p>safe</p>', author=author,
                    category=category, is_published=True)
        db.session.add(post)
        db.session.commit()
        return {'admin': admin.id, 'author': author.id, 'other': other.id,
                'post': post.id}


@pytest.fixture()
def role_users(application):
    with application.app_context():
        admin = User(username='role-admin', email='role-admin@example.com',
                     role='admin')
        member = User(username='role-member', email='role-member@example.com',
                      role='user')
        admin.set_password('password')
        member.set_password('password')
        db.session.add_all([admin, member])
        db.session.commit()
        return {'admin': admin.id, 'member': member.id}


def photo_like(size):
    """Smooth gradients plus sensor-style noise: lots of colours, JPEG-friendly."""
    channels = [
        PILImage.linear_gradient('L').rotate(90).resize(size),
        PILImage.linear_gradient('L').resize(size),
        PILImage.radial_gradient('L').resize(size),
    ]
    return PILImage.merge('RGB', [
        ImageChops.add(channel, PILImage.effect_noise(size, 6), 1, 0)
        for channel in channels])


def make_image(fmt='PNG', size=(8, 8), mode='RGB', noise=False, photo=False,
               **save_kwargs):
    """Bytes of a real image; ``noise`` is incompressible, ``photo`` photo-like."""
    if photo:
        image = photo_like(size)
    elif noise:
        image = PILImage.frombytes(
            mode, size, os.urandom(size[0] * size[1] * len(mode)))
    else:
        image = PILImage.new(mode, size, (30, 120, 200, 255)[:len(mode)])
    buffer = io.BytesIO()
    image.save(buffer, fmt, **save_kwargs)
    return buffer.getvalue()


def login(client, username):
    return client.post('/login', data={
        'username': username,
        'password': 'password',
    })
