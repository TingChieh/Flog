"""Tests for batch Markdown + media export/import (round-trip, idempotency, safety, rollback)."""
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

from app import content_io, db
from app.content_io import (
    ContentExportError,
    ContentImportError,
    dump_front_matter,
    export_posts_bundle,
    import_posts_bundle,
    parse_markdown_document,
    sha256_bytes,
)
from app.models import Category, Image, Post, PostDraft, User
from tests.conftest import make_image


def _seed_sample_data(application):
    uploads = Path(application.config['UPLOAD_FOLDER'])
    uploads.mkdir(parents=True, exist_ok=True)
    img1_bytes = make_image('PNG', size=(32, 24))
    img2_bytes = make_image('JPEG', size=(40, 30))
    clip_bytes = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom'

    img1_name = 'a' * 32 + '.png'
    img2_name = 'b' * 32 + '.jpg'
    clip_name = 'b' * 32 + '.mp4'
    (uploads / img1_name).write_bytes(img1_bytes)
    (uploads / img2_name).write_bytes(img2_bytes)
    (uploads / clip_name).write_bytes(clip_bytes)

    author = User(username='writer', email='writer@example.com', role='admin')
    author.set_password('password')
    cat_tech = Category(name='技术')
    cat_life = Category(name='生活')
    db.session.add_all([author, cat_tech, cat_life])
    db.session.flush()

    db.session.add_all([
        Image(
            filename=img1_name, original_name='diagram.png', title='架构图',
            note='主图说明', size=len(img1_bytes), width=32, height=24,
            user_id=author.id,
        ),
        Image(
            filename=img2_name, original_name='live.jpg', title='实况图',
            size=len(img2_bytes), width=40, height=30,
            video_filename=clip_name, user_id=author.id,
        ),
    ])

    pub_post = Post(
        legacy_id=101,
        title='带图片的 Markdown 文章',
        body=f'# 标题\n\n![架构图](/files/{img1_name})\n\n![实况图](/files/{img2_name})\n\n外链：[站外](https://example.com)',
        body_format='markdown',
        is_published=True,
        comments_enabled=False,
        timestamp=datetime(2026, 3, 15, 4, 30, 0),
        updated_at=datetime(2026, 3, 16, 8, 0, 0),
        author=author,
        category=cat_tech,
        language='zh-cn',
    )
    draft_post = Post(
        title='',
        body='',
        body_format='markdown',
        is_published=False,
        timestamp=datetime(2026, 4, 1, 1, 0, 0),
        scheduled_at=datetime(2026, 12, 1, 0, 0, 0),
        author=author,
        draft=PostDraft(
            title='定时草稿：含特殊字符 "引号"',
            body=f'草稿正文 ![图](/files/{img1_name})',
            category_id=cat_life.id,
            language='zh-cn',
        ),
    )
    db.session.add_all([pub_post, draft_post])
    db.session.commit()
    return {
        'img1_name': img1_name,
        'img2_name': img2_name,
        'clip_name': clip_name,
        'img1_bytes': img1_bytes,
        'img2_bytes': img2_bytes,
        'clip_bytes': clip_bytes,
    }


def _wipe_content_and_uploads(application):
    db.session.execute(sa.delete(PostDraft))
    db.session.execute(sa.delete(Post))
    db.session.execute(sa.delete(Image))
    db.session.execute(sa.delete(Category))
    db.session.commit()
    uploads = Path(application.config['UPLOAD_FOLDER'])
    if uploads.is_dir():
        for child in uploads.iterdir():
            if child.is_file():
                child.unlink()


def test_front_matter_round_trip_with_unicode_and_nested_media():
    meta = {
        'title': '标题: 含冒号与 "引号"',
        'slug': 'post-101',
        'legacy_id': 101,
        'is_published': True,
        'tags': ['python', 'blog'],
        'note': None,
        'media': [
            {'path': '../media/abc.png', 'sha256': '1234', 'note': None},
        ],
    }
    doc = dump_front_matter(meta) + '\n正文第一行\n\n---\n\n正文第二行\n'
    parsed_meta, parsed_body = parse_markdown_document(doc)
    assert parsed_meta == meta
    assert parsed_body == '正文第一行\n\n---\n\n正文第二行\n'


