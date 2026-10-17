"""Semantic CLI/stdio acceptance for counter mutations and citation contexts.

Run with the isolated installed interpreter and a new --output outside Git.
Only synthetic text is generated. Each case launches the existing CLI/stdio
harness, then asserts source numbers/owners and actual MCP/external-plan data.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def payload(directory, name):
    result = json.loads((directory / (name + '.json')).read_text(encoding='utf-8'))
    assert not result.get('is_error', result.get('isError', False))
    return json.loads(next(c['text'] for c in result['content'] if c['type'] == 'text'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    repository = Path(__file__).resolve().parents[1]
    if root == repository or repository in root.parents:
        parser.error('--output must be outside the repository')
    root.mkdir(parents=True, exist_ok=False)
    fixtures = root / 'fixtures'
    fixtures.mkdir()
    cases = []
    for control in ('stepcounter', 'refstepcounter'):
        text = (r'\newtheorem{axi}{Theorem}\newtheorem{shared}[axi]{Lemma}'
                r'\begin{axi}\label{a}A.\end{axi}' + '\\' + control + r'{shared}'
                r'\begin{axi}\label{b}B.\end{axi}'
                r'\begin{proof}[Proof of Theorem 2]No certified owner.\end{proof}')
        cases.append((control, text, 'b', []))
    for name, declaration, definition, number in [
        ('format-plain', r'\newtheorem{a}{Theorem}', r'\renewcommand{\thea}{X}', '1'),
        ('format-starred', r'\newtheorem{a}{Theorem}', r'\renewcommand*{\thea}{X}', '1'),
        ('format-bare-starred', r'\newtheorem{a}{Theorem}', r'\renewcommand * \thea {X}', '1'),
        ('format-prefix-starred', r'\newtheorem{a}{Theorem}[section]\section{S}',
         r'\renewcommand * {\thesection}{X}', '1.1'),
        ('format-alias-starred', r'\newtheorem{root}{Theorem}\newtheorem{a}[root]{Theorem}',
         r'\renewcommand*{\thea}{X}', '1'),
    ]:
        text = (declaration + definition + r'\begin{a}\label{main}A.\end{a}'
                r'\begin{proof}[Proof of Theorem ' + number + r']No certified owner.\end{proof}')
        cases.append((name, text, 'main', []))
    for name, body, keys in [
        ('ensuremath', r'\ensuremath{[K]}', []),
        ('two-options', r'\makebox[2cm][c]{Text}', []),
        ('comment-options', '\\makebox[2cm]% comment\n[c]{Text}', []),
        ('math-real-cite', r'\ensuremath{[K] + \text{by \cite{Q}}}', ['Q']),
    ]:
        text = (r'\begin{theorem}\label{main}A.\end{theorem}\begin{proof}' + body +
                r'\end{proof}\begin{thebibliography}{9}\bibitem{K}Synthetic K.'
                r'\bibitem{Q}Synthetic Q.\bibitem{c}Alignment token.\end{thebibliography}')
        cases.append((name, text, 'main', keys))
    observations = []
    for name, text, target, keys in cases:
        source = fixtures / (name + '.tex')
        source.write_text(text, encoding='utf-8')
        output = root / name
        argv = [sys.executable, str(repository / 'scripts/accept_latex_structure.py'),
                '--output', str(output), '--tex', str(source), '--target', target]
        run = subprocess.run(argv, cwd=root, capture_output=True, timeout=240)
        (root / (name + '.stdout.txt')).write_bytes(run.stdout)
        (root / (name + '.stderr.txt')).write_bytes(run.stderr)
        assert run.returncode == 0, (name, run.stderr.decode('utf-8', errors='replace'))
        doc = json.loads((output / 'document.json').read_text(encoding='utf-8'))
        assert [m['raw_key'] for m in doc['citation_mentions']] == keys, name
        plan = payload(output, 'external-plan')
        assert plan['summary']['unique_external_targets'] == len(keys), name
        proof = payload(output, 'target-proof')
        if name in ('stepcounter', 'refstepcounter') or name.startswith('format-'):
            assert all(r['visible_number'] is None for r in doc['results']), name
            assert doc['proofs'][0]['result_id'] is None, name
            assert doc['proofs'][0]['association_basis'] == 'unresolved', name
            assert doc['proofs'][0]['association_confidence'] == 0.0, name
            assert proof['known'].get('proof') is None, name
            assert proof['unresolved']['proof'] == 'not_found', name
        else:
            assert len(doc['bibliography_entries']) == 3, name
            assert proof['known']['proof']['result_id'] == 'local:acceptance::main', name
            dependencies = payload(output, 'dependencies-False')
            assert [m['raw_key'] for m in dependencies['known']['citation_mentions']] == keys, name
        observations.append({'name': name, 'status': 'passed', 'argv': argv,
                             'citation_keys': keys, 'external_targets': len(keys)})
        (root / 'observations.json').write_text(json.dumps(observations, indent=2), encoding='utf-8')
    summary = {'status': 'passed', 'semantic_cases': len(observations),
               'cases': observations, 'private_inputs': False, 'external_downloads': 'not_run'}
    (root / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
