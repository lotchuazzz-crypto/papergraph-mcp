import re
from pathlib import Path

from papergraph.evidence import (
    EvidenceDocument,
    ResultEvidence,
    SourceSpanEvidence,
)
from papergraph.identity import global_theorem_id
from papergraph.models import TheoremNode
from papergraph.project import LoadedProject


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
    r"\\newtheorem\*?\{(?P<env>[^}]+)\}\{(?P<display>[^}]+)\}"
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


def extract_refs(text: str) -> tuple[str, ...]:
    refs: list[str] = []

    for match in REF_RE.finditer(text):
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

    for match in NEW_THEOREM_RE.finditer(text):
        raw_kind = match.group("env")
        display_kind = match.group("display").strip() or raw_kind
        environments[raw_kind] = (
            display_kind,
            _normalize_display_kind(raw_kind, display_kind),
        )

    return environments


def parse_latex(text: str) -> list[TheoremNode]:
    environments = discover_theorem_environments(text)

    matches: list[
        tuple[int, str, str, str, str | None, str]
    ] = []

    for environment, (display_kind, normalized_kind) in environments.items():
        pattern = re.compile(
            rf"""
            \\begin\{{{re.escape(environment)}\}}
            (?:\[(?P<title>[^\]]*)\])?
            (?P<body>.*?)
            \\end\{{{re.escape(environment)}\}}
            """,
            re.DOTALL | re.VERBOSE,
        )

        for match in pattern.finditer(text):
            matches.append(
                (
                    match.start(),
                    environment,
                    display_kind,
                    normalized_kind,
                    match.group("title"),
                    match.group("body").strip(),
                )
            )

    matches.sort(key=lambda item: item[0])

    counters: dict[str, int] = {}
    nodes: list[TheoremNode] = []

    for position, environment, display_kind, normalized_kind, title, body in matches:
        counters[environment] = counters.get(environment, 0) + 1

        label_match = LABEL_RE.search(body)

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
                title=title,
                label=label,
                content=body,
                refs=extract_refs(body),
                position=position,
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


def latex_project_to_evidence_document(
    paper_id: str,
    source_type: str,
    source_ref: str,
    source_version: str | None,
    project: LoadedProject,
) -> EvidenceDocument:
    nodes = parse_project(project)
    spans: list[SourceSpanEvidence] = []
    results: list[ResultEvidence] = []

    for span_index, node in enumerate(nodes):
        project_span = next(
            (
                item
                for item in project.spans
                if item.start <= node.position < item.end
            ),
            None,
        )
        if project_span is None:
            raise ValueError(f"No source span contains theorem {node.id!r}")

        spans.append(
            SourceSpanEvidence(
                paper_id=paper_id,
                source_type="tex",
                source_ref=project_span.path.relative_to(
                    project.project_root
                ).as_posix(),
                page=None,
                block_index=None,
                start_offset=node.position,
                end_offset=node.position + len(node.content),
                bbox=None,
                text=node.content,
                method="latex_environment",
                confidence=1.0,
            )
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
                visible_number=None,
                title=node.title,
                statement=node.content,
                span_indices=(span_index,),
                method="latex_environment",
                confidence=1.0,
            )
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
        proofs=(),
        bibliography_entries=(),
        local_result_mentions=(),
        citation_mentions=(),
        external_result_mentions=(),
        edges=(),
        warnings=(),
    )


def parse_file(path: str | Path) -> list[TheoremNode]:
    path = Path(path)

    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    return parse_latex(text)
