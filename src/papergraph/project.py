import re
from dataclasses import dataclass
from pathlib import Path

from papergraph.loader import (
    SourceSpan,
    _is_commented,
    _load_latex_with_spans,
)


BIBLIOGRAPHY_RE = re.compile(
    r"\\(?P<command>bibliography|addbibresource)\s*"
    r"\{(?P<paths>[^}]*)\}"
)

TITLE_RE = re.compile(r"\\title\s*\{(?P<value>[^}]*)\}")
AUTHOR_RE = re.compile(r"\\author\s*\{(?P<value>[^}]*)\}")
AUTHOR_SEPARATOR_RE = re.compile(r"\\and")


@dataclass(frozen=True, slots=True)
class LoadedProject:
    root_file: Path
    project_root: Path
    text: str
    spans: tuple[SourceSpan, ...]
    bibliography_files: tuple[Path, ...]
    title: str | None
    authors: tuple[str, ...]


def load_project(main_file: str | Path) -> LoadedProject:
    traversal = _load_latex_with_spans(main_file)
    root_file = Path(main_file).expanduser().resolve()
    project_root = root_file.parent

    return LoadedProject(
        root_file=root_file,
        project_root=project_root,
        text=traversal.text,
        spans=traversal.spans,
        bibliography_files=_discover_bibliographies(
            traversal.text,
            traversal.spans,
            project_root,
        ),
        title=_first_command_value(
            TITLE_RE,
            traversal.text,
            traversal.spans,
        ),
        authors=_authors(traversal.text, traversal.spans),
    )


def _discover_bibliographies(
    text: str,
    spans: tuple[SourceSpan, ...],
    project_root: Path,
) -> tuple[Path, ...]:
    bibliography_files: list[Path] = []

    for span in spans:
        fragment = text[span.start:span.end]

        for match in BIBLIOGRAPHY_RE.finditer(fragment):
            if _is_commented(fragment, match.start()):
                continue

            paths = match.group("paths")
            for declared_path in paths.split(","):
                bibliography = _resolve_bibliography_path(
                    span.path,
                    declared_path.strip(),
                    project_root,
                )

                if bibliography not in bibliography_files:
                    bibliography_files.append(bibliography)

    return tuple(bibliography_files)


def _resolve_bibliography_path(
    declaring_file: Path,
    declared_path: str,
    project_root: Path,
) -> Path:
    if not declared_path:
        raise ValueError("Bibliography path is empty")

    path = Path(declared_path)
    if path.suffix == "":
        path = path.with_suffix(".bib")

    if not path.is_absolute():
        path = declaring_file.parent / path

    path = path.resolve()

    try:
        path.relative_to(project_root)
    except ValueError as error:
        raise ValueError(
            f"Bibliography path outside project root: {path}"
        ) from error

    if not path.exists():
        raise ValueError(f"Bibliography file does not exist: {path}")

    if not path.is_file():
        raise ValueError(f"Bibliography path is not a file: {path}")

    return path


def _first_command_value(
    pattern: re.Pattern[str],
    text: str,
    spans: tuple[SourceSpan, ...],
) -> str | None:
    for span in spans:
        fragment = text[span.start:span.end]

        for match in pattern.finditer(fragment):
            if _is_commented(fragment, match.start()):
                continue

            value = match.group("value").strip()
            return value or None

    return None


def _authors(
    text: str,
    spans: tuple[SourceSpan, ...],
) -> tuple[str, ...]:
    author = _first_command_value(AUTHOR_RE, text, spans)
    if author is None:
        return ()

    return tuple(
        person.strip()
        for person in AUTHOR_SEPARATOR_RE.split(author)
        if person.strip()
    )
