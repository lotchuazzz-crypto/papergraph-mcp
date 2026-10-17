import re
from dataclasses import dataclass
from pathlib import Path

from papergraph.evidence import (
    EvidenceDocument,
    ProofEvidence,
    ResultEvidence,
    SourceSpanEvidence,
)
from papergraph.evidence_extractors import (
    extract_citation_mentions,
    extract_external_result_mentions,
    extract_local_result_mentions,
)
from papergraph.identity import global_theorem_id
from papergraph.models import TheoremNode
from papergraph.project import LoadedProject
from papergraph.latex import environment_blocks, group_at, masked_text


DEFAULT_ENVIRONMENTS = {
    "theorem",
    "lemma",
    "proposition",
    "corollary",
    "definition",
    "claim",
    "conjecture",
}


NEW_THEOREM_RE = re.compile(
    r"(?<!\\)\\newtheorem(?P<star>\*)?\s*\{(?P<env>[^}]+)\}\s*"
    r"(?:\[(?P<shared>[^]]+)\]\s*)?\{(?P<display>[^}]+)\}\s*"
    r"(?:\[(?P<within>[^]]+)\])?"
)

LABEL_RE = re.compile(
    r"\\label\{(?P<label>[^}]+)\}"
)

REF_RE = re.compile(
    r"\\(?:ref|eqref|autoref|cref|Cref)\{(?P<labels>[^}]+)\}"
)
KIND_ALIASES = {
    "theorem": "theorem",
    "lemma": "lemma",
    "proposition": "proposition",
    "corollary": "corollary",
    "definition": "definition",
    "claim": "claim",
    "conjecture": "conjecture",
}


@dataclass(frozen=True, slots=True)
class LatexProofBlock:
    position: int
    body_start: int
    body_end: int
    body: str
    title: str | None = None
    end: int = 0


def extract_refs(text: str) -> tuple[str, ...]:
    refs: list[str] = []

    for match in REF_RE.finditer(masked_text(text)):
        labels = match.group("labels")

        for label in labels.split(","):
            label = label.strip()

            if label and label not in refs:
                refs.append(label)

    return tuple(refs)


def _normalize_display_kind(raw_kind: str, display_kind: str) -> str:
    normalized = display_kind.strip().lower()
    return KIND_ALIASES.get(normalized, raw_kind.lower())


def discover_theorem_environments(text: str) -> dict[str, tuple[str, str]]:
    environments = {
        environment: (environment, environment)
        for environment in DEFAULT_ENVIRONMENTS
    }

    for match in NEW_THEOREM_RE.finditer(masked_text(text)):
        raw_kind = match.group("env")
        display_kind = match.group("display").strip() or raw_kind
        environments[raw_kind] = (
            display_kind,
            _normalize_display_kind(raw_kind, display_kind),
        )

    return environments


_COUNTER_MUTATION_RE = re.compile(
    r'(?<!\\)\\(?:setcounter|addtocounter|stepcounter|refstepcounter|'
    r'counterwithin|counterwithout|numberwithin|usecounter)\b\*?')


def _counter_root(counter, declarations):
    seen = set()
    while declarations.get(counter, {}).get('shared'):
        if counter in seen:
            return None
        seen.add(counter)
        counter = declarations[counter]['shared'].strip()
    return counter


def _uninterpreted_counter_mutations(scan, declarations):
    """Return tainted counter roots and whether a target cannot be bounded.

    These commands are deliberately not executed. Aliases share uncertainty,
    and a dynamic/malformed counter argument cannot certify any numbering.
    """
    targets, unbounded = set(), False
    for command in _COUNTER_MUTATION_RE.finditer(scan):
        cursor = command.end()
        while option := group_at(scan, cursor, '[', ']'):
            cursor = option[1]
        argument = group_at(scan, cursor)
        if argument is None or re.fullmatch(r'[A-Za-z@][A-Za-z0-9_:@-]*', argument[0].strip()) is None:
            unbounded = True
            continue
        root = _counter_root(argument[0].strip(), declarations)
        if root is None:
            unbounded = True
        else:
            targets.add(root)
    return targets, unbounded


