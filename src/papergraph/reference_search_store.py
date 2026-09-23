"""Atomic schema-9 migration and immutable resolver snapshot writes."""
from __future__ import annotations
import copy
import json

COLUMNS = {
    'reference_search_runs': {'resolver_version','search_schema_version','assessment_metadata_json'},
    'reference_search_candidates': {'candidate_schema_version','assessment_json'},
}
_ALTERS = [
    "ALTER TABLE reference_search_runs ADD COLUMN resolver_version TEXT NOT NULL DEFAULT 'legacy_v1'",
    "ALTER TABLE reference_search_runs ADD COLUMN search_schema_version INTEGER NOT NULL DEFAULT 1",
    'ALTER TABLE reference_search_runs ADD COLUMN assessment_metadata_json TEXT',
    'ALTER TABLE reference_search_candidates ADD COLUMN candidate_schema_version INTEGER NOT NULL DEFAULT 1',
    'ALTER TABLE reference_search_candidates ADD COLUMN assessment_json TEXT',
]


def migrate(connection):
    connection.execute('SAVEPOINT resolver_migration')
    try:
        for statement in _ALTERS:
            connection.execute(statement)
        connection.execute("UPDATE workspace_meta SET value='9' WHERE key='schema_version'")
    except Exception:
        connection.execute('ROLLBACK TO resolver_migration')
        raise
    finally:
        connection.execute('RELEASE resolver_migration')


def dumps(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def save_search(connection, *, run_id, paper_id, blocked_id, ranked, providers,
                max_candidates, resolver_version, timestamp):
    from papergraph.reference_search import candidate_id_for
    ranked = copy.deepcopy(ranked)
    suffix = ':' + run_id.rsplit(':', 1)[-1]
    mapping = {}
    for candidate in ranked['candidates']:
        original = candidate['candidate_id']
        mapping[original] = (candidate_id_for(paper_id, blocked_id, candidate['target'])
                             if resolver_version == 'legacy_v1' else original) + suffix
        candidate['candidate_id'] = mapping[original]
    def remap(value):
        if isinstance(value, dict):
            return {k: remap(v) for k,v in value.items()}
        if isinstance(value, list):
            return [remap(v) for v in value]
        if isinstance(value,str):
            return mapping.get(value, value)
        return value
    # Hidden candidates retain explicit evaluation IDs, not fake persisted IDs.
    metadata = {'provider_outcomes':ranked.get('provider_outcomes',[]), 'summary':remap(ranked['summary'])}
    connection.execute('SAVEPOINT reference_search_write')
    try:
        connection.execute('''INSERT INTO reference_search_runs
            (search_run_id,source_paper_id,blocked_id,query_json,provider_json,boundary_json,created_at,
             resolver_version,search_schema_version,assessment_metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (run_id,paper_id,blocked_id,dumps(ranked['query']),
             dumps({'providers':providers,'max_candidates':max_candidates,'provider_warnings':ranked['provider_warnings']}),
             dumps(remap(ranked['boundaries'])),timestamp,resolver_version,ranked['search_schema_version'],
             dumps(metadata) if resolver_version != 'legacy_v1' else None))
        for index,c in enumerate(ranked['candidates'],1):
            connection.execute('''INSERT INTO reference_search_candidates
                (candidate_id,search_run_id,source_paper_id,blocked_id,target_json,score,confidence,
                 evidence_json,provider_record_json,warning_json,rank,candidate_schema_version,assessment_json)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (c['candidate_id'],run_id,paper_id,blocked_id,dumps(c['target']),c['score'],c['confidence'],
                 dumps(c['evidence']),dumps(c['provider_records']),dumps(c['warnings']),index,
                 c['candidate_schema_version'],dumps(c['assessment']) if 'assessment' in c else None))
    except Exception:
        connection.execute('ROLLBACK TO reference_search_write')
        raise
    finally:
        connection.execute('RELEASE reference_search_write')
