"""Source-backed dependency reading, without semantic inference or imports."""
from __future__ import annotations

from papergraph.evidence import EVIDENCE_EMPTY_DEPENDENCY_WARNING
from papergraph.models import DEPENDENCY_EXTRACTION_BASIS
from papergraph.paper_map import _list_all_results
from papergraph.reading import base_bridge_payload


def find_dependency_cycles(dependency_index):
    """Find cycle witnesses in the exported source-backed dependency index."""
    adjacency = {source: [node['result_id'] for node in payload['known']['resolved_local_results']]
                 for source, payload in dependency_index.items()}
    visited, active, trail, cycles = set(), set(), [], []
    for root in sorted(adjacency):
        if root in visited:
            continue
        visited.add(root)
        active.add(root)
        trail.append(root)
        stack = [(root, iter(adjacency.get(root, [])))]
        while stack:
            node, targets = stack[-1]
            target = next(targets, None)
            if target is None:
                stack.pop()
                active.remove(node)
                trail.pop()
            elif target in active:
                cycle = trail[trail.index(target):]
                # Canonical rotation deduplicates witnesses from different roots.
                start = cycle.index(min(cycle))
                cycle = cycle[start:] + cycle[:start]
                cycle.append(cycle[0])
                if cycle not in cycles:
                    cycles.append(cycle)
            elif target not in visited:
                visited.add(target)
                active.add(target)
                trail.append(target)
                stack.append((target, iter(adjacency.get(target, []))))
    return sorted(cycles)


def build_result_reading_path(workspace, result_id, recursive, parser_version):
    if not isinstance(recursive, bool):
        raise ValueError('recursive must be a boolean')
    workspace._ensure_result_exists(result_id)
    top_down, bottom_up, edges, edge_evidence = [], [], [], []
    external_stops, unresolved_stops, cycles, cycle_paths = [], [], [], []
    visited, active = set(), set()
    trail = []
    proof_warnings = []
    proof_entries = {}

    def enter(current_id):
        visited.add(current_id)
        active.add(current_id)
        trail.append(current_id)
        top_down.append(workspace.get_result(current_id))
        dependencies = workspace.get_proof_dependencies(current_id)
        proof_entries[current_id] = dependencies.get('proof_entry', {})
        external_stops.extend(dependencies['known'].get('external_result_mentions', []))
        for kind, mentions in dependencies.get('unresolved', {}).items():
            if mentions:
                unresolved_stops.append({'result_id': current_id, 'kind': kind, 'mentions': mentions})
        for warning in dependencies.get('warnings', []):
            if warning == EVIDENCE_EMPTY_DEPENDENCY_WARNING:
                continue
            if warning not in proof_warnings:
                proof_warnings.append(f'{current_id}: {warning}')
        return iter(dependencies['known']['resolved_local_results'])

    # Iterative postorder avoids reversing preorder (wrong for shared dependencies)
    # and avoids Python recursion limits for long source-backed local chains.
    stack = [(result_id, enter(result_id))]
    while stack:
        current_id, targets = stack[-1]
        dependency = next(targets, None)
        if dependency is None:
            bottom_up.append(workspace.get_result(current_id))
            active.remove(current_id)
            trail.pop()
            stack.pop()
            continue
        target_id = dependency['result_id']
        edge = {'source_result_id': current_id, 'target_result_id': target_id,
                'relation': 'uses_local_result'}
        entry = proof_entries[current_id]
        if entry.get('status') == 'corresponding_proof':
            edge.update(relation='corresponding_proof_uses_local_result',
                        proof_result_id=entry['proof_result_id'],
                        author_correspondences=entry['correspondences'])
        edges.append(edge)
        edge_evidence.append({**edge, 'via_mentions': dependency.get('via_mentions', [])})
        if target_id in active:
            if target_id not in cycles:
                cycles.append(target_id)
            cycle = trail[trail.index(target_id):] + [target_id]
            if cycle not in cycle_paths:
                cycle_paths.append(cycle)
        elif target_id not in visited:
            if recursive:
                stack.append((target_id, enter(target_id)))
            else:
                visited.add(target_id)
                node = workspace.get_result(target_id)
                top_down.append(node)
                bottom_up.append(node)

    entry_stops = [{'result_id': node, **entry} for node, entry in proof_entries.items()
                   if entry.get('status') not in (None, 'direct', 'not_found', 'corresponding_proof')]
    order_status = ('cycle_blocked' if cycles else 'correspondence_blocked' if entry_stops
                    else 'dependency_first' if recursive else 'direct_dependencies_first')
    warnings = proof_warnings + ['Reading order covers extracted local proof evidence only; unknown and external prerequisites remain outside this order.']
    if not edges and not external_stops:
        warnings.append(EVIDENCE_EMPTY_DEPENDENCY_WARNING)
    if cycles:
        warnings.append('Local evidence contains a cycle; no dependency-first order is available. Use top_down for exploration.')
    return {
        **base_bridge_payload(parser_version), 'result_id': result_id,
        'recursive': recursive,
        'top_down': top_down if recursive else top_down[:1],
        'direct_dependencies': [node for node in top_down if node['result_id'] != result_id] if not recursive else [],
        'bottom_up': [] if cycles or entry_stops else bottom_up, 'edges': edges,
        'edge_evidence': edge_evidence, 'external_stops': external_stops,
        'unresolved_stops': unresolved_stops, 'cycles': cycles,
        'cycle_paths': cycle_paths, 'order_status': order_status,
        'coverage': {'basis': 'source_backed_explicit_proof_local_evidence',
                     'complete_mathematical_dependencies': False,
                     'scope': 'reachable_local_proofs' if recursive else 'selected_proof_only',
                     'external_references_traversed': False},
        'warnings': list(dict.fromkeys(warnings)),
        'proof_entries': proof_entries,
        'proof_entry_stops': entry_stops,
    }


