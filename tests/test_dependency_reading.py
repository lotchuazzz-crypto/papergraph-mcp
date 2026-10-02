from pathlib import Path

import pytest

from papergraph.project import load_project
from papergraph.workspace import Workspace


def import_graph(tmp_path, graph):
    lines = [r'\documentclass{article}', r'\newtheorem{lemma}{Lemma}', r'\newtheorem{theorem}{Theorem}', r'\begin{document}']
    for node, targets in graph.items():
        kind = 'theorem' if node == 'A' else 'lemma'
        statement = 'Main theorem A result.' if node == 'A' else f'{node} result.'
        lines += [rf'\begin{{{kind}}}\label{{node:{node}}}', statement, rf'\end{{{kind}}}',
                  r'\begin{proof}', 'By ' + ', '.join(rf'\ref{{node:{target}}}' for target in targets) + '.' if targets else 'Direct.', r'\end{proof}']
    lines += [r'\end{document}']
    main = tmp_path / 'main.tex'
    main.write_text('\n'.join(lines), encoding='utf-8')
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    workspace.import_project('local:graph', 'local', str(main), None, load_project(main))
    return workspace


def names(nodes):
    return [node['result_id'].rsplit(':', 1)[-1] for node in nodes]


def test_shared_dependency_prerequisites_precede_every_user(tmp_path):
    workspace = import_graph(tmp_path, {'D': [], 'B': ['D'], 'C': ['D'], 'A': ['B', 'C']})
    try:
        path = workspace.get_result_reading_path('local:graph::node:A')
        assert names(path['top_down']) == ['A', 'B', 'D', 'C']
        order = names(path['bottom_up'])
        for user, dependency in [('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'D')]:
            assert order.index(dependency) < order.index(user), order
        assert len(order) == len(set(order))
    finally:
        workspace.close()


def test_direct_mode_includes_immediate_dependencies_only(tmp_path):
    workspace = import_graph(tmp_path, {'D': [], 'B': ['D'], 'C': ['D'], 'A': ['B', 'C']})
    try:
        path = workspace.get_result_reading_path('local:graph::node:A', recursive=False)
        assert names(path['top_down']) == ['A']
        assert names(path['direct_dependencies']) == ['B', 'C']
        assert names(path['bottom_up']) == ['B', 'C', 'A']
        assert path['order_status'] == 'direct_dependencies_first'
    finally:
        workspace.close()


@pytest.mark.parametrize('graph', [{'A': ['B'], 'B': ['A']}, {'A': ['A']}])
def test_cycles_do_not_claim_valid_prerequisite_order(tmp_path, graph):
    workspace = import_graph(tmp_path, graph)
    try:
        path = workspace.get_result_reading_path('local:graph::node:A')
        assert path['cycles']
        assert path['cycle_paths'][0][0] == path['cycle_paths'][0][-1]
        assert path['order_status'] == 'cycle_blocked'
        assert path['bottom_up'] == []
        assert path['warnings']
        assert path['top_down']
        assert workspace.export_reading_bundle('local:graph')['completeness_check']['circular_deps']
    finally:
        workspace.close()


def test_duplicate_mentions_retain_source_evidence_without_duplicate_nodes(tmp_path):
    workspace = import_graph(tmp_path, {'B': [], 'A': ['B', 'B']})
    try:
        path = workspace.get_result_reading_path('local:graph::node:A')
        assert names(path['bottom_up']) == ['B', 'A']
        assert len(path['edge_evidence']) == 1
        assert path['edge_evidence'][0]['via_mentions']
        assert path['coverage']['complete_mathematical_dependencies'] is False
    finally:
        workspace.close()


def test_overview_requires_selection_instead_of_promoting_heuristic(tmp_path):
    workspace = import_graph(tmp_path, {'B': [], 'A': ['B']})
    try:
        overview = workspace.get_dependency_reading('local:graph')
        assert overview['selection']['status'] == 'choose_target'
        assert overview['selection']['target_result_id'] is None
        assert overview['main_result_candidates']
        assert overview['reading_path'] is None
        selected = workspace.get_dependency_reading('local:graph', 'local:graph::node:A')
        assert selected['selection']['basis'] == 'user_selected'
        assert selected['statement_graph']['basis'] == 'statement_explicit_latex_refs_only'
        assert selected['statement_graph']['direct'] == []
        assert selected['proof_local']['direct']['known']['resolved_local_results']
        assert selected['external_import_plan']['candidates'] == []
    finally:
        workspace.close()


def test_overview_rejects_cross_paper_target(tmp_path):
    workspace = import_graph(tmp_path, {'A': []})
    try:
        with pytest.raises((ValueError, KeyError)):
            workspace.get_dependency_reading('local:graph', 'local:other::node:A')
    finally:
        workspace.close()


def test_unknown_proof_and_label_stay_visible(tmp_path):
    main = tmp_path / 'unknown.tex'
    main.write_text('\n'.join([r'\documentclass{article}', r'\newtheorem{theorem}{Theorem}',
        r'\begin{document}', r'\begin{theorem}\label{th:missing}No proof.\end{theorem}',
        r'\begin{theorem}\label{th:unknown}Unknown dependency.\end{theorem}',
        r'\begin{proof}By \ref{unknown:label}.\end{proof}', r'\end{document}']), encoding='utf-8')
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        workspace.import_project('local:unknown', 'local', str(main), None, load_project(main))
        missing = workspace.get_dependency_reading('local:unknown', 'local:unknown::th:missing')
        assert missing['proof_local']['direct']['unresolved']['proof'] == 'not_found'
        assert missing['reading_path']['unresolved_stops']
        unknown = workspace.get_dependency_reading('local:unknown', 'local:unknown::th:unknown')
        assert unknown['proof_local']['direct']['unresolved']['local_result_mentions']
        assert unknown['reading_path']['unresolved_stops']
        assert unknown['policy']['empty_dependencies_mean_independence'] is False
    finally:
        workspace.close()


def test_overview_cli_and_mcp_match_and_direct_queue_retains_dependencies(tmp_path, capsys):
    import json
    import papergraph.server as server
    workspace = import_graph(tmp_path, {'D': [], 'B': ['D'], 'A': ['B']})
    workspace.close()
    server._reset_server_state()
    try:
        server.open_workspace(str(tmp_path / 'workspace.sqlite3'))
        mcp = server.workspace_get_dependency_reading('local:graph', 'local:graph::node:A', recursive=False)
        server.main(['get-dependency-reading', str(tmp_path / 'workspace.sqlite3'),
                     'local:graph', '--target-result-id', 'local:graph::node:A', '--direct'])
        cli = json.loads(capsys.readouterr().out)
        assert cli == mcp
        assert names(cli['reading_path']['bottom_up']) == ['B', 'A']
        queue = server.require_workspace().create_reading_queue('local:graph::node:A', recursive=False)
        items = server.require_workspace().get_reading_queue(queue['queue_id'])['items']
        ids = [item['target_id'] for item in items if item['target_kind'] == 'result_id']
        assert 'local:graph::node:B' in ids
        assert 'local:graph::node:D' not in ids
    finally:
        server._reset_server_state()


def test_paper_map_and_reading_report_expose_cycle_status(tmp_path):
    workspace = import_graph(tmp_path, {'A': ['B'], 'B': ['A']})
    try:
        paper_map = workspace.get_paper_map('local:graph')
        candidate = paper_map['main_result_candidates'][0]
        assert candidate['reading_path']['order_status'] == 'cycle_blocked'
        assert candidate['reading_path']['bottom_up_result_ids'] == []
        report = workspace.export_paper_reading_report('local:graph')
        assert 'Cycle prevents prerequisite ordering' in report['markdown']
    finally:
        workspace.close()


def test_cycle_with_sortable_branch_propagates_to_all_reading_surfaces(tmp_path):
    workspace = import_graph(tmp_path, {'D': [], 'C': ['D'], 'B': ['A'], 'A': ['B', 'C']})
    try:
        target = 'local:graph::node:A'
        path = workspace.get_result_reading_path(target)
        assert set(names(path['top_down'])) == {'A', 'B', 'C', 'D'}
        assert path['bottom_up'] == []
        bundle = workspace.export_reading_bundle('local:graph')
        assert bundle['completeness_check']['circular_deps']
        assert bundle['completeness_check']['acyclic'] is False
        context = workspace.export_result_reading_context(target)
        assert any('cycle' in warning for warning in context['warnings'])
        report = workspace.export_paper_reading_report('local:graph')
        assert report['evidence_triage']['dependency_order']['order_status'] == 'cycle_blocked'
        queue = workspace.create_reading_queue(target)
        queued = workspace.get_reading_queue(queue['queue_id'])
        assert queued['reading_order']['order_status'] == 'cycle_blocked'
        assert queued['queue']['sequence_policy'] == 'exploration_queue_not_topological'
        session = workspace.create_reading_session('local:graph', target_result_id=target)
        workspace.apply_reading_queue_to_session(queue['queue_id'], session['session_id'])
        before = workspace.export_reading_session_summary(session['session_id'])['progress']
        workspace.import_project('local:graph', 'local', str(tmp_path / 'main.tex'), None, load_project(tmp_path / 'main.tex'))
        retained = workspace.get_reading_queue(queue['queue_id'])['items']
        assert [(item['item_id'], item['target_kind'], item['target_id'], item['position']) for item in retained] == [
            (item['item_id'], item['target_kind'], item['target_id'], item['position']) for item in queued['items']]
        assert all(item['evidence'].get('reimport_review_required') for item in retained)
        after = workspace.export_reading_session_summary(session['session_id'])['progress']
        assert after['total_checkpoints'] == before['total_checkpoints']
        assert after['blocked'] == before['total_checkpoints']
        assert workspace.get_reading_queue(queue['queue_id'])['reading_order']['order_status'] == 'cycle_blocked'
    finally:
        workspace.close()


def test_triage_uses_actual_proof_edges_not_exploration_sequence(tmp_path):
    workspace = import_graph(tmp_path, {'D': [], 'B': ['D'], 'C': ['D'], 'A': ['B', 'C']})
    try:
        report = workspace.export_paper_reading_report('local:graph')
        chains = report['evidence_triage']['supported_local_chains']
        pairs = {(edge['source_result_id'].rsplit(':', 1)[-1], edge['target_result_id'].rsplit(':', 1)[-1]) for edge in chains}
        assert pairs == {('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'D')}
        assert report['evidence_triage']['counts']['local_dependency_edge_count'] == 4
    finally:
        workspace.close()


def test_cross_paper_plan_propagates_local_cycles_without_claiming_topology(tmp_path):
    workspace = import_graph(tmp_path, {'B': ['A'], 'A': ['B']})
    other = tmp_path / 'other.tex'
    other.write_text('\n'.join([r'\documentclass{article}', r'\newtheorem{theorem}{Theorem}',
        r'\begin{document}', r'\begin{theorem}\label{other}Other result.\end{theorem}',
        r'\begin{proof}Direct.\end{proof}', r'\end{document}']), encoding='utf-8')
    try:
        workspace.import_project('local:other', 'local', str(other), None, load_project(other))
        plan = workspace.export_cross_paper_reading_plan(['local:graph', 'local:other'])
        assert plan['sequence_policy'] == 'heuristic_exploration_not_topological'
        assert any(warning['kind'] == 'dependency_cycle' for warning in plan['warnings'])
        assert plan['papers'][0]['dependency_order']['order_status'] == 'cycle_blocked'
        assert 'not a topological prerequisite order' in plan['markdown']
    finally:
        workspace.close()


def test_statement_reference_cycle_is_not_a_proof_cycle(tmp_path):
    main = tmp_path / 'statements.tex'
    main.write_text('\n'.join([r'\documentclass{article}', r'\newtheorem{theorem}{Theorem}',
        r'\begin{document}', r'\begin{theorem}\label{A}By \ref{B}.\end{theorem}',
        r'\begin{proof}Direct.\end{proof}', r'\begin{theorem}\label{B}By \ref{A}.\end{theorem}',
        r'\begin{proof}Direct.\end{proof}', r'\end{document}']), encoding='utf-8')
    workspace = Workspace.open(tmp_path / 'workspace.sqlite3')
    try:
        workspace.import_project('local:statements', 'local', str(main), None, load_project(main))
        overview = workspace.get_dependency_reading('local:statements', 'local:statements::A')
        assert {node['global_id'] for node in overview['statement_graph']['recursive']} == {'local:statements::A', 'local:statements::B'}
        assert overview['reading_path']['cycles'] == []
        assert overview['proof_local']['recursive']['known']['resolved_local_results'] == []
    finally:
        workspace.close()