def test_export_and_import_round_trip_and_idempotency(application, tmp_path):
    with application.app_context():
        seeded = _seed_sample_data(application)
        bundle_dir = tmp_path / 'export-bundle'

        exported = export_posts_bundle(bundle_dir)
        assert exported.exported_posts == 2
        assert exported.exported_media == 2
        assert exported.exported_videos == 1
        assert exported.manifest_path and exported.manifest_path.is_file()
        assert (bundle_dir / 'media' / seeded['img1_name']).read_bytes() == seeded['img1_bytes']
        assert (bundle_dir / 'media' / seeded['clip_name']).read_bytes() == seeded['clip_bytes']

        # Verify exported Markdown rewrites /files/ to relative ../media/
        post_md = (bundle_dir / exported.post_files[0]).read_text(encoding='utf-8')
        assert f'../media/{seeded["img1_name"]}' in post_md
        assert f'/files/{seeded["img1_name"]}' not in post_md
        assert 'published_at: "2026-03-15T12:30:00+08:00"' in post_md
        assert 'tags: []' in post_md

        # Wipe DB + uploads (keeping User) and import back into clean state.
        _wipe_content_and_uploads(application)

        dry = import_posts_bundle(bundle_dir, dry_run=True)
        assert dry.dry_run is True
        assert dry.created_posts == 2
        assert dry.created_media == 2
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post)) == 0

        imported = import_posts_bundle(bundle_dir)
        assert imported.created_posts == 2
        assert imported.updated_posts == 0
        assert imported.skipped_posts == 0
        assert imported.created_media == 2
        assert sorted(imported.created_categories) == ['技术', '生活']

        posts = db.session.scalars(sa.select(Post).order_by(Post.timestamp.asc())).all()
        assert len(posts) == 2
        rebuilt_pub, rebuilt_draft = posts
        assert rebuilt_pub.legacy_id == 101
        assert rebuilt_pub.title == '带图片的 Markdown 文章'
        assert f'/files/{seeded["img1_name"]}' in rebuilt_pub.body
        assert f'/files/{seeded["img2_name"]}' in rebuilt_pub.body
        assert 'https://example.com' in rebuilt_pub.body
        assert rebuilt_pub.comments_enabled is False
        assert rebuilt_pub.timestamp == datetime(2026, 3, 15, 4, 30, 0)
        assert rebuilt_pub.updated_at == datetime(2026, 3, 16, 8, 0, 0)
        assert rebuilt_pub.category.name == '技术'

        assert rebuilt_draft.is_published is False
        assert rebuilt_draft.scheduled_at == datetime(2026, 12, 1, 0, 0, 0)
        assert rebuilt_draft.draft is not None
        assert rebuilt_draft.draft.title == '定时草稿：含特殊字符 "引号"'
        assert f'/files/{seeded["img1_name"]}' in rebuilt_draft.draft.body

        uploads = Path(application.config['UPLOAD_FOLDER'])
        assert (uploads / seeded['img1_name']).read_bytes() == seeded['img1_bytes']
        assert (uploads / seeded['img2_name']).read_bytes() == seeded['img2_bytes']
        assert (uploads / seeded['clip_name']).read_bytes() == seeded['clip_bytes']
        img2 = db.session.scalar(sa.select(Image).where(Image.filename == seeded['img2_name']))
        assert img2 is not None and img2.video_filename == seeded['clip_name']

        # Re-importing the exact same bundle is strictly idempotent.
        repeat = import_posts_bundle(bundle_dir)
        assert repeat.created_posts == 0
        assert repeat.updated_posts == 0
        assert repeat.skipped_posts == 2
        assert repeat.created_media == 0
        assert repeat.reused_media == 2
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post)) == 2
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Image)) == 2