def build_dependency_reading(workspace, paper_id, target_result_id=None, recursive=True, max_candidates=5):
    """Present candidates or a user-selected target with separated evidence."""
    if not isinstance(recursive, bool):
        raise ValueError('recursive must be a boolean')
    paper = workspace.get_paper(paper_id)
    paper_id = paper['paper_id']
    if target_result_id is not None:
        target = workspace.get_result(target_result_id)
        if target['paper_id'] != paper_id:
            raise ValueError('target_result_id must belong to the selected paper')
    overview = workspace.get_paper_map(paper_id, max_candidates=max_candidates)
    result = {
        'dependency_reading_schema_version': 1,
        'paper': paper,
        'results': _list_all_results(workspace, paper_id),
        'main_result_candidates': overview['main_result_candidates'],
        'selection': {'status': 'selected' if target_result_id else 'choose_target',
                      'basis': 'user_selected' if target_result_id else 'unselected',
                      'target_result_id': target_result_id,
                      'candidate_policy': 'source_signals_are_heuristic_not_definitive_main_theorem'},
        'statement_graph': None, 'proof_local': None, 'reading_path': None,
        'external_import_plan': None,
        'policy': {'proof_verification': False, 'implicit_dependency_inference': False,
                   'external_references': 'review_plan_only_no_download',
                   'empty_dependencies_mean_independence': False},
        'warnings': [EVIDENCE_EMPTY_DEPENDENCY_WARNING,
                     'Main-result candidates are heuristic; choose a result before requesting its reading path.'],
    }
    if target_result_id is None:
        return result
    # Legacy statement graph is available for LaTeX theorem records only; absence
    # of that representation (e.g. PDF evidence) is not an empty mathematical graph.
    statement_available = workspace._connection.execute(
        'SELECT 1 FROM theorems WHERE global_id = ?', (target_result_id,)).fetchone() is not None
    result['statement_graph'] = {
        'basis': DEPENDENCY_EXTRACTION_BASIS,
        'semantics': 'statement_reference_reachability_not_proof_or_reading_order',
        'status': 'available' if statement_available else 'not_available_for_result',
        'direct': workspace.get_dependencies(target_result_id) if statement_available else None,
        'recursive': workspace.get_dependencies(target_result_id, recursive=True) if statement_available and recursive else None,
    }
    result['proof_local'] = {
        'basis': 'source_backed_explicit_proof_local_evidence',
        'direct': workspace.get_proof_dependencies(target_result_id),
        'recursive': workspace.get_proof_dependencies(target_result_id, recursive=True) if recursive else None,
    }
    result['reading_path'] = workspace.get_result_reading_path(target_result_id, recursive=recursive)
    result['external_import_plan'] = workspace.plan_external_imports_for_result(target_result_id, recursive=recursive)
    result['warnings'] = result['reading_path']['warnings']
    return result
