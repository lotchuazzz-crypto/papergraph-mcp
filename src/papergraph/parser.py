import re
from pathlib import Path

from papergraph.models import TheoremNode


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
    r"\\newtheorem\*?\{(?P<env>[^}]+)\}\{[^}]+\}"
)

LABEL_RE = re.compile(
    r"\\label\{(?P<label>[^}]+)\}"
)

REF_RE = re.compile(
    r"\\(?:ref|eqref|autoref|cref|Cref)\{(?P<labels>[^}]+)\}"
)


def extract_refs(text: str) -> tuple[str, ...]:
    refs: list[str] = []

    for match in REF_RE.finditer(text):
        labels = match.group("labels")

        for label in labels.split(","):
            label = label.strip()

            if label and label not in refs:
                refs.append(label)

    return tuple(refs)


def discover_theorem_environments(text: str) -> set[str]:
    environments = set(DEFAULT_ENVIRONMENTS)

    for match in NEW_THEOREM_RE.finditer(text):
        environments.add(match.group("env"))

    return environments


def parse_latex(text: str) -> list[TheoremNode]:
    environments = discover_theorem_environments(text)

    matches: list[
        tuple[int, str, str | None, str]
    ] = []

    for environment in environments:
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
                    match.group("title"),
                    match.group("body").strip(),
                )
            )

    matches.sort(key=lambda item: item[0])

    counters: dict[str, int] = {}
    nodes: list[TheoremNode] = []

    for position, environment, title, body in matches:
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
                title=title,
                label=label,
                content=body,
                refs=extract_refs(body),
                position=position,
            )
        )

    return nodes


def parse_file(path: str | Path) -> list[TheoremNode]:
    path = Path(path)

    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    return parse_latex(text)