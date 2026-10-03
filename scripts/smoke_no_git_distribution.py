"""Run only in a genuinely Git-free Linux consumer, with no source checkout."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PUBLIC_REQUIREMENT = 'papergraph-mcp==1.2.0'
PUBLIC_INDEX = 'https://pypi.org/simple'
PUBLIC_SOURCE_SHA = '60977c06217905e5c1db15fbf27aff4ca208a517'
PUBLIC_SOURCE_DIGEST = '9e873fd94cfa16b41b67acd2a1b19caab7083717b36e758553873bb9153da58a'


def consumer_command(uvx, artifact=None, *, public_index=False):
    if public_index:
        if artifact is not None:
            raise ValueError('Public-index acceptance cannot use a local artifact')
        return [uvx, '--no-config', '--no-env-file', '--default-index', PUBLIC_INDEX,
                '--from', PUBLIC_REQUIREMENT, 'papergraph-mcp']
    if artifact is None:
        raise ValueError('Local-artifact acceptance requires an artifact')
    return [uvx, '--from', str(artifact), 'papergraph-mcp']


def consumer_environment(cache, tool_dir, *, public_index=False):
    env = dict(os.environ)
    if public_index:
        env = {key: value for key, value in env.items()
               if not key.startswith('UV_') and key not in {'PYTHONPATH', 'PYTHONHOME'}}
    env.update(UV_CACHE_DIR=str(cache), UV_TOOL_DIR=str(tool_dir), UV_PYTHON_DOWNLOADS='never')
    return env


def validate_public_identity(identity):
    expected = {'schema_version': 1, 'origin': 'git_checkout',
                'source_commit': PUBLIC_SOURCE_SHA, 'source_tree_sha256': PUBLIC_SOURCE_DIGEST,
                'tracked_dirty': False}
    if any(identity.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Installed package does not have the reviewed public release identity')


def check_environment():
    if shutil.which('git') is not None:
        raise RuntimeError('Git must be absent from the original container PATH')
    try:
        subprocess.run(['git', '--version'], capture_output=True, check=False)
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError('Git must be absent: execution unexpectedly succeeded')
    if sys.platform != 'linux':
        raise RuntimeError('A fresh Linux container is required for this acceptance check')
    status = subprocess.run(['dpkg-query', '-W', '-f=${Status}', 'git'],
                            capture_output=True, text=True, check=False)
    if status.returncode == 0 and 'install ok installed' in status.stdout:
        raise RuntimeError('Git must be absent from the container package database')
    assert not any(Path(p).exists() for p in ('/usr/bin/git', '/usr/local/bin/git', '/bin/git'))
    print(json.dumps({'git_executable': 'absent', 'git_package': 'not_installed',
                      'platform': sys.platform, 'python': sys.version.split()[0]}), flush=True)


def run_cli(command, env, timeout):
    result = subprocess.run(command, env=env, capture_output=True, text=True,
                            check=False, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'Consumer CLI exited {result.returncode}: {result.stderr[-6000:]}')
    return result.stdout


async def verify(artifact, expected_sha, *, public_index=False):
    # Bootstrap and uvx both use the selected source, never an editable checkout.
    import papergraph
    import pymupdf as fitz
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    assert 'site-packages' in str(Path(papergraph.__file__).resolve())
    uvx = shutil.which('uvx')
    assert uvx
    command = consumer_command(uvx, artifact, public_index=public_index)
    with tempfile.TemporaryDirectory(prefix='papergraph-no-git-') as temp:
        root = Path(temp)
        cache = root / 'fresh-uvx-cache'
        assert not cache.exists()
        tool_dir = root / 'uv-tools'
        assert not tool_dir.exists()
        env = consumer_environment(cache, tool_dir, public_index=public_index)
        version = run_cli(command + ['--version'], env=env, timeout=240).strip()
        assert version == 'papergraph-mcp 1.2.0'
        doctor = json.loads(run_cli(command + ['doctor'], env=env, timeout=90))
        identity = doctor['build_identity']
        assert doctor['version'] == '1.2.0' and doctor['git'] is None
        assert identity['source_commit'] == expected_sha
        assert identity['tracked_dirty'] is False
        assert len(identity['source_tree_sha256']) == 64
        if public_index:
            validate_public_identity(identity)

        pdf = root / 'fixture.pdf'
        with fitz.open() as document:
            page = document.new_page()
            for i, line in enumerate(['Lemma 1.1. Base result.', 'Proof. Direct.',
                                      'Theorem 1.2. Main result.', 'Proof. By Lemma 1.1.']):
                page.insert_text((72, 72 + i * 18), line)
            document.save(pdf)
        params = StdioServerParameters(command=uvx, args=command[1:], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                initialized = await session.initialize()
                assert initialized.server_info.version == '1.2.0'
                tools = {tool.name for tool in (await session.list_tools()).tools}
                assert {'discover_doi_paper', 'workspace_add_doi_paper',
                        'workspace_import_doi_candidate', 'workspace_get_dependency_reading'} <= tools

                async def call(name, arguments):
                    result = await session.call_tool(name, arguments)
                    assert not result.is_error, result
                    return result.structured_content or json.loads(next(
                        c.text for c in result.content if c.type == 'text'))

                diagnostics = await call('get_environment_diagnostics', {})
                assert diagnostics['version'] == '1.2.0' and diagnostics['git'] is None
                assert diagnostics['build_identity'] == identity
                await call('open_workspace', {'path': str(root / 'workspace.sqlite3')})
                await call('workspace_add_pdf_paper', {'path': str(pdf), 'paper_id': 'local:no-git'})
                reading = await call('workspace_get_dependency_reading', {
                    'paper_id': 'local:no-git', 'target_result_id': 'local:no-git::pdf:theorem:1.2'})
                assert reading['paper']['result_count'] == 2
                assert reading['paper']['import_state']['body_imported'] is True
                assert [item['result_id'] for item in reading['reading_path']['bottom_up']] == [
                    'local:no-git::pdf:lemma:1.1', 'local:no-git::pdf:theorem:1.2']
        receipt = {'artifact': artifact.name if artifact else None, 'version': '1.2.0',
                   'build_identity': identity, 'git': 'absent', 'fresh_uvx_cache': True,
                   'cli_version_doctor': 'passed', 'stdio_initialize_tools_diagnostics': 'passed',
                   'generated_pdf_reading': 'passed', 'consumer_git_download': False}
        if public_index:
            receipt.update(install_source='public_index', requirement=PUBLIC_REQUIREMENT,
                           index=PUBLIC_INDEX, installed_local_artifact=False)
        print(json.dumps(receipt), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-environment', action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--artifact', type=Path)
    mode.add_argument('--public-index', action='store_true')
    parser.add_argument('--expected-sha')
    args = parser.parse_args()
    if args.public_index and args.expected_sha is not None:
        parser.error('--public-index has a fixed reviewed source; --expected-sha is not allowed')
    if not args.check_environment and not args.public_index and (args.artifact is None or args.expected_sha is None):
        parser.error('--artifact and --expected-sha are required unless --public-index is used')
    check_environment()
    if not args.check_environment:
        expected_sha = PUBLIC_SOURCE_SHA if args.public_index else args.expected_sha
        asyncio.run(asyncio.wait_for(verify(args.artifact, expected_sha, public_index=args.public_index), timeout=420))


if __name__ == '__main__':
    main()
