import re
from dataclasses import dataclass
from pathlib import Path


INCLUDE_RE = re.compile(
    r"\\(?:input|include)\s*\{(?P<path>[^}]+)\}"
)


@dataclass(frozen=True, slots=True)
class SourceSpan:
    path: Path
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _TraversalResult:
    text: str
    spans: tuple[SourceSpan, ...]


class _Traversal:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.spans: list[SourceSpan] = []
        self.length = 0

    def append(self, path: Path, text: str) -> None:
        if not text:
            return

        start = self.length
        self.parts.append(text)
        self.length += len(text)
        self.spans.append(
            SourceSpan(path=path, start=start, end=self.length)
        )

    def result(self) -> _TraversalResult:
        return _TraversalResult(
            text="".join(self.parts),
            spans=tuple(self.spans),
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
    return _load_latex_with_spans(root).text


def _load_latex_with_spans(
    main_file: str | Path,
) -> _TraversalResult:
    root = Path(main_file).expanduser().resolve()
    traversal = _Traversal()
    _load_file(root, (), traversal)
    return traversal.result()


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
    traversal: _Traversal,
) -> None:
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

    cursor = 0
    child_stack = (*stack, path)

    for match in INCLUDE_RE.finditer(text):
        if _is_commented(text, match.start()):
            continue

        traversal.append(path, text[cursor:match.start()])
        included = resolve_tex_path(
            path,
            match.group("path").strip(),
        )
        _load_file(included, child_stack, traversal)
        cursor = match.end()

    traversal.append(path, text[cursor:])
