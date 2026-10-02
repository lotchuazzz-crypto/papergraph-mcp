"""Build provenance without private checkout paths or runtime-cwd assumptions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess


def _source_digest(root: Path) -> str:
    files = list((root / 'src' / 'papergraph').rglob('*.py'))
    files += [root / name for name in ('pyproject.toml', 'hatch_build.py')
              if (root / name).is_file()]
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        if '__pycache__' in path.parts:
            continue
        digest.update(path.relative_to(root).as_posix().encode('utf-8') + b'\0')
        digest.update(path.read_bytes() + b'\0')
    return digest.hexdigest()


def _read_manifest(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if (value.get('schema_version') != 1 or
            not re.fullmatch(r'[a-f0-9]{64}', value.get('source_tree_sha256', '')) or
            value.get('source_commit') is not None and
                not re.fullmatch(r'[a-f0-9]{40}', value['source_commit']) or
            value.get('origin') not in ('git_checkout', 'source_archive_unknown') or
            value.get('tracked_dirty') not in (True, False, None)):
            return None
        # Only the fixed public fields survive, even for supplied source archives.
        return {key: value.get(key) for key in (
            'schema_version', 'source_commit', 'tracked_dirty', 'source_tree_sha256', 'origin')}
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def build_source_identity(root: Path) -> dict:
    root = root.resolve()
    digest = _source_digest(root)
    identity = {'schema_version': 1, 'source_commit': None, 'tracked_dirty': None,
                'source_tree_sha256': digest, 'origin': 'source_archive_unknown'}
    try:
        def git(*args):
            return subprocess.run(['git', *args], cwd=root, check=True,
                                  capture_output=True, text=True, timeout=10).stdout.strip()
        if Path(git('rev-parse', '--show-toplevel')).resolve() == root:
            identity.update(source_commit=git('rev-parse', 'HEAD'),
                            tracked_dirty=bool(git('status', '--porcelain', '--untracked-files=no')),
                            origin='git_checkout')
            return identity
    except (OSError, subprocess.SubprocessError):
        pass
    saved = _read_manifest(root / 'src' / 'papergraph' / '_build_info.json')
    return saved if saved and saved['source_tree_sha256'] == digest else identity


def runtime_build_identity() -> dict:
    package = Path(__file__).resolve().parent
    # Editable/development code: inspect the actual module tree, not caller cwd.
    root = package.parent.parent
    if package.parent.name == 'src' and (root / 'pyproject.toml').is_file():
        return build_source_identity(root)
    saved = _read_manifest(package / '_build_info.json')
    return saved or {'schema_version': 1, 'source_commit': None, 'tracked_dirty': None,
                     'source_tree_sha256': None, 'origin': 'installed_build_unknown'}
