"""Current main records verified PyPI separately from immutable release files."""
import ast
import importlib.util
import json
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / '.agents/skills/setting-up-papergraph'
GUIDANCE = [ROOT / 'README.md', *sorted(SETUP.rglob('*.md'))]
EVIDENCE = json.loads((ROOT / 'docs/reference/v1.2.2-publication.json').read_text(encoding='utf-8'))


def plain(text):
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    return ' '.join(text.replace('`', '').replace('**', '').split())


def contradictory_claims(text):
    text = plain(text)
    # Channel-specific: the public tag does not establish a GitHub Release.
    unavailable_pypi = re.search(r'PyPI\s+v?1\.2\.2\s+is\s+not\s+published', text, re.I)
    released = re.search(r'GitHub\s+v?1\.2\.2\s+Release\s+'
                         r'(?:is|was|has been)\s+(?:published|released|verified)', text, re.I)
    return bool(unavailable_pypi or (released and not EVIDENCE['github_release']['published']))


def test_runtime_gate_matches_actual_public_acceptance_and_package_version():
    tree = ast.parse((ROOT / 'scripts/check_onboarding.py').read_text(encoding='utf-8'))
    constants = {node.targets[0].id: ast.literal_eval(node.value)
                 for node in tree.body if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in {'PAPERGRAPH_VERSION', 'PYPI_PUBLICATION_VERIFIED'}}
    assert constants == {'PAPERGRAPH_VERSION': '1.2.2', 'PYPI_PUBLICATION_VERIFIED': True}
    metadata = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert f'version = "{constants["PAPERGRAPH_VERSION"]}"' in metadata
    assert EVIDENCE['pypi']['published'] and EVIDENCE['pypi']['public_bytes_verified']
    acceptance = EVIDENCE['public_index_acceptance']
    assert acceptance['conclusion'] == 'success'
    assert acceptance['install_source'] == 'public_index'
    assert not acceptance['installed_local_artifact']
    assert acceptance['fresh_cache']
    assert acceptance['git_executable'] == 'absent'
    assert acceptance['git_package'] == 'not_installed'
    assert not EVIDENCE['immutable_release_files_rewritten']


def test_public_evidence_matches_unchanged_approved_release_bytes():
    spec = importlib.util.spec_from_file_location('release_verifier', ROOT / 'scripts/check_release_artifacts.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert EVIDENCE['pypi']['files'] == module.APPROVED_HASHES
    assert EVIDENCE['source_commit'] == module.SOURCE_SHA
    assert EVIDENCE['source_tree_sha256'] == module.SOURCE_DIGEST
    assert EVIDENCE['git_tag']['target'] == EVIDENCE['source_commit']
    assert EVIDENCE['git_tag']['live_verification_still_required_for_setup']


@pytest.mark.parametrize('path', GUIDANCE, ids=lambda path: path.name)
def test_all_active_guidance_records_current_pypi_acceptance(path):
    text = path.read_text(encoding='utf-8')
    assert not contradictory_claims(text), path
    assert 'PyPI publication_verified=true' in text, path
    assert 'v1.2.2-publication.md' in text, path
    # A consumer recipe must obtain source R from the reviewed artifact record,
    # never a copied prior-version SHA (nor an impossible self-referential SHA).
    if path.is_relative_to(SETUP):
        assert not re.search(r'(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])', text), path
    for paragraph in re.split(r'\n\s*\n', text):
        if 'actions/runs/38837645223' in paragraph:
            assert '1.2.1' in paragraph, 'historical evidence must name its own version'


def test_client_recipe_distinguishes_verified_pypi_and_explicit_live_git_check():
    text = (SETUP / 'references/client-configuration.md').read_text(encoding='utf-8')
    introduction = text.split('## Install', 1)[0]
    assert 'PyPI 1.2.2 is published' in introduction
    assert 'PyPI publication_verified=true' in introduction
    assert '--verify-git-release --expected-source-commit SHA' in introduction
    assert 'v1.2.2-artifact-verification.md' in introduction
    assert 'do not run' in introduction
    assert '1.2.1' in introduction
    assert 'GitHub Release creation remains pending' in introduction
    assert 'requires approval at the point of mutation' in introduction


def test_setup_and_readme_local_reference_closure_remains_complete():
    # Follow the actual local Markdown references rather than a hand-maintained
    # list which can omit the complete client recipe or its release record.
    pending, seen = list(GUIDANCE), set()
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        seen.add(path)
        assert path.is_relative_to(ROOT)
        text = path.read_text(encoding='utf-8')
        # Linked historical snapshots retain their original preparation state.
        if path in GUIDANCE or path.name == 'v1.2.2-publication.md':
            assert not contradictory_claims(text), path
        # Example exports retain links relative to their eventual artifact
        # directory (e.g. START_HERE.md), not navigation in this checkout.
        # Their prose above is checked; do not rewrite the output contract.
        if path.parent == ROOT / 'docs/examples':
            continue
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            target = target.split('#', 1)[0]
            if not target or '://' in target or target.startswith(('mailto:', 'data:')):
                continue
            referenced = (path.parent / target).resolve()
            assert referenced.is_file(), (path, target)
            if referenced.suffix == '.md':
                pending.append(referenced)
    assert (SETUP / 'references/client-configuration.md').resolve() in seen
    assert (ROOT / 'docs/reference/v1.2.2-artifact-verification.md').resolve() in seen
    assert (ROOT / 'docs/reference/v1.2.2-publication.md').resolve() in seen


@pytest.mark.parametrize('claim', [
    'PyPI 1.2.2 is not published',
    'The [GitHub v1.2.2 Release](https://example.invalid) was published yesterday.',
])
def test_contradiction_guard_detects_rejected_current_version_claims(claim):
    assert contradictory_claims(claim)


def test_current_pypi_historical_acceptance_and_pending_github_are_distinct():
    assert not contradictory_claims('PyPI 1.2.1 is published. PyPI 1.2.2 is published.')
    assert not contradictory_claims('GitHub v1.2.2 Release is not published. The public tag exists.')


def test_current_guidance_discloses_fail_closed_pdf_policy():
    for path in GUIDANCE:
        text = path.read_text(encoding='utf-8')
        assert 'automatic_ownership_policy' in text, path
        if path.name == 'usage-prompt.md':
            assert '首个原始文本行' in text and '后续行或块不自动关联' in text
        else:
            normalized = plain(text)
            assert 'first physical line' in normalized, path
            assert 'not automatically join' in normalized, path