def test_import_external_markdown_with_human_media_names_is_idempotent(application, users, tmp_path):
    bundle = tmp_path / 'external'
    (bundle / 'posts').mkdir(parents=True)
    (bundle / 'media').mkdir(parents=True)
    raw = make_image('PNG', size=(16, 16))
    (bundle / 'media' / 'cover.png').write_bytes(raw)
    (bundle / 'posts' / 'hello.md').write_text(
        '---\n'
        'title: "外部导入文章"\n'
        'slug: "external-hello"\n'
        'category: "随笔"\n'
        'tags: ["notes", "travel"]\n'
        'published_at: "2026-05-01T10:00:00+08:00"\n'
        '---\n\n'
        '内容 ![封面](../media/cover.png)\n',
        encoding='utf-8',
    )

    with application.app_context():
        first = import_posts_bundle(bundle, default_author='author')
        assert first.created_posts == 1
        assert first.created_media == 1
        assert any('tags' in w for w in first.warnings)

        expected_name = f'{sha256_bytes(raw)[:32]}.png'
        post = db.session.scalar(sa.select(Post).where(Post.title == '外部导入文章'))
        assert post is not None
        assert f'/files/{expected_name}' in post.body
        assert post.timestamp == datetime(2026, 5, 1, 2, 0, 0)

        second = import_posts_bundle(bundle, default_author='author')
        assert second.created_posts == 0
        assert second.skipped_posts == 1
        assert second.reused_media == 1


def test_import_rejects_missing_media_and_path_traversal(application, users, tmp_path):
    bundle = tmp_path / 'bad-bundle'
    (bundle / 'posts').mkdir(parents=True)
    (bundle / 'posts' / 'missing.md').write_text(
        '---\n'
        'title: "缺失图片"\n'
        'slug: "missing-img"\n'
        'published_at: "2026-05-01T10:00:00+08:00"\n'
        '---\n\n'
        '![gone](../media/does-not-exist.png)\n',
        encoding='utf-8',
    )
    (bundle / 'posts' / 'escape.md').write_text(
        '---\n'
        'title: "路径穿越"\n'
        'slug: "path-escape"\n'
        'published_at: "2026-05-01T10:00:00+08:00"\n'
        '---\n\n'
        '![escape](../../../../etc/passwd)\n',
        encoding='utf-8',
    )

    with application.app_context():
        before_posts = db.session.scalar(sa.select(sa.func.count()).select_from(Post))
        with pytest.raises(ContentImportError) as exc_info:
            import_posts_bundle(bundle, default_author='author')
        joined = '\n'.join(exc_info.value.diagnostics)
        assert 'missing media file' in joined
        assert 'escapes import directory' in joined
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post)) == before_posts


def test_import_refuses_unconfirmed_post_and_media_conflicts_until_overwrite(
    application, tmp_path
):
    with application.app_context():
        seeded = _seed_sample_data(application)
        bundle = tmp_path / 'conflict-bundle'
        export_posts_bundle(bundle)

        # Modify exported post body to create a post conflict.
        post_files = sorted((bundle / 'posts').glob('*.md'))
        pub_file = next(p for p in post_files if 'legacy-101' in p.name)
        pub_file.write_text(
            pub_file.read_text(encoding='utf-8') + '\n新增冲突段落\n',
            encoding='utf-8',
        )

        # Modify exported image bytes (and its manifest sha256) to create a media conflict.
        replacement_png = make_image('PNG', size=(64, 64), noise=True)
        (bundle / 'media' / seeded['img1_name']).write_bytes(replacement_png)
        old_sha = sha256_bytes(seeded['img1_bytes'])
        new_sha = sha256_bytes(replacement_png)
        for p in post_files:
            p.write_text(
                p.read_text(encoding='utf-8').replace(old_sha, new_sha),
                encoding='utf-8',
            )

        with pytest.raises(ContentImportError) as exc_info:
            import_posts_bundle(bundle)
        diag = '\n'.join(exc_info.value.diagnostics)
        assert 'media path conflict on disk' in diag
        assert '--overwrite' in diag

        # Existing disk image and post must remain untouched.
        uploads = Path(application.config['UPLOAD_FOLDER'])
        assert (uploads / seeded['img1_name']).read_bytes() == seeded['img1_bytes']
        existing = db.session.scalar(sa.select(Post).where(Post.legacy_id == 101))
        assert existing is not None and '新增冲突段落' not in existing.body

        # Explicit overwrite=True applies both updates cleanly.
        confirmed = import_posts_bundle(bundle, overwrite=True)
        assert confirmed.updated_posts == 1
        assert confirmed.skipped_posts == 1
        assert confirmed.overwritten_media == 1
        assert (uploads / seeded['img1_name']).read_bytes() == replacement_png
        refreshed = db.session.scalar(sa.select(Post).where(Post.legacy_id == 101))
        assert refreshed is not None and '新增冲突段落' in refreshed.body


