"""Application version and Git commit metadata for the admin interface."""
from functools import lru_cache
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parent.parent
_HEX_SHA = re.compile(r'^[0-9a-f]{7,40}$')


def _git_dir(root: Path) -> Path | None:
    dot_git = root / '.git'
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        content = dot_git.read_text(encoding='utf-8').strip()
        if content.startswith('gitdir:'):
            target = Path(content.split(':', 1)[1].strip())
            return target if target.is_absolute() else (root / target).resolve()
    return None


def _resolve_ref(git_dir: Path, ref: str) -> str | None:
    ref_file = git_dir / ref
    if ref_file.is_file():
        return ref_file.read_text(encoding='utf-8').strip()
    packed_refs = git_dir / 'packed-refs'
    if packed_refs.is_file():
        for line in packed_refs.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('^'):
                continue
            parts = line.split(' ', 1)
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    return None


def git_commit(root: Path = ROOT) -> str | None:
    """Short 7-character Git SHA from ``.git/HEAD``, or None outside a checkout."""
    git_dir = _git_dir(root)
    if git_dir is None:
        return None
    head_file = git_dir / 'HEAD'
    if not head_file.is_file():
        return None
    head = head_file.read_text(encoding='utf-8').strip()
    if head.startswith('ref:'):
        ref = head.split(':', 1)[1].strip()
        sha = _resolve_ref(git_dir, ref)
        if sha is None:
            common = git_dir / 'commondir'
            if common.is_file():
                shared_dir = (git_dir / common.read_text(encoding='utf-8').strip()).resolve()
                sha = _resolve_ref(shared_dir, ref)
    else:
        sha = head
    if sha and _HEX_SHA.fullmatch(sha.lower()):
        return sha.lower()[:7]
    return None


def app_version(root: Path = ROOT) -> str:
    """Read the semantic version from ``pyproject.toml``."""
    pyproject = root / 'pyproject.toml'
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding='utf-8'))
        version = data.get('project', {}).get('version')
        if isinstance(version, str) and version.strip():
            return version.strip()
    return '0.0.0'


@lru_cache(maxsize=1)
def version_info() -> dict[str, str | None]:
    version = app_version()
    commit = git_commit()
    label = f'v{version} ({commit})' if commit else f'v{version}'
    return {'version': version, 'commit': commit, 'label': label}