def _counter_display_redefinitions(scan):
    """Read direct definition targets, never evaluate replacement bodies.

    LaTeX's renewcommand accepts a star and either a braced or bare control
    word. Whitespace includes masked comments. The existing primitive def
    boundary also covers its direct global/expanded variants.
    """
    counters = set()
    commands = re.finditer(r'(?<!\\)\\(?P<name>renewcommand|def|gdef|edef|xdef)\b', scan)
    for command in commands:
        cursor = command.end()
        while cursor < len(scan) and scan[cursor].isspace():
            cursor += 1
        if command.group('name') == 'renewcommand' and scan[cursor:cursor + 1] == '*':
            cursor += 1
        while cursor < len(scan) and scan[cursor].isspace():
            cursor += 1
        group = group_at(scan, cursor)
        if group is not None:
            target = group[0].strip()
        else:
            token = re.match(r'\\[A-Za-z@]+', scan[cursor:])
            target = token.group() if token else ''
        display = re.fullmatch(r'\\the(?P<counter>[A-Za-z@]+)', target)
        if display is not None:
            counters.add(display.group('counter'))
    return counters


def parse_latex(text: str) -> list[TheoremNode]:
    environments = discover_theorem_environments(text)
    scan = masked_text(text)
    declarations = {m.group('env'): m.groupdict() for m in NEW_THEOREM_RE.finditer(scan)}
    mutated_counters, unbounded_mutation = _uninterpreted_counter_mutations(scan, declarations)
    redefined_displays = _counter_display_redefinitions(scan)

    matches: list[
        tuple[int, str, str, str, str | None, str, int, int]
    ] = []

    for environment, (display_kind, normalized_kind) in environments.items():
        for position, _, title, body, left, right in environment_blocks(text, environment):
            matches.append(
                (
                    position,
                    environment,
                    display_kind,
                    normalized_kind,
                    title, body, left, right,
                )
            )

    matches.sort(key=lambda item: item[0])

    counters: dict[str, int] = {}
    numbering: dict[tuple[str, tuple[int, ...]], int] = {}
    section_levels = ['chapter', 'section', 'subsection', 'subsubsection']
    section_values = [0] * len(section_levels)
    section_events = list(re.finditer(r'(?<!\\)\\(chapter|section|subsection|subsubsection)(?![A-Za-z*])', scan))
    section_cursor = 0
    nodes: list[TheoremNode] = []

    for position, environment, display_kind, normalized_kind, title, body, body_start, body_end in matches:
        counters[environment] = counters.get(environment, 0) + 1
        while section_cursor < len(section_events) and section_events[section_cursor].start() < position:
            level = section_levels.index(section_events[section_cursor].group(1))
            section_values[level] += 1
            section_values[level + 1:] = [0] * (len(section_values) - level - 1)
            section_cursor += 1
        root, seen = environment, set()
        while declarations.get(root, {}).get('shared') and root not in seen:
            seen.add(root)
            root = declarations[root]['shared'].strip()
        declaration = declarations.get(root, {})
        within = declaration.get('within')
        # Unknown/cyclic counters and custom numbering must not invent a number.
        unknown = root in seen or (root != environment and root not in declarations)
        dependent_counters = {root}
        if within in section_levels:
            dependent_counters.update(section_levels[:section_levels.index(within) + 1])
        controls = unbounded_mutation or bool(dependent_counters & mutated_counters)
        custom = bool((seen | {environment} | dependent_counters) & redefined_displays)
        if within:
            custom = custom or re.search(r'(?<!\\)\\appendix\b', scan)
        prefix = ()
        if within in section_levels:
            level = section_levels.index(within)
            first = 0 if section_values[0] else 1
            prefix = tuple(section_values[first:level + 1])
        elif within:
            unknown = True
        counter_key = (root, prefix)
        numbering[counter_key] = numbering.get(counter_key, 0) + 1
        visible_number = '.'.join(map(str, (*prefix, numbering[counter_key])))
        if declarations.get(environment, {}).get('star') or unknown or custom or controls:
            visible_number = None

        label_match = LABEL_RE.search(masked_text(body))

        label = (
            label_match.group("label")
            if label_match
            else None
        )

        node_id = (
            label
            if label
            else f"{environment}:{counters[environment]}"
        )

        nodes.append(
            TheoremNode(
                id=node_id,
                kind=environment,
                raw_kind=environment,
                display_kind=display_kind,
                normalized_kind=normalized_kind,
                visible_number=visible_number,
                title=title,
                label=label,
                content=body,
                refs=extract_refs(body),
                position=position,
                body_start=body_start,
                body_end=body_end,
            )
        )

    return nodes


