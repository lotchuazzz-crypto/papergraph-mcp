"""Check the reviewed v1.2.2 bytes and provenance without executing a package."""
import argparse
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import zipfile


SOURCE_SHA = '8da46bb3c95dd83b31815da6d33f636ea67ed2bb'
SOURCE_DIGEST = '704f2a4dc699cd44e337f51d3733e7fe9f9334cc9e4ffad797e7aa49ec4cae7c'
APPROVED_HASHES = {
    'papergraph_mcp-1.2.2-py3-none-any.whl': '3232f7501b21f15e7c270a62862451e07da8b12e7fbf1ac1c2c151a000ac78a2',
    'papergraph_mcp-1.2.2.tar.gz': '7ca61a9b601fa54e57e7e496f3f46bce312d4070a88e895c0d28563e76b29e4e',
}
EXPECTED_IDENTITY = {
    'schema_version': 1, 'source_commit': SOURCE_SHA,
    'source_tree_sha256': SOURCE_DIGEST, 'tracked_dirty': False,
    'origin': 'git_checkout',
}


def validate_run_identity(producer_run_id, consumer_run_id):
    if (not isinstance(producer_run_id, str) or
            not re.fullmatch(r'[1-9][0-9]*', producer_run_id) or
            producer_run_id != consumer_run_id):
        raise ValueError('Artifacts must come from the same workflow run')


def validate_distribution(path, expected_sha256):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected_sha256:
        raise ValueError(f'SHA-256 mismatch: {path.name}')
    if path.name.endswith('.whl'):
        with zipfile.ZipFile(path) as archive:
            manifest = archive.read('papergraph/_build_info.json')
            metadata = archive.read('papergraph_mcp-1.2.2.dist-info/METADATA')
    elif path.name.endswith('.tar.gz'):
        with tarfile.open(path, 'r:gz') as archive:
            def read_member(name):
                member = archive.getmember('papergraph_mcp-1.2.2/' + name)
                if not member.isfile():
                    raise ValueError('Distribution metadata must be a regular file')
                with archive.extractfile(member) as stream:
                    return stream.read()
            manifest = read_member('src/papergraph/_build_info.json')
            metadata = read_member('PKG-INFO')
    else:
        raise ValueError('Unsupported release distribution')
    identity = json.loads(manifest)
    if identity != EXPECTED_IDENTITY:
        raise ValueError(f'Unexpected release identity: {path.name}')
    package = BytesParser().parsebytes(metadata)
    if package.get_all('Name') != ['papergraph-mcp'] or package.get_all('Version') != ['1.2.2']:
        raise ValueError(f'Unexpected package metadata: {path.name}')
    return {'artifact': path.name, 'sha256': actual, 'build_identity': identity}


def verify_directory(directory):
    items = list(directory.iterdir())
    if (set(p.name for p in items) != set(APPROVED_HASHES) or
            any(not p.is_file() or p.is_symlink() for p in items)):
        raise ValueError('Directory must contain exactly the two approved distributions')
    return [validate_distribution(directory / name, digest)
            for name, digest in APPROVED_HASHES.items()]


def stage_candidates(source, destination):
    items = list(source.iterdir())
    names = set(p.name for p in items)
    approved = set(APPROVED_HASHES)
    if (names not in (approved, approved | {'.gitignore'}) or
            any(not p.is_file() or p.is_symlink() for p in items)):
        raise ValueError(f'Unexpected build output: {sorted(names)}')
    # uv creates a build-output .gitignore. It is never a distribution or copied.
    for name, digest in APPROVED_HASHES.items():
        validate_distribution(source / name, digest)
    destination.mkdir()  # Never overwrite an existing candidate directory.
    for name in APPROVED_HASHES:
        shutil.copyfile(source / name, destination / name)
    return verify_directory(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--producer-run-id')
    parser.add_argument('--stage-to', type=Path)
    args = parser.parse_args()
    try:
        if args.producer_run_id is not None:
            validate_run_identity(args.producer_run_id, os.environ.get('GITHUB_RUN_ID'))
        distributions = (stage_candidates(args.directory, args.stage_to)
                         if args.stage_to else verify_directory(args.directory))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, tarfile.TarError) as error:
        parser.exit(1, f'Release candidate verification failed: {error}\n')
    print(json.dumps({'version': '1.2.2', 'source_commit': SOURCE_SHA,
                      'producer_run_id': args.producer_run_id,
                      'distributions': distributions}))


if __name__ == '__main__':
    main()
