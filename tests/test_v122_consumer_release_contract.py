"""Consumer guidance must agree with the unpublished version's executable gate.

Historical release evidence is allowed, but cannot certify the current pin or
supply its expected source SHA. These are preparation contracts; release
closeout on main must update the gate, evidence and these assertions together.
"""
import ast
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / '.agents/skills/setting-up-papergraph'
GUIDANCE = [ROOT / 'README.md', *sorted(SETUP.rglob('*.md'))]


def plain(text):
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    return ' '.join(text.replace('`', '').replace('**', '').split())


def contradictory_claims(text, version):
    text = plain(text)
    released = re.search(
        rf'(?:PyPI\s+|GitHub\s+)?v?{re.escape(version)}(?:\s+Release)?\s+'
        r'(?:is|was|has been)\s+(?:published|released|verified)', text, re.I)
    verified = re.search(r'publication_verified(?:\s+flag)?\s*(?:is|=|:)\s*true', text, re.I)
    return bool(released or verified)


def test_preparation_runtime_gate_is_false_and_matches_package_version():
    tree = ast.parse((ROOT / 'scripts/check_onboarding.py').read_text(encoding='utf-8'))
    constants = {node.targets[0].id: ast.literal_eval(node.value)
                 for node in tree.body if isinstance(node, ast.Assign)
                 and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in {'PAPERGRAPH_VERSION', 'PYPI_PUBLICATION_VERIFIED'}}
    assert constants == {'PAPERGRAPH_VERSION': '1.2.2', 'PYPI_PUBLICATION_VERIFIED': False}
    metadata = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert f'version = "{constants["PAPERGRAPH_VERSION"]}"' in metadata


@pytest.mark.parametrize('path', GUIDANCE, ids=lambda path: path.name)
def test_all_active_guidance_keeps_current_publication_unverified(path):
    text = path.read_text(encoding='utf-8')
    assert not contradictory_claims(text, '1.2.2'), path
    assert 'publication_verified=false' in text, path
    # A consumer recipe must obtain source R from the reviewed artifact record,
    # never a copied prior-version SHA (nor an impossible self-referential SHA).
    if path.is_relative_to(SETUP):
        assert not re.search(r'(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])', text), path
    for paragraph in re.split(r'\n\s*\n', text):
        if 'actions/runs/38837645223' in paragraph:
            assert '1.2.1' in paragraph, 'historical evidence must name its own version'


def test_client_recipe_gates_every_native_recipe_before_any_mutation():
    text = (SETUP / 'references/client-configuration.md').read_text(encoding='utf-8')
    introduction = text.split('## Install', 1)[0]
    assert 'not published' in introduction
    assert 'publication_verified=false' in introduction
    assert '--verify-git-release --expected-source-commit SHA' in introduction
    assert 'v1.2.2-artifact-verification.md' in introduction
    assert 'do not run' in introduction
    assert '1.2.1' in introduction


def test_setup_and_readme_local_reference_closure_has_no_current_release_claim():
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
        # Historical verified flags belong to their historical versions. Only
        # the primary current guidance has the unconditional false-gate check.
        assert not re.search(
            r'(?:PyPI\s+|GitHub\s+)?v?1\.2\.2(?:\s+Release)?\s+'
            r'(?:is|was|has been)\s+(?:published|released|verified)', plain(text), re.I), path
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


@pytest.mark.parametrize('claim', [
    'PyPI 1.2.2 is published',
    'The [GitHub v1.2.2 Release](https://example.invalid) was published yesterday.',
    'The version-specific `publication_verified` flag is true.',
    '`publication_verified=true`',
])
def test_contradiction_guard_detects_rejected_current_version_claims(claim):
    assert contradictory_claims(claim, '1.2.2')


def test_historical_acceptance_and_explicit_nonpublication_are_distinct():
    assert not contradictory_claims('PyPI 1.2.1 is published. 1.2.2 is not published.', '1.2.2')


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
