"""Execute the post-approval guard locally without a token or upload action."""
import ast
import hashlib
import os
import subprocess
import sys

from tests.test_pypi_publish_draft import validator, workflow


def guard():
    steps = workflow('pypi-publish.yml')['jobs']['publish']['steps']
    matches = [step for step in steps if step.get('name') == 'Recheck approved bytes after approval']
    assert len(matches) == 1, 'Post-approval byte guard has not been implemented'
    step = matches[0]
    assert step['env']['PRODUCER_RUN_ID'] == '${{ needs.build.outputs.producer_run_id }}'
    script = step['run'].split("python - <<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
    tree = ast.parse(script)
    values = {node.targets[0].id: ast.literal_eval(node.value)
              for node in tree.body if isinstance(node, ast.Assign)
              and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Dict)}
    assert values['approved'] == validator().APPROVED_HASHES
    return script


def run_guard(tmp_path, script, producer='101', current='101'):
    env = dict(os.environ, PRODUCER_RUN_ID=producer, GITHUB_RUN_ID=current)
    return subprocess.run([sys.executable, '-c', script], cwd=tmp_path,
                          env=env, text=True, capture_output=True, timeout=10)


def test_guard_accepts_only_matching_reviewed_bytes(tmp_path):
    script = guard()
    directory = tmp_path / 'dist'
    directory.mkdir()
    # Calibrate approved fixture bytes, while separately asserting production hashes.
    for name, approved_digest in validator().APPROVED_HASHES.items():
        data = name.encode()
        (directory / name).write_bytes(data)
        script = script.replace(approved_digest, hashlib.sha256(data).hexdigest())
    result = run_guard(tmp_path, script)
    assert result.returncode == 0, result.stderr


def test_guard_refuses_foreign_run_before_reading_artifact(tmp_path):
    result = run_guard(tmp_path, guard(), producer='100')
    assert result.returncode != 0
    assert 'same workflow run' in result.stderr


def test_guard_refuses_missing_or_extra_distribution(tmp_path):
    directory = tmp_path / 'dist'
    directory.mkdir()
    (directory / 'replacement.whl').write_bytes(b'replacement')
    result = run_guard(tmp_path, guard())
    assert result.returncode != 0
    assert 'two approved distributions' in result.stderr


def test_guard_refuses_replacement_even_with_correct_filenames(tmp_path):
    directory = tmp_path / 'dist'
    directory.mkdir()
    for name in validator().APPROVED_HASHES:
        (directory / name).write_bytes(b'replacement')
    result = run_guard(tmp_path, guard())
    assert result.returncode != 0
    assert 'SHA-256 mismatch' in result.stderr