def test_import_rolls_back_db_and_uploads_on_commit_failure(
    application, tmp_path, monkeypatch
):
    with application.app_context():
        seeded = _seed_sample_data(application)
        bundle = tmp_path / 'rollback-bundle'
        export_posts_bundle(bundle)
        _wipe_content_and_uploads(application)

        # Place a pre-existing image that will be overwritten during overwrite=True,
        # and verify it is restored after rollback.
        uploads = Path(application.config['UPLOAD_FOLDER'])
        uploads.mkdir(parents=True, exist_ok=True)
        original_existing = make_image('PNG', size=(12, 12), noise=True)
        (uploads / seeded['img1_name']).write_bytes(original_existing)

        def explode():
            raise RuntimeError('simulated commit crash')

        monkeypatch.setattr(content_io, '_before_commit_hook', explode)

        with pytest.raises(ContentImportError) as exc_info:
            import_posts_bundle(bundle, overwrite=True)
        assert 'simulated commit crash' in str(exc_info.value)

        # DB must have 0 posts/categories/images; newly created img2/clip must be removed;
        # overwritten img1 must be restored to its pre-import bytes; no staging dirs left.
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post)) == 0
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Image)) == 0
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Category)) == 0
        assert (uploads / seeded['img1_name']).read_bytes() == original_existing
        assert not (uploads / seeded['img2_name']).exists()
        assert not (uploads / seeded['clip_name']).exists()
        assert not list(uploads.glob('.import-staging-*'))


def test_export_aborts_on_missing_media_unless_allowed(application, users, tmp_path):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post is not None
        post.body = '![lost](/files/' + 'c' * 32 + '.png)'
        post.body_format = 'markdown'
        db.session.commit()

        with pytest.raises(ContentExportError) as exc_info:
            export_posts_bundle(tmp_path / 'strict')
        assert 'missing /files/' in '\n'.join(exc_info.value.diagnostics)

        lenient = export_posts_bundle(tmp_path / 'lenient', allow_missing_media=True)
        assert lenient.exported_posts == 1
        assert len(lenient.missing_media) == 1


def test_cli_content_export_and_import_commands(application, tmp_path):
    runner = application.test_cli_runner()
    with application.app_context():
        _seed_sample_data(application)

    bundle = tmp_path / 'cli-bundle'
    res_export = runner.invoke(args=['content', 'export', str(bundle)])
    assert res_export.exit_code == 0, res_export.output
    assert 'Exported 2 post(s)' in res_export.output

    res_dry = runner.invoke(args=['content', 'import', str(bundle), '--dry-run'])
    assert res_dry.exit_code == 0, res_dry.output
    assert '[dry-run]' in res_dry.output
    assert '2 skipped' in res_dry.output


def test_export_gives_migrated_and_native_posts_distinct_slugs(application, users, tmp_path):
    with application.app_context():
        author = db.session.get(User, users['author'])
        cat = db.session.scalar(sa.select(Category))
        assert author is not None and cat is not None
        native = Post(
            id=42, title='原生 42 号文章', body='原生正文', body_format='markdown',
            is_published=True, timestamp=datetime(2026, 2, 1, 10, 0, 0),
            author=author, category=cat,
        )
        migrated = Post(
            id=43, legacy_id=42, title='迁移 42 号文章', body='迁移正文',
            body_format='markdown', is_published=True,
            timestamp=datetime(2026, 2, 2, 10, 0, 0),
            author=author, category=cat,
        )
        db.session.add_all([native, migrated])
        db.session.commit()

        bundle = tmp_path / 'distinct-slugs'
        exported = export_posts_bundle(bundle)
        assert exported.exported_posts == 3
        slugs = [
            parse_markdown_document((bundle / rel).read_text(encoding='utf-8'))[0]['slug']
            for rel in exported.post_files
        ]
        assert 'post-42' in slugs
        assert 'legacy-42' in slugs
        assert len(slugs) == len(set(slugs))

        _wipe_content_and_uploads(application)
        imported = import_posts_bundle(bundle)
        assert imported.created_posts == 3


