"""Display grouping without replacing persisted blocker IDs or evidence."""
from hashlib import sha256
import json


def aggregate_blockers(blocked):
    groups = {}
    for item in blocked:
        evidence = item.get('evidence', [])
        papers = sorted({e.get('paper_id') for e in evidence if e.get('paper_id')})
        keys = sorted({e.get('citation_key') for e in evidence if e.get('citation_key')})
        # Bibliography-only records use their exact ID; unidentified records are
        # deliberately separate. No fuzzy/title-based identity merging.
        entries = sorted({e['id'] for e in evidence if e['kind'] == 'bibliography_entry'})
        identity = [papers, keys or entries or [item['blocked_id']], item['reason']]
        key = json.dumps(identity, sort_keys=True)
        group = groups.setdefault(key, {'group_id': 'external-group:' + sha256(key.encode()).hexdigest(),
                    'reason': item['reason'], 'citation_keys': keys, 'blocked_ids': [], 'evidence': []})
        group['blocked_ids'].append(item['blocked_id'])
        seen = {(e['kind'], e['id'], e.get('source')) for e in group['evidence']}
        for e in evidence:
            identity = (e['kind'], e['id'], e.get('source'))
            if identity not in seen:
                group['evidence'].append(e)
                seen.add(identity)
    return list(groups.values())
