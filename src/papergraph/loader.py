import re
from pathlib import Path


INCLUDE_RE = re.compile(
    r"\\(?:input|include)\s*\{(?P<path>[^}]+)\}"
)


def resolve_tex_path(
    parent_file: Path,
    included_path: str,
) -> Path:
    path = Path(included_path)

    if path.suffix == "":
        path = path.with_suffix(".tex")

    if not path.is_absolute():
        path = parent_file.parent / path

    return path.resolve()


def load_latex_project(
    main_file: str | Path,
) -> str:
    root = Path(main_file).expanduser().resolve()
    return _load_file(root, ())


def _load_file(
    path: Path,
    stack: tuple[Path, ...],
) -> str:
    path = path.resolve()
    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    parts: list[str] = []
    cursor = 0

    for match in INCLUDE_RE.finditer(text):
        parts.append(text[cursor:match.start()])
        included = resolve_tex_path(
            path,
            match.group("path").strip(),
        )
        parts.append(_load_file(included, (*stack, path)))
        cursor = match.end()

    parts.append(text[cursor:])
    return "".join(parts)