def test_import_rejects_undated_markdown_to_preserve_idempotency(application, users, tmp_path):
    bundle = tmp_path / 'undated'
    (bundle / 'posts').mkdir(parents=True)
    (bundle / 'posts' / 'no-date.md').write_text(
        '---\n'
        'title: "缺少发布时间的文章"\n'
        'slug: "no-date"\n'
        '---\n\n'
        '正文内容\n',
        encoding='utf-8',
    )

    with application.app_context():
        before = db.session.scalar(sa.select(sa.func.count()).select_from(Post))
        with pytest.raises(ContentImportError) as exc_info:
            import_posts_bundle(bundle, default_author='author')
        assert 'published_at' in '\n'.join(exc_info.value.diagnostics)
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post)) == before


def test_reimport_native_post_with_renamed_title_conflicts_or_overwrites_without_duplicating(
    application, users, tmp_path
):
    with application.app_context():
        native = db.session.get(Post, users['post'])
        assert native is not None and native.legacy_id is None
        native_id = native.id
        native.title = '原生旧标题'
        native.body = '原生文章正文'
        native.body_format = 'markdown'
        native.timestamp = datetime(2026, 5, 10, 8, 0, 0)
        db.session.commit()

        bundle = tmp_path / 'native-rename'
        export_posts_bundle(bundle)
        md_file = next((bundle / 'posts').glob('*.md'))
        original_md = md_file.read_text(encoding='utf-8')
        assert f'id: {native_id}' in original_md
        assert f'slug: "post-{native_id}"' in original_md

        # 1) Change only the title (keeping id + slug): must conflict without --overwrite, never duplicate.
        md_file.write_text(
            original_md.replace('title: "原生旧标题"', 'title: "原生新标题"'),
            encoding='utf-8',
        )
        with pytest.raises(ContentImportError) as exc_info:
            import_posts_bundle(bundle)
        assert 'differs in: title' in '\n'.join(exc_info.value.diagnostics)
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post)) == 1
        assert db.session.get(Post, native_id).title == '原生旧标题'

        # With --overwrite, updates the existing native post in place (no duplicate created).
        updated = import_posts_bundle(bundle, overwrite=True)
        assert updated.updated_posts == 1
        assert updated.created_posts == 0
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post)) == 1
        assert db.session.get(Post, native_id).title == '原生新标题'

        # 2) Strip `id:` so only `slug: "post-<id>"` identifies the post, rename again.
        slug_only_md = '\n'.join(
            line for line in md_file.read_text(encoding='utf-8').splitlines()
            if not line.startswith('id:')
        ) + '\n'
        md_file.write_text(
            slug_only_md.replace('title: "原生新标题"', 'title: "仅凭Slug改标题"'),
            encoding='utf-8',
        )
        with pytest.raises(ContentImportError) as exc_info:
            import_posts_bundle(bundle)
        assert 'differs in: title' in '\n'.join(exc_info.value.diagnostics)
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post)) == 1

        updated_slug = import_posts_bundle(bundle, overwrite=True)
        assert updated_slug.updated_posts == 1
        assert updated_slug.created_posts == 0
        assert db.session.scalar(sa.select(sa.func.count()).select_from(Post)) == 1
        assert db.session.get(Post, native_id).title == '仅凭Slug改标题'