def parse_project(project: LoadedProject) -> list[TheoremNode]:
    nodes = parse_latex(project.text)

    for node in nodes:
        span = next(
            (
                item
                for item in project.spans
                if item.start <= node.position < item.end
            ),
            None,
        )

        if span is not None:
            node.source_file = span.path.relative_to(
                project.project_root
            ).as_posix()

    return nodes


def parse_latex_proofs(text: str) -> list[LatexProofBlock]:
    proofs: list[LatexProofBlock] = []
    for position, end, title, body, left, right in environment_blocks(text, 'proof'):
        proofs.append(
            LatexProofBlock(
                position=position, body_start=left, body_end=right,
                body=body, title=title, end=end,
            )
        )
    return proofs


def _append_source_spans(spans, paper_id, project, start, end, method):
    """Map merged ranges to ordered original-file fragments; fail on gaps."""
    indices = []
    cursor = start
    for segment in project.spans:
        left, right = max(start, segment.start), min(end, segment.end)
        if left >= right and not (start == end and segment.start <= start < segment.end):
            continue
        if left != cursor or segment.source_start is None:
            raise ValueError("Cannot map TeX evidence to original source offsets")
        source_start = segment.source_start + left - segment.start
        source_end = source_start + right - left
        text = project.text[left:right]
        original = segment.path.read_text(encoding="utf-8", errors="replace")
        if original[source_start:source_end] != text:
            raise ValueError("TeX source changed while mapping evidence")
        indices.append(len(spans))
        spans.append(SourceSpanEvidence(
            paper_id=paper_id, source_type="tex",
            source_ref=segment.path.relative_to(project.project_root).as_posix(),
            page=None, block_index=None, start_offset=source_start,
            end_offset=source_end, bbox=None, text=text, method=method, confidence=1.0,
        ))
        cursor = right
        if cursor == end:
            break
    if cursor != end or not indices:
        raise ValueError("Cannot map TeX evidence to original source offsets")
    return tuple(indices)


def _explicit_proof_owner(title, results):
    """Only a complete, single explicit goal can override proximity."""
    if title is None:
        return None
    title = masked_text(title).strip().replace('~', ' ')
    prefix = re.fullmatch(r'Proof\s+of\s+(.+?)[.:]?\s*', title, re.I)
    if prefix is None:
        return None
    goal = prefix.group(1).strip()
    match = re.fullmatch(
        r'(?:(?P<kind>[A-Za-z]+)\s+)?(?:\\(?:ref|autoref|cref|Cref)\s*\{(?P<label>[^{},]+)\}|(?P<number>\d+(?:\.\d+)*))', goal)
    if match is None:
        return None
    compatible = [r for r in results if not match.group('kind') or match.group('kind').casefold() in
                  {r.kind.casefold(), r.normalized_kind.casefold(), r.display_kind.casefold()}]
    # An unknown compatible number can conceal a second target. Never turn
    # an apparently unique known number into ownership by ignoring that risk.
    if match.group('number') and any(r.visible_number is None for r in compatible):
        return None
    matches = [r for r in compatible
               if ((r.label == match.group('label')) if match.group('label')
                   else r.visible_number == match.group('number'))]
    return matches[0].result_id if len(matches) == 1 else None


