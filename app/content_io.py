"""Batch Markdown + media export and staged, idempotent, recoverable import."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import sqlalchemy as sa
import sqlalchemy.orm as so

from app import db
from app.content import (
    BODY_FORMAT_HTML,
    BODY_FORMAT_MARKDOWN,
    CONTENT_FORMATS,
    normalize_body_format,
    prepare_content_source,
)
from app.images import (
    IMAGE_NAME_RE,
    USAGE_RE,
    _has_image_signature,
    read_dimensions,
    upload_folder,
)
from app.live_photos import has_video_signature, video_filename
from app.models import Category, Image, Post, PostDraft, User
from app.post_drafts import normalize_utc_naive
from app.timezones import to_display


EXPORT_FORMAT_VERSION = 1

_SAFE_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,119}$')
_MD_LINK_RE = re.compile(r'(!?\[[^\]]*\]\()([^)\s]+)((?:\s+"[^"]*")?\))')
_HTML_ATTR_RE = re.compile(
    r'(\b(?:src|href)\s*=\s*)(["\'])([^"\']+)\2',
    flags=re.IGNORECASE,
)
_EXTERNAL_SCHEMES = frozenset({'http', 'https', 'mailto', 'tel', 'data', 'javascript'})
_VIDEO_NAME_RE = re.compile(r'^[0-9a-f]{32}\.mp4$')


class ContentIOError(ValueError):
    """Base error for content export/import failures with per-item diagnostics."""

    def __init__(self, message: str, diagnostics: list[str] | None = None):
        super().__init__(message)
        self.diagnostics = list(diagnostics or [message])


class ContentExportError(ContentIOError):
    pass


class ContentImportError(ContentIOError):
    pass


@dataclass
class ExportResult:
    output_dir: Path
    exported_posts: int = 0
    exported_media: int = 0
    exported_videos: int = 0
    post_files: list[str] = field(default_factory=list)
    missing_media: list[str] = field(default_factory=list)
    manifest_path: Path | None = None


@dataclass
class ImportResult:
    dry_run: bool
    created_posts: int = 0
    updated_posts: int = 0
    skipped_posts: int = 0
    created_media: int = 0
    overwritten_media: int = 0
    reused_media: int = 0
    created_categories: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _format_scalar(value: Any) -> str:
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def dump_front_matter(metadata: dict[str, Any]) -> str:
    """Serialize metadata as a clean, deterministic YAML front-matter block."""
    lines = ['---']
    for key, value in metadata.items():
        if isinstance(value, list):
            if not value:
                lines.append(f'{key}: []')
                continue
            lines.append(f'{key}:')
            for item in value:
                if isinstance(item, dict):
                    entries = list(item.items())
                    if not entries:
                        lines.append('  - {}')
                        continue
                    first_k, first_v = entries[0]
                    lines.append(f'  - {first_k}: {_format_scalar(first_v)}')
                    for sub_k, sub_v in entries[1:]:
                        lines.append(f'    {sub_k}: {_format_scalar(sub_v)}')
                else:
                    lines.append(f'  - {_format_scalar(item)}')
        else:
            lines.append(f'{key}: {_format_scalar(value)}')
    lines.append('---')
    return '\n'.join(lines) + '\n'


def _parse_scalar(raw: str) -> Any:
    text = raw.strip()
    if text == '' or text in ('null', 'Null', 'NULL', '~'):
        return None
    if text in ('true', 'True', 'TRUE'):
        return True
    if text in ('false', 'False', 'FALSE'):
        return False
    if text == '[]':
        return []
    if text == '{}':
        return {}
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ContentImportError(f'Invalid quoted front matter value: {text}') from exc
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text.startswith('[') and text.endswith(']'):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in inner.split(',')]
    if re.fullmatch(r'-?\d+', text):
        return int(text)
    return text


def parse_markdown_document(text: str, source_name: str = '<memory>') -> tuple[dict[str, Any], str]:
    """Parse a Markdown document with YAML front matter into ``(metadata, body)``."""
    normalized = text.replace('\r\n', '\n')
    if not normalized.startswith('---\n'):
        raise ContentImportError(f'{source_name}: missing YAML front matter opening "---"')
    lines = normalized.split('\n')
    end_index = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == '---':
            end_index = idx
            break
    if end_index is None:
        raise ContentImportError(f'{source_name}: missing YAML front matter closing "---"')

    fm_lines = lines[1:end_index]
    body = '\n'.join(lines[end_index + 1:])
    if body.startswith('\n'):
        body = body[1:]

    metadata: dict[str, Any] = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            i += 1
            continue
        if line.startswith(' '):
            raise ContentImportError(
                f'{source_name}: unexpected indentation at front matter line {i + 2}')
        if ':' not in line:
            raise ContentImportError(
                f'{source_name}: invalid front matter line {i + 2}: {line!r}')
        key, _, rest = line.partition(':')
        key = key.strip()
        if not key:
            raise ContentImportError(
                f'{source_name}: empty key at front matter line {i + 2}')
        rest = rest.strip()
        if rest:
            metadata[key] = _parse_scalar(rest)
            i += 1
            continue

        # Block list (scalar list or list of flat mappings).
        items: list[Any] = []
        i += 1
        while i < len(fm_lines):
            sub = fm_lines[i]
            if not sub.strip() or sub.lstrip().startswith('#'):
                i += 1
                continue
            if not sub.startswith('  '):
                break
            if sub.startswith('  - '):
                item_raw = sub[4:]
                if ':' in item_raw and not item_raw.startswith(('"', "'")):
                    sub_k, _, sub_v = item_raw.partition(':')
                    entry: dict[str, Any] = {sub_k.strip(): _parse_scalar(sub_v)}
                    i += 1
                    while i < len(fm_lines):
                        cont = fm_lines[i]
                        if not cont.strip():
                            i += 1
                            continue
                        if cont.startswith('    ') and not cont.startswith('  - '):
                            if ':' not in cont:
                                raise ContentImportError(
                                    f'{source_name}: invalid mapping item at line {i + 2}')
                            ck, _, cv = cont.strip().partition(':')
                            entry[ck.strip()] = _parse_scalar(cv)
                            i += 1
                        else:
                            break
                    items.append(entry)
                else:
                    items.append(_parse_scalar(item_raw))
                    i += 1
            else:
                raise ContentImportError(
                    f'{source_name}: invalid list entry at line {i + 2}: {sub!r}')
        metadata[key] = items
    return metadata, body


def _post_slug(post: Post) -> str:
    if post.legacy_id is not None:
        return f'legacy-{post.legacy_id}'
    return f'post-{post.id}'


def _iso_display(value: datetime | None) -> str | None:
    if value is None:
        return None
    local = to_display(value)
    return local.replace(microsecond=0).isoformat()


def _parse_datetime(raw: Any, field_name: str, source_name: str) -> datetime | None:
    if raw is None or raw == '':
        return None
    if not isinstance(raw, str):
        raise ContentImportError(f'{source_name}: {field_name} must be an ISO-8601 string')
    text = raw.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ContentImportError(
            f'{source_name}: invalid {field_name} datetime {raw!r}') from exc
    return normalize_utc_naive(parsed).replace(microsecond=0)


def _rewrite_export_media_paths(body: str, filename_map: dict[str, str]) -> str:
    if not filename_map:
        return body

    def replace_match(match: re.Match[str]) -> str:
        filename = match.group(1)
        return filename_map.get(filename, match.group(0))

    return USAGE_RE.sub(replace_match, body)


def export_posts_bundle(
    output_dir: str | Path,
    *,
    include_drafts: bool = True,
    allow_missing_media: bool = False,
) -> ExportResult:
    """Export posts as Markdown with YAML front matter and paired local media."""
    target_root = Path(output_dir).resolve()
    posts_dir = target_root / 'posts'
    media_dir = target_root / 'media'
    uploads = upload_folder()

    query = (
        sa.select(Post)
        .options(
            so.selectinload(Post.category),
            so.selectinload(Post.author),
            so.selectinload(Post.draft),
        )
        .order_by(Post.timestamp.asc(), Post.id.asc())
    )
    if not include_drafts:
        query = query.where(Post.is_published.is_(True))
    posts = db.session.scalars(query).all()

    referenced_names: set[str] = set()
    post_sources: list[tuple[Post, str, str, int | None, str | None, list[str]]] = []
    for post in posts:
        source = post.draft if (not post.is_published and post.draft is not None) else post
        title = source.title or ''
        body = source.body or ''
        category_id = source.category_id
        language = source.language
        names = sorted(set(USAGE_RE.findall(body)))
        referenced_names.update(names)
        post_sources.append((post, title, body, category_id, language, names))

    categories_by_id = {
        cat.id: cat.name for cat in db.session.scalars(sa.select(Category)).all()
    }
    image_rows = {}
    if referenced_names:
        image_rows = {
            img.filename: img
            for img in db.session.scalars(
                sa.select(Image).where(Image.filename.in_(referenced_names))
            ).all()
        }

    # Pre-check media availability before creating output files.
    missing_media: list[str] = []
    media_to_copy: dict[str, Path] = {}
    videos_to_copy: dict[str, Path] = {}
    for post, _title, _body, _cat_id, _lang, names in post_sources:
        for filename in names:
            src = uploads / filename
            if not src.is_file():
                missing_media.append(f'post:{post.id} missing /files/{filename}')
                continue
            media_to_copy[filename] = src
            row = image_rows.get(filename)
            if row and row.video_filename:
                video_src = uploads / row.video_filename
                if video_src.is_file():
                    videos_to_copy[row.video_filename] = video_src
                else:
                    missing_media.append(
                        f'post:{post.id} missing Live Photo clip /files/{row.video_filename}'
                    )

    if missing_media and not allow_missing_media:
        raise ContentExportError(
            f'Export aborted: {len(missing_media)} referenced media file(s) missing on disk.',
            diagnostics=missing_media,
        )

    posts_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    media_hashes: dict[str, str] = {}
    for filename, src in sorted(media_to_copy.items()):
        dest = media_dir / filename
        shutil.copy2(src, dest)
        media_hashes[filename] = sha256_file(dest)

    video_hashes: dict[str, str] = {}
    for vname, src in sorted(videos_to_copy.items()):
        dest = media_dir / vname
        shutil.copy2(src, dest)
        video_hashes[vname] = sha256_file(dest)

    used_filenames: set[str] = set()
    post_manifest_entries: list[dict[str, Any]] = []
    post_files: list[str] = []

    for post, title, body, category_id, language, names in post_sources:
        slug = _post_slug(post)
        date_prefix = to_display(post.timestamp).strftime('%Y-%m-%d')
        candidate = f'{date_prefix}-{slug}.md'
        if candidate in used_filenames:
            candidate = f'{date_prefix}-{slug}-{post.id}.md'
        used_filenames.add(candidate)

        rewrite_map = {
            name: f'../media/{name}' for name in names if name in media_hashes
        }
        exported_body = _rewrite_export_media_paths(body, rewrite_map)

        media_entries: list[dict[str, Any]] = []
        for name in names:
            if name not in media_hashes:
                continue
            row = image_rows.get(name)
            entry: dict[str, Any] = {
                'path': f'../media/{name}',
                'filename': name,
                'sha256': media_hashes[name],
                'original_name': row.original_name if row else name,
                'title': row.title if row else Path(name).stem,
                'note': row.note if row else None,
            }
            if row and row.video_filename and row.video_filename in video_hashes:
                entry['video_path'] = f'../media/{row.video_filename}'
                entry['video_filename'] = row.video_filename
                entry['video_sha256'] = video_hashes[row.video_filename]
            media_entries.append(entry)

        metadata: dict[str, Any] = {
            'title': title,
            'slug': slug,
            'id': post.id,
            'legacy_id': post.legacy_id,
            'author': post.author.username if post.author else None,
            'category': categories_by_id.get(category_id) if category_id is not None else None,
            'tags': [],
            'published_at': _iso_display(post.timestamp),
            'updated_at': _iso_display(post.updated_at),
            'scheduled_at': _iso_display(post.scheduled_at),
            'is_published': bool(post.is_published),
            'body_format': normalize_body_format(post.body_format),
            'comments_enabled': bool(post.comments_enabled),
            'language': language or None,
            'media': media_entries,
        }
        content = dump_front_matter(metadata) + '\n' + exported_body
        if not content.endswith('\n'):
            content += '\n'
        post_path = posts_dir / candidate
        post_path.write_text(content, encoding='utf-8')
        rel_post_path = f'posts/{candidate}'
        post_files.append(rel_post_path)
        post_manifest_entries.append({
            'path': rel_post_path,
            'slug': slug,
            'sha256': sha256_file(post_path),
        })

    manifest = {
        'version': EXPORT_FORMAT_VERSION,
        'exported_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'posts_count': len(post_manifest_entries),
        'media_count': len(media_hashes),
        'videos_count': len(video_hashes),
        'posts': post_manifest_entries,
        'media': [
            {'path': f'media/{name}', 'filename': name, 'sha256': digest}
            for name, digest in sorted(media_hashes.items())
        ],
        'videos': [
            {'path': f'media/{name}', 'filename': name, 'sha256': digest}
            for name, digest in sorted(video_hashes.items())
        ],
    }
    manifest_path = target_root / 'manifest.json'
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    return ExportResult(
        output_dir=target_root,
        exported_posts=len(post_manifest_entries),
        exported_media=len(media_hashes),
        exported_videos=len(video_hashes),
        post_files=post_files,
        missing_media=missing_media,
        manifest_path=manifest_path,
    )


def _is_local_media_ref(raw_ref: str, *, always_media: bool = False) -> bool:
    ref = raw_ref.strip()
    if not ref or ref.startswith('#') or ref.startswith('//'):
        return False
    parsed = urlsplit(ref)
    if parsed.scheme.lower() in _EXTERNAL_SCHEMES:
        return False
    if parsed.netloc:
        return False
    path = unquote(parsed.path)
    if path.startswith('/'):
        return path.startswith('/files/') or always_media
    if always_media:
        return True
    suffix = Path(path).suffix.lower()
    return (
        'media/' in path
        or path.startswith('media/')
        or suffix in ('.png', '.jpg', '.jpeg', '.gif', '.mp4')
    )


def _extract_body_media_refs(body: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in _MD_LINK_RE.finditer(body):
        is_image = match.group(1).startswith('!')
        ref = match.group(2)
        if _is_local_media_ref(ref, always_media=is_image) and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    for match in _HTML_ATTR_RE.finditer(body):
        is_src = match.group(1).strip().lower().startswith('src')
        ref = match.group(3)
        if _is_local_media_ref(ref, always_media=is_src) and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _resolve_bundle_media_path(
    bundle_root: Path, doc_path: Path, raw_ref: str, source_label: str
) -> Path:
    parsed = urlsplit(raw_ref.strip())
    rel_text = unquote(parsed.path)
    if rel_text.startswith('/files/'):
        name = rel_text.removeprefix('/files/')
        if '/' in name or '\\' in name or '..' in name:
            raise ContentImportError(
                f'{source_label}: unsafe media reference {raw_ref!r}')
        candidate = bundle_root / 'media' / name
    elif os.path.isabs(rel_text) or rel_text.startswith('\\'):
        raise ContentImportError(
            f'{source_label}: absolute media path is not allowed: {raw_ref!r}')
    else:
        candidate = doc_path.parent / rel_text

    resolved_root = bundle_root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ContentImportError(
            f'{source_label}: media path escapes import directory: {raw_ref!r}')
    return resolved


def _rewrite_import_media_paths(body: str, ref_to_url: dict[str, str]) -> str:
    if not ref_to_url:
        return body

    def repl_md(match: re.Match[str]) -> str:
        ref = match.group(2)
        if ref in ref_to_url:
            return f'{match.group(1)}{ref_to_url[ref]}{match.group(3)}'
        return match.group(0)

    def repl_html(match: re.Match[str]) -> str:
        ref = match.group(3)
        if ref in ref_to_url:
            return f'{match.group(1)}{match.group(2)}{ref_to_url[ref]}{match.group(2)}'
        return match.group(0)

    body = _MD_LINK_RE.sub(repl_md, body)
    return _HTML_ATTR_RE.sub(repl_html, body)


@dataclass
class _PlannedMedia:
    target_filename: str
    source_path: Path
    raw_bytes: bytes
    sha256: str
    width: int | None
    height: int | None
    original_name: str
    title: str
    note: str | None
    action: str  # 'create' | 'reuse' | 'overwrite'
    create_db_row: bool
    video_filename: str | None = None
    video_source_path: Path | None = None
    video_bytes: bytes | None = None
    video_action: str | None = None  # 'create' | 'reuse' | 'overwrite'


@dataclass
class _PlannedPost:
    source_label: str
    slug: str
    legacy_id: int | None
    title: str
    body: str
    body_format: str
    category_name: str | None
    author_username: str | None
    timestamp: datetime
    updated_at: datetime | None
    scheduled_at: datetime | None
    is_published: bool
    comments_enabled: bool
    language: str | None
    action: str  # 'create' | 'skip' | 'update'
    existing_post_id: int | None = None


def _normalize_dt_seconds(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0)


def _find_existing_post(
    legacy_id: int | None, title: str, timestamp: datetime
) -> Post | None:
    if legacy_id is not None:
        by_legacy = db.session.scalar(
            sa.select(Post)
            .options(so.selectinload(Post.category), so.selectinload(Post.draft))
            .where(Post.legacy_id == legacy_id)
        )
        if by_legacy is not None:
            return by_legacy

    target_ts = _normalize_dt_seconds(timestamp)
    candidates = db.session.scalars(
        sa.select(Post)
        .options(so.selectinload(Post.category), so.selectinload(Post.draft))
        .where(
            sa.or_(
                Post.title == title,
                Post.draft.has(PostDraft.title == title),
            )
        )
    ).all()
    for candidate in candidates:
        cand_title = (
            candidate.draft.title
            if (not candidate.is_published and candidate.draft is not None)
            else candidate.title
        )
        if cand_title == title and _normalize_dt_seconds(candidate.timestamp) == target_ts:
            return candidate
    return None


def _post_diff_fields(existing: Post, planned_fields: dict[str, Any]) -> list[str]:
    source = (
        existing.draft
        if (not existing.is_published and existing.draft is not None)
        else existing
    )
    existing_category = None
    if source.category_id is not None:
        cat = db.session.get(Category, source.category_id)
        existing_category = cat.name if cat else None

    diffs: list[str] = []
    if (source.title or '') != planned_fields['title']:
        diffs.append('title')
    if (source.body or '').rstrip('\n') != planned_fields['body'].rstrip('\n'):
        diffs.append('body')
    if normalize_body_format(existing.body_format) != planned_fields['body_format']:
        diffs.append('body_format')
    if existing_category != planned_fields['category_name']:
        diffs.append('category')
    if bool(existing.is_published) != bool(planned_fields['is_published']):
        diffs.append('is_published')
    if bool(existing.comments_enabled) != bool(planned_fields['comments_enabled']):
        diffs.append('comments_enabled')
    if _normalize_dt_seconds(existing.timestamp) != _normalize_dt_seconds(planned_fields['timestamp']):
        diffs.append('published_at')
    if _normalize_dt_seconds(existing.updated_at) != _normalize_dt_seconds(planned_fields['updated_at']):
        diffs.append('updated_at')
    if _normalize_dt_seconds(existing.scheduled_at) != _normalize_dt_seconds(planned_fields['scheduled_at']):
        diffs.append('scheduled_at')
    return diffs


def _discover_markdown_files(bundle_root: Path) -> list[Path]:
    posts_dir = bundle_root / 'posts'
    if posts_dir.is_dir():
        return sorted(p for p in posts_dir.glob('*.md') if p.is_file())
    return sorted(p for p in bundle_root.glob('*.md') if p.is_file())


def _resolve_author(
    explicit_username: str | None,
    doc_username: str | None,
    source_label: str,
) -> User:
    for candidate in (explicit_username, doc_username):
        if candidate:
            user = db.session.scalar(sa.select(User).where(User.username == candidate))
            if user is not None:
                return user
            if candidate == explicit_username:
                raise ContentImportError(
                    f'{source_label}: specified author {candidate!r} does not exist')
    fallback = db.session.scalar(
        sa.select(User).where(User.role == 'admin').order_by(User.id.asc())
    ) or db.session.scalar(sa.select(User).order_by(User.id.asc()))
    if fallback is None:
        raise ContentImportError(
            f'{source_label}: no user exists in database to own imported posts')
    return fallback


def _before_commit_hook() -> None:
    """Extension point used by rollback tests to inject commit-phase failures."""


def import_posts_bundle(
    input_dir: str | Path,
    *,
    default_author: str | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> ImportResult:
    """Validate, stage, and atomically import a Markdown + media bundle.

    - Idempotent: re-importing an unchanged bundle skips existing posts and reuses
      identical media without creating duplicates.
    - Safe by default: never overwrites conflicting posts or media unless
      ``overwrite=True``.
    - Recoverable: validates everything before touching DB/disk, stages media
      writes, and rolls back both DB and uploaded files on any commit failure.
    """
    bundle_root = Path(input_dir).resolve()
    if not bundle_root.is_dir():
        raise ContentImportError(f'Import directory does not exist: {bundle_root}')

    md_files = _discover_markdown_files(bundle_root)
    if not md_files:
        raise ContentImportError(f'No Markdown files found in {bundle_root}')

    uploads = upload_folder()
    diagnostics: list[str] = []
    warnings: list[str] = []

    planned_media: dict[str, _PlannedMedia] = {}
    planned_posts: list[_PlannedPost] = []
    seen_slugs: dict[str, str] = {}
    seen_legacy_ids: dict[int, str] = {}
    seen_title_ts: dict[tuple[str, datetime], str] = {}

    # Stage 1: full read-only validation and planning.
    for md_path in md_files:
        rel_label = str(md_path.relative_to(bundle_root))
        try:
            raw_text = md_path.read_text(encoding='utf-8')
            metadata, raw_body = parse_markdown_document(raw_text, source_name=rel_label)
        except (OSError, ContentImportError) as exc:
            diagnostics.append(str(exc))
            continue

        title = metadata.get('title')
        if not isinstance(title, str) or not title.strip():
            diagnostics.append(f'{rel_label}: front matter "title" is required')
            continue
        title = title.strip()
        if len(title) > 120:
            diagnostics.append(f'{rel_label}: title exceeds 120 characters')
            continue

        raw_slug = metadata.get('slug')
        slug = (raw_slug.strip() if isinstance(raw_slug, str) and raw_slug.strip()
                else md_path.stem.lower())
        if not _SAFE_SLUG_RE.match(slug):
            diagnostics.append(f'{rel_label}: invalid slug {slug!r}')
            continue
        if slug in seen_slugs:
            diagnostics.append(
                f'{rel_label}: duplicate slug {slug!r} (already in {seen_slugs[slug]})')
            continue
        seen_slugs[slug] = rel_label

        legacy_id = metadata.get('legacy_id')
        if legacy_id is not None:
            if isinstance(legacy_id, bool) or not isinstance(legacy_id, int) or legacy_id < 1:
                diagnostics.append(f'{rel_label}: legacy_id must be a positive integer')
                continue
            if legacy_id in seen_legacy_ids:
                diagnostics.append(
                    f'{rel_label}: duplicate legacy_id {legacy_id} '
                    f'(already in {seen_legacy_ids[legacy_id]})')
                continue
            seen_legacy_ids[legacy_id] = rel_label

        raw_tags = metadata.get('tags', [])
        if raw_tags is not None:
            if not isinstance(raw_tags, list) or not all(isinstance(t, str) for t in raw_tags):
                diagnostics.append(f'{rel_label}: tags must be a list of strings')
                continue
            if raw_tags:
                warnings.append(
                    f'{rel_label}: tags {raw_tags!r} noted (Flog stores categories only)')

        body_format = metadata.get('body_format') or BODY_FORMAT_MARKDOWN
        if body_format not in CONTENT_FORMATS:
            diagnostics.append(
                f'{rel_label}: unsupported body_format {body_format!r}')
            continue

        try:
            timestamp = _parse_datetime(
                metadata.get('published_at') or metadata.get('date'),
                'published_at',
                rel_label,
            )
            if timestamp is None:
                raise ContentImportError(
                    f'{rel_label}: front matter "published_at" (or "date") is required for idempotent import')
            updated_at = _parse_datetime(metadata.get('updated_at'), 'updated_at', rel_label)
            scheduled_at = _parse_datetime(metadata.get('scheduled_at'), 'scheduled_at', rel_label)
        except ContentImportError as exc:
            diagnostics.append(str(exc))
            continue

        is_published = metadata.get('is_published', True)
        if not isinstance(is_published, bool):
            diagnostics.append(f'{rel_label}: is_published must be a boolean')
            continue
        comments_enabled = metadata.get('comments_enabled', True)
        if not isinstance(comments_enabled, bool):
            diagnostics.append(f'{rel_label}: comments_enabled must be a boolean')
            continue
        if is_published and scheduled_at is not None:
            diagnostics.append(
                f'{rel_label}: published post cannot also carry scheduled_at')
            continue

        category_name = metadata.get('category')
        if category_name is not None:
            if not isinstance(category_name, str) or not category_name.strip():
                diagnostics.append(f'{rel_label}: category must be a non-empty string or null')
                continue
            category_name = category_name.strip()
            if len(category_name) > 120:
                diagnostics.append(f'{rel_label}: category exceeds 120 characters')
                continue

        title_ts_key = (title, timestamp)
        if title_ts_key in seen_title_ts:
            diagnostics.append(
                f'{rel_label}: duplicate post title+published_at '
                f'(already in {seen_title_ts[title_ts_key]})')
            continue
        seen_title_ts[title_ts_key] = rel_label

        # Collect media declarations from front matter and references from body.
        fm_media_raw = metadata.get('media') or []
        if not isinstance(fm_media_raw, list):
            diagnostics.append(f'{rel_label}: media front matter must be a list')
            continue
        fm_media_by_ref: dict[str, dict[str, Any]] = {}
        fm_valid = True
        for item in fm_media_raw:
            if not isinstance(item, dict) or not isinstance(item.get('path'), str):
                diagnostics.append(f'{rel_label}: each media entry must be a mapping with "path"')
                fm_valid = False
                break
            fm_media_by_ref[item['path']] = item
        if not fm_valid:
            continue

        body_refs = _extract_body_media_refs(raw_body)
        all_refs = list(dict.fromkeys([*body_refs, *fm_media_by_ref.keys()]))
        ref_to_url: dict[str, str] = {}
        media_failed = False

        for ref in all_refs:
            try:
                resolved = _resolve_bundle_media_path(bundle_root, md_path, ref, rel_label)
            except ContentImportError as exc:
                diagnostics.append(str(exc))
                media_failed = True
                continue

            if not resolved.is_file():
                diagnostics.append(f'{rel_label}: missing media file {ref!r}')
                media_failed = True
                continue

            raw_bytes = resolved.read_bytes()
            digest = sha256_bytes(raw_bytes)
            declared = fm_media_by_ref.get(ref, {})
            declared_sha = declared.get('sha256')
            if declared_sha and declared_sha != digest:
                diagnostics.append(
                    f'{rel_label}: checksum mismatch for media {ref!r} '
                    f'(expected {declared_sha}, got {digest})')
                media_failed = True
                continue

            ext = resolved.suffix.lower()
            if not _has_image_signature(ext, raw_bytes[:16]):
                diagnostics.append(
                    f'{rel_label}: unsupported or invalid image file {ref!r}')
                media_failed = True
                continue
            width, height = read_dimensions(resolved)
            if width is None or height is None:
                diagnostics.append(f'{rel_label}: unreadable image {ref!r}')
                media_failed = True
                continue

            declared_filename = declared.get('filename')
            if isinstance(declared_filename, str) and IMAGE_NAME_RE.match(declared_filename):
                target_name = declared_filename
            elif IMAGE_NAME_RE.match(resolved.name):
                target_name = resolved.name
            else:
                target_name = f'{digest[:32]}{ext}'

            # Live Photo companion clip, if declared.
            clip_target: str | None = None
            clip_path: Path | None = None
            clip_bytes: bytes | None = None
            clip_action: str | None = None
            raw_vpath = declared.get('video_path')
            if raw_vpath:
                try:
                    clip_path = _resolve_bundle_media_path(
                        bundle_root, md_path, str(raw_vpath), rel_label)
                except ContentImportError as exc:
                    diagnostics.append(str(exc))
                    media_failed = True
                    continue
                if not clip_path.is_file():
                    diagnostics.append(
                        f'{rel_label}: missing Live Photo video {raw_vpath!r}')
                    media_failed = True
                    continue
                clip_bytes = clip_path.read_bytes()
                clip_sha = sha256_bytes(clip_bytes)
                if declared.get('video_sha256') and declared['video_sha256'] != clip_sha:
                    diagnostics.append(
                        f'{rel_label}: checksum mismatch for video {raw_vpath!r}')
                    media_failed = True
                    continue
                if not has_video_signature(clip_bytes[:12]):
                    diagnostics.append(
                        f'{rel_label}: invalid Live Photo video {raw_vpath!r}')
                    media_failed = True
                    continue
                declared_vname = declared.get('video_filename')
                if isinstance(declared_vname, str) and _VIDEO_NAME_RE.match(declared_vname):
                    clip_target = declared_vname
                else:
                    clip_target = video_filename(Path(target_name).stem)

            if target_name in planned_media:
                prev = planned_media[target_name]
                if prev.sha256 != digest:
                    diagnostics.append(
                        f'{rel_label}: media path conflict within bundle for '
                        f'{target_name!r} ({ref!r} vs {prev.source_path.name!r})')
                    media_failed = True
                    continue
            else:
                existing_disk = uploads / target_name
                existing_row = db.session.scalar(
                    sa.select(Image).where(Image.filename == target_name))
                if existing_disk.is_file():
                    existing_sha = sha256_file(existing_disk)
                    if existing_sha == digest:
                        action = 'reuse'
                    elif overwrite:
                        action = 'overwrite'
                    else:
                        diagnostics.append(
                            f'{rel_label}: media path conflict on disk for '
                            f'/files/{target_name} (different content; pass --overwrite to replace)')
                        media_failed = True
                        continue
                else:
                    action = 'create'

                if clip_target and clip_bytes is not None:
                    existing_clip = uploads / clip_target
                    if existing_clip.is_file():
                        if sha256_file(existing_clip) == sha256_bytes(clip_bytes):
                            clip_action = 'reuse'
                        elif overwrite:
                            clip_action = 'overwrite'
                        else:
                            diagnostics.append(
                                f'{rel_label}: media path conflict on disk for '
                                f'/files/{clip_target} (different content; pass --overwrite to replace)')
                            media_failed = True
                            continue
                    else:
                        clip_action = 'create'

                orig_name = str(declared.get('original_name') or resolved.name)[:255]
                img_title = str(declared.get('title') or Path(orig_name).stem)[:120]
                img_note = (str(declared['note'])[:500]
                            if declared.get('note') not in (None, '') else None)
                planned_media[target_name] = _PlannedMedia(
                    target_filename=target_name,
                    source_path=resolved,
                    raw_bytes=raw_bytes,
                    sha256=digest,
                    width=width,
                    height=height,
                    original_name=orig_name,
                    title=img_title,
                    note=img_note,
                    action=action,
                    create_db_row=existing_row is None,
                    video_filename=clip_target,
                    video_source_path=clip_path,
                    video_bytes=clip_bytes,
                    video_action=clip_action,
                )
            ref_to_url[ref] = f'/files/{target_name}'

        if media_failed:
            continue

        rewritten_body = _rewrite_import_media_paths(raw_body, ref_to_url)
        if body_format == BODY_FORMAT_HTML:
            rewritten_body = prepare_content_source(rewritten_body, BODY_FORMAT_HTML)
        else:
            rewritten_body = rewritten_body.rstrip('\n')

        author_username = (metadata.get('author')
                           if isinstance(metadata.get('author'), str) else None)
        try:
            _resolve_author(default_author, author_username, rel_label)
        except ContentImportError as exc:
            diagnostics.append(str(exc))
            continue

        existing_post = _find_existing_post(legacy_id, title, timestamp)
        post_action = 'create'
        existing_post_id: int | None = None
        if existing_post is not None:
            existing_post_id = existing_post.id
            diffs = _post_diff_fields(existing_post, {
                'title': title,
                'body': rewritten_body,
                'body_format': body_format,
                'category_name': category_name,
                'is_published': is_published,
                'comments_enabled': comments_enabled,
                'timestamp': timestamp,
                'updated_at': updated_at,
                'scheduled_at': scheduled_at,
            })
            if not diffs:
                post_action = 'skip'
            elif overwrite:
                post_action = 'update'
            else:
                diagnostics.append(
                    f'{rel_label}: conflicts with existing post #{existing_post.id} '
                    f'(differs in: {", ".join(diffs)}; pass --overwrite to replace)')
                continue

        planned_posts.append(_PlannedPost(
            source_label=rel_label,
            slug=slug,
            legacy_id=legacy_id,
            title=title,
            body=rewritten_body,
            body_format=body_format,
            category_name=category_name,
            author_username=author_username,
            timestamp=timestamp,
            updated_at=updated_at,
            scheduled_at=scheduled_at,
            is_published=is_published,
            comments_enabled=comments_enabled,
            language=(metadata.get('language')
                      if isinstance(metadata.get('language'), str) else None),
            action=post_action,
            existing_post_id=existing_post_id,
        ))

    if diagnostics:
        raise ContentImportError(
            f'Import validation failed with {len(diagnostics)} error(s); no changes were made.',
            diagnostics=diagnostics,
        )

    result = ImportResult(dry_run=dry_run, warnings=warnings)
    if dry_run:
        for item in planned_media.values():
            if item.action == 'create':
                result.created_media += 1
            elif item.action == 'overwrite':
                result.overwritten_media += 1
            else:
                result.reused_media += 1
        existing_cats = set(db.session.scalars(sa.select(Category.name)).all())
        needed_cats = sorted({
            p.category_name for p in planned_posts
            if p.category_name and p.category_name not in existing_cats
        })
        result.created_categories = needed_cats
        for post_plan in planned_posts:
            if post_plan.action == 'create':
                result.created_posts += 1
            elif post_plan.action == 'update':
                result.updated_posts += 1
            else:
                result.skipped_posts += 1
        return result

    # Stage 2: stage files on disk, apply DB + upload mutations, and roll back cleanly on failure.
    uploads.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix='.import-staging-', dir=str(uploads)))
    backup_dir = staging_dir / 'backup'
    backup_dir.mkdir(exist_ok=True)
    created_paths: list[Path] = []
    overwritten_backups: list[tuple[Path, Path]] = []

    try:
        # Prepare staged files first so disk space/IO errors happen before mutation.
        staged_writes: list[tuple[Path, Path, str]] = []
        for item in planned_media.values():
            if item.action in ('create', 'overwrite'):
                staged_file = staging_dir / item.target_filename
                staged_file.write_bytes(item.raw_bytes)
                staged_writes.append((staged_file, uploads / item.target_filename, item.action))
            if item.video_filename and item.video_bytes is not None and item.video_action in ('create', 'overwrite'):
                staged_clip = staging_dir / item.video_filename
                staged_clip.write_bytes(item.video_bytes)
                staged_writes.append((staged_clip, uploads / item.video_filename, item.video_action))

        # Ensure categories exist.
        category_map = {
            cat.name: cat for cat in db.session.scalars(sa.select(Category)).all()
        }
        for post_plan in planned_posts:
            if post_plan.category_name and post_plan.category_name not in category_map:
                cat = Category(name=post_plan.category_name)
                db.session.add(cat)
                db.session.flush()
                category_map[cat.name] = cat
                result.created_categories.append(cat.name)

        # Move staged media into place while keeping backups for rollback.
        for staged_file, dest_path, action in staged_writes:
            if action == 'overwrite' and dest_path.is_file():
                backup_copy = backup_dir / dest_path.name
                shutil.copy2(dest_path, backup_copy)
                overwritten_backups.append((dest_path, backup_copy))
                os.replace(staged_file, dest_path)
            else:
                os.replace(staged_file, dest_path)
                created_paths.append(dest_path)

        # Sync Image database records.
        default_user = _resolve_author(default_author, None, 'import')
        for item in planned_media.values():
            if item.action == 'create':
                result.created_media += 1
            elif item.action == 'overwrite':
                result.overwritten_media += 1
            else:
                result.reused_media += 1

            existing_img = db.session.scalar(
                sa.select(Image).where(Image.filename == item.target_filename))
            if existing_img is None:
                db.session.add(Image(
                    filename=item.target_filename,
                    original_name=item.original_name,
                    title=item.title,
                    note=item.note,
                    size=len(item.raw_bytes),
                    width=item.width,
                    height=item.height,
                    video_filename=item.video_filename,
                    user_id=default_user.id,
                ))
            elif item.action == 'overwrite':
                existing_img.size = len(item.raw_bytes)
                existing_img.width = item.width
                existing_img.height = item.height
                existing_img.title = item.title
                existing_img.note = item.note
                if item.video_filename:
                    existing_img.video_filename = item.video_filename

        # Apply posts.
        for post_plan in planned_posts:
            if post_plan.action == 'skip':
                result.skipped_posts += 1
                continue
            author = _resolve_author(
                default_author, post_plan.author_username, post_plan.source_label)
            cat_id = (
                category_map[post_plan.category_name].id
                if post_plan.category_name else None
            )
            if post_plan.action == 'create':
                post = Post(
                    legacy_id=post_plan.legacy_id,
                    title=post_plan.title if post_plan.is_published else '',
                    body=post_plan.body if post_plan.is_published else '',
                    body_format=post_plan.body_format,
                    is_published=post_plan.is_published,
                    comments_enabled=post_plan.comments_enabled,
                    timestamp=post_plan.timestamp,
                    updated_at=post_plan.updated_at,
                    scheduled_at=post_plan.scheduled_at,
                    author=author,
                    category_id=cat_id if post_plan.is_published else None,
                    language=post_plan.language,
                )
                db.session.add(post)
                db.session.flush()
                if not post_plan.is_published:
                    post.draft = PostDraft(
                        title=post_plan.title,
                        body=post_plan.body,
                        category_id=cat_id,
                        language=post_plan.language,
                    )
                result.created_posts += 1
            else:
                existing_post = db.session.get(Post, post_plan.existing_post_id)
                assert existing_post is not None
                existing_post.legacy_id = post_plan.legacy_id
                existing_post.body_format = post_plan.body_format
                existing_post.is_published = post_plan.is_published
                existing_post.comments_enabled = post_plan.comments_enabled
                existing_post.timestamp = post_plan.timestamp
                existing_post.updated_at = post_plan.updated_at
                existing_post.scheduled_at = post_plan.scheduled_at
                existing_post.language = post_plan.language
                if post_plan.is_published:
                    existing_post.title = post_plan.title
                    existing_post.body = post_plan.body
                    existing_post.category_id = cat_id  # type: ignore[assignment]
                    existing_post.draft = None
                else:
                    if existing_post.draft is None:
                        existing_post.draft = PostDraft(title='', body='')
                        db.session.add(existing_post.draft)
                    existing_post.draft.title = post_plan.title
                    existing_post.draft.body = post_plan.body
                    existing_post.draft.category_id = cat_id
                    existing_post.draft.language = post_plan.language
                result.updated_posts += 1

        db.session.flush()
        _before_commit_hook()
        db.session.commit()
        return result
    except Exception as exc:
        db.session.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        for dest_path, backup_copy in overwritten_backups:
            if backup_copy.is_file():
                shutil.copy2(backup_copy, dest_path)
        if isinstance(exc, ContentImportError):
            raise
        raise ContentImportError(
            f'Import aborted and rolled back cleanly due to error: {exc}',
            diagnostics=[f'rollback completed after commit error: {exc}'],
        ) from exc
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