def test_same_title_same_second_posts_with_distinct_ids_and_one_second_apart(
    application, users, tmp_path
):
    with application.app_context():
        author = db.session.get(User, users['author'])
        cat = db.session.scalar(sa.select(Category))
        assert author is not None and cat is not None
        same_ts = datetime(2026, 6, 1, 4, 0, 0)
        p1 = Post(
            title='同标题文章', body='第一篇正文', body_format='markdown',
            is_published=True, timestamp=same_ts, author=author, category=cat,
        )
        p2 = Post(
            title='同标题文章', body='第二篇正文', body_format='markdown',
            is_published=True, timestamp=same_ts, author=author, category=cat,
        )
        db.session.add_all([p1, p2])
        db.session.commit()

        # Export bundle containing two posts with identical title and identical second,
        # differentiated by distinct id / slug.
        bundle = tmp_path / 'same-title-same-sec'
        exported = export_posts_bundle(bundle)
        assert exported.exported_posts == 3

        # Re-importing into same DB is idempotent (0 errors, 3 skipped).
        same_db_res = import_posts_bundle(bundle)
        assert same_db_res.skipped_posts == 3
        assert same_db_res.created_posts == 0

        # Wiping and importing into clean DB recreates all 3, and repeat import is idempotent.
        _wipe_content_and_uploads(application)
        rebuilt = import_posts_bundle(bundle)
        assert rebuilt.created_posts == 3
        repeat = import_posts_bundle(bundle)
        assert repeat.skipped_posts == 3
        assert repeat.created_posts == 0

        # External Markdown without id/slug: same title 1 second apart succeeds.
        one_sec_bundle = tmp_path / 'one-sec-apart'
        (one_sec_bundle / 'posts').mkdir(parents=True)
        (one_sec_bundle / 'posts' / 'a.md').write_text(
            '---\ntitle: "差一秒同标题"\npublished_at: "2026-07-01T10:00:00+08:00"\n---\n\nA\n',
            encoding='utf-8',
        )
        (one_sec_bundle / 'posts' / 'b.md').write_text(
            '---\ntitle: "差一秒同标题"\npublished_at: "2026-07-01T10:00:01+08:00"\n---\n\nB\n',
            encoding='utf-8',
        )
        apart = import_posts_bundle(one_sec_bundle, default_author='author')
        assert apart.created_posts == 2

        # Truly ambiguous duplicate: same title, same second, NO id/legacy_id/explicit slug -> rejected.
        dup_bundle = tmp_path / 'ambiguous-dup'
        (dup_bundle / 'posts').mkdir(parents=True)
        (dup_bundle / 'posts' / 'x.md').write_text(
            '---\ntitle: "无身份重复"\npublished_at: "2026-07-02T10:00:00+08:00"\n---\n\nX\n',
            encoding='utf-8',
        )
        (dup_bundle / 'posts' / 'y.md').write_text(
            '---\ntitle: "无身份重复"\npublished_at: "2026-07-02T10:00:00+08:00"\n---\n\nY\n',
            encoding='utf-8',
        )
        with pytest.raises(ContentImportError) as exc_info:
            import_posts_bundle(dup_bundle, default_author='author')
        assert 'duplicate post title+published_at' in '\n'.join(exc_info.value.diagnostics)


def test_reimport_with_only_language_changed_conflicts_and_overwrites(
    application, users, tmp_path
):
    with application.app_context():
        post = db.session.get(Post, users['post'])
        assert post is not None
        post_id = post.id
        post.body_format = 'markdown'
        post.language = 'zh-cn'
        post.timestamp = datetime(2026, 5, 20, 6, 0, 0)
        db.session.commit()

        bundle = tmp_path / 'lang-diff'
        export_posts_bundle(bundle)
        md_file = next((bundle / 'posts').glob('*.md'))
        md_file.write_text(
            md_file.read_text(encoding='utf-8').replace('language: "zh-cn"', 'language: "en"'),
            encoding='utf-8',
        )

        # Without --overwrite, language-only diff must be reported as conflict (not skipped).
        with pytest.raises(ContentImportError) as exc_info:
            import_posts_bundle(bundle)
        assert 'differs in: language' in '\n'.join(exc_info.value.diagnostics)
        assert db.session.get(Post, post_id).language == 'zh-cn'

        # With --overwrite, updates language cleanly.
        updated = import_posts_bundle(bundle, overwrite=True)
        assert updated.updated_posts == 1
        assert updated.skipped_posts == 0
        assert db.session.get(Post, post_id).language == 'en'