def latex_project_to_evidence_document(
    paper_id: str,
    source_type: str,
    source_ref: str,
    source_version: str | None,
    project: LoadedProject,
) -> EvidenceDocument:
    nodes = parse_project(project)
    proof_blocks = parse_latex_proofs(project.text)
    spans: list[SourceSpanEvidence] = []
    results: list[ResultEvidence] = []

    for node in nodes:
        if node.body_start is None or node.body_end is None:
            raise ValueError(f"No source body bounds for theorem {node.id!r}")
        span_indices = _append_source_spans(
            spans, paper_id, project, node.body_start, node.body_end,
            "latex_environment",
        )
        results.append(
            ResultEvidence(
                result_id=global_theorem_id(paper_id, node.id),
                paper_id=paper_id,
                local_id=node.id,
                kind=node.kind,
                raw_kind=node.raw_kind,
                display_kind=node.display_kind,
                normalized_kind=node.normalized_kind,
                label=node.label,
                visible_number=node.visible_number,
                title=node.title,
                statement=node.content,
                span_indices=span_indices,
                method="latex_environment",
                confidence=1.0,
            )
        )

    explicit_owners = {p.position: _explicit_proof_owner(p.title, results) for p in proof_blocks}
    # Reserve explicit goals before applying the weaker unnamed adjacency rule.
    associated_result_ids = {owner for owner in explicit_owners.values() if owner}
    result_ends = {}
    ends_by_position = {position: end for kind in {n.kind for n in nodes}
                        for position, end, *_ in environment_blocks(project.text, kind)}
    for node, result in zip(nodes, results):
        result_ends[ends_by_position[node.position]] = result
    scan = masked_text(project.text)

    proofs: list[ProofEvidence] = []
    for proof in proof_blocks:
        span_indices = _append_source_spans(
            spans, paper_id, project, proof.body_start, proof.body_end,
            "latex_proof_environment",
        )

        result_id = explicit_owners[proof.position]
        association_basis = "unresolved"
        association_confidence = 0.0
        if result_id is not None:
            association_basis = 'proof_heading_names_result'
            association_confidence = 0.95
        elif proof.title is None:
            candidates = [r for end, r in result_ends.items()
                          if end <= proof.position and not scan[end:proof.position].strip()]
            if len(candidates) == 1 and candidates[0].result_id not in associated_result_ids:
                result_id = candidates[0].result_id
                associated_result_ids.add(result_id)
                association_basis = 'immediately_follows_result'
                association_confidence = 0.8

        proofs.append(
            ProofEvidence(
                proof_id=f"{paper_id}::proof:{len(proofs) + 1}",
                paper_id=paper_id,
                result_id=result_id,
                text=proof.body,
                span_indices=span_indices,
                association_basis=association_basis,
                association_confidence=association_confidence,
                method="latex_proof_environment",
                confidence=1.0,
            )
        )

    local_result_mentions = extract_local_result_mentions(
        paper_id,
        tuple(proofs),
        tuple(results),
    )
    from papergraph.citations import build_bibliography_evidence
    bibliography_entries, bibliography_spans = build_bibliography_evidence(paper_id, project)
    spans.extend(bibliography_spans)
    citation_mentions = extract_citation_mentions(
        paper_id,
        tuple(proofs),
        bibliography_entries,
    )
    external_result_mentions = extract_external_result_mentions(
        paper_id,
        citation_mentions,
    )

    return EvidenceDocument(
        paper_id=paper_id,
        source_type=source_type,
        source_ref=source_ref,
        source_version=source_version,
        title=project.title,
        authors=project.authors,
        main_file=project.root_file.relative_to(project.project_root).as_posix(),
        spans=tuple(spans),
        results=tuple(results),
        proofs=tuple(proofs),
        bibliography_entries=bibliography_entries,
        local_result_mentions=local_result_mentions,
        citation_mentions=citation_mentions,
        external_result_mentions=external_result_mentions,
        edges=(),
        warnings=tuple(
            ['LaTeX extraction is lexical; custom macros and numbering are not interpreted.']
            + (['Counter mutations are not executed; affected visible numbers remain unknown and cannot establish numeric proof ownership.']
               if _COUNTER_MUTATION_RE.search(masked_text(project.text)) else [])
            + (['Custom counter-display definitions are not interpreted; affected visible numbers remain unknown.']
               if _counter_display_redefinitions(masked_text(project.text)) else [])
            + ([f'{sum(p.result_id is None for p in proofs)} proof environments have unresolved ownership.']
               if any(p.result_id is None for p in proofs) else [])
        ),
    )


def parse_file(path: str | Path) -> list[TheoremNode]:
    path = Path(path)

    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    return parse_latex(text)
