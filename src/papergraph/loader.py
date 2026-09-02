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


def _is_commented(
    text: str,
    position: int,
) -> bool:
    line_start = text.rfind("\n", 0, position) + 1

    for index in range(line_start, position):
        if text[index] != "%":
            continue

        backslashes = 0
        cursor = index - 1

        while (
            cursor >= line_start
            and text[cursor] == "\\"
        ):
            backslashes += 1
            cursor -= 1

        if backslashes % 2 == 0:
            return True

    return False


def _load_file(
    path: Path,
    stack: tuple[Path, ...],
) -> str:
    path = path.resolve()

    if path in stack:
        chain = " -> ".join(
            str(item)
            for item in (*stack, path)
        )
        raise ValueError(
            f"Circular LaTeX include: {chain}"
        )

    if not path.exists():
        raise FileNotFoundError(
            f"LaTeX file does not exist: {path}"
        )

    if not path.is_file():
        raise IsADirectoryError(
            f"LaTeX path is not a file: {path}"
        )

    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    parts: list[str] = []
    cursor = 0
    child_stack = (*stack, path)

    for match in INCLUDE_RE.finditer(text):
        if _is_commented(text, match.start()):
            continue

        parts.append(text[cursor:match.start()])
        included = resolve_tex_path(
            path,
            match.group("path").strip(),
        )
        parts.append(_load_file(included, child_stack))
        cursor = match.end()

    parts.append(text[cursor:])
    return "".join(parts)
