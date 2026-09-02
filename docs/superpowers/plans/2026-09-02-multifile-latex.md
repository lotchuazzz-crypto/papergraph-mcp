# Multi-file LaTeX Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PaperGraph MCP recursively expand `\input` and `\include` from a root `.tex` file before parsing theorem dependencies.

**Architecture:** Preserve the v0.1 parser, graph, and MCP interfaces. Add a focused loader for filesystem traversal and combined LaTeX text; the server composes it with `parse_latex`.

**Tech Stack:** Python 3.10+, pathlib, re, MCP Python SDK 2.x, pytest 8+, uv, Git

## Global Constraints

- Preserve the three v0.1 commits from `feature/v0.1-local-latex`.
- Do not merge v0.2 into `main` and do not push.
- Resolve includes relative to the containing file and add `.tex` only when no suffix exists.
- Preserve source order, ignore commented include commands, and allow repeated non-cyclic includes.
- Fail clearly on missing files and circular includes.
- Keep `parse_file` as the single-file API and set the package version to `0.2.0`.

---

### Task 1: Restore v0.1 on the v0.2 branch

**Files:**
- Preserve: `docs/superpowers/specs/2026-09-02-multifile-latex-design.md`
- Restore from Git: `pyproject.toml`, `src/papergraph/*.py`, `tests/**`, `uv.lock`

**Interfaces:**
- Consumes: `feature/v0.1-local-latex` at `55bf024`
- Produces: current v0.2 branch containing the design commit and all v0.1 commits

- [ ] **Step 1: Verify the current branch and tracked state**

Run:

```powershell
git branch --show-current
git status --short
```

Expected: `feature/v0.2-multifile` and no tracked source changes.

- [ ] **Step 2: Merge the v0.1 history**

Run:

```powershell
git merge --no-edit feature/v0.1-local-latex
```

Expected: a clean merge restoring v0.1 while retaining design commit `e707db6`.

- [ ] **Step 3: Verify the v0.1 baseline**

Run:

```powershell
uv run pytest -q -p no:cacheprovider
```

Expected: `5 passed`. Stop and diagnose if the baseline fails.

- [ ] **Step 4: Confirm history**

Run `git log --graph --oneline --decorate -8`.

Expected: the parser, graph, MCP, and v0.2 design commits are ancestors of HEAD.

---

### Task 2: Resolve and recursively expand LaTeX includes

**Files:**
- Create: `src/papergraph/loader.py`
- Create: `tests/test_loader.py`

**Interfaces:**
- Produces: `resolve_tex_path(parent_file: Path, included_path: str) -> Path`
- Produces: `load_latex_project(main_file: str | Path) -> str`

- [ ] **Step 1: Write failing path and recursion tests**

Create `tests/test_loader.py`:

```python
from pathlib import Path

from papergraph.loader import load_latex_project, resolve_tex_path


def test_resolve_tex_path_relative_to_containing_file(tmp_path: Path):
    parent = tmp_path / "paper" / "main.tex"

    resolved = resolve_tex_path(parent, "sections/results")

    assert resolved == (
        tmp_path / "paper" / "sections" / "results.tex"
    ).resolve()


def test_load_latex_project_expands_nested_commands_in_order(
    tmp_path: Path,
):
    nested = tmp_path / "sections" / "nested"
    nested.mkdir(parents=True)
    main = tmp_path / "main.tex"
    first = tmp_path / "sections" / "first.tex"
    second = nested / "second.tex"
    main.write_text(
        "START\n\\input{sections/first}\nEND",
        encoding="utf-8",
    )
    first.write_text(
        "FIRST\n\\include{nested/second.tex}\n",
        encoding="utf-8",
    )
    second.write_text("SECOND", encoding="utf-8")

    text = load_latex_project(main)

    assert text.index("START") < text.index("FIRST")
    assert text.index("FIRST") < text.index("SECOND")
    assert text.index("SECOND") < text.index("END")
    assert "\\input{" not in text
    assert "\\include{" not in text
```

- [ ] **Step 2: Run and verify RED**

Run `uv run pytest tests/test_loader.py -q -p no:cacheprovider`.

Expected: collection error `ModuleNotFoundError: No module named 'papergraph.loader'`.

- [ ] **Step 3: Implement the minimal loader**

Create `src/papergraph/loader.py`:

```python
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


def load_latex_project(main_file: str | Path) -> str:
    root = Path(main_file).expanduser().resolve()
    return _load_file(root, ())


def _load_file(path: Path, stack: tuple[Path, ...]) -> str:
    path = path.resolve()
    text = path.read_text(encoding="utf-8", errors="replace")
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
```

- [ ] **Step 4: Verify GREEN and regressions**

Run:

```powershell
uv run pytest tests/test_loader.py -q -p no:cacheprovider
uv run pytest -q -p no:cacheprovider
```

Expected: both new tests and all v0.1 tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/papergraph/loader.py tests/test_loader.py
git commit -m "Add recursive LaTeX project loader"
```

---

### Task 3: Harden comments and error behavior

**Files:**
- Modify: `src/papergraph/loader.py`
- Modify: `tests/test_loader.py`

**Interfaces:**
- Consumes: Task 2 loader API
- Produces: deterministic loader errors and comment filtering without changing public signatures

- [ ] **Step 1: Add failing edge-case tests**

Append:

```python
import pytest


def test_commented_include_is_not_expanded(tmp_path: Path):
    main = tmp_path / "main.tex"
    main.write_text(
        "% \\input{missing}\nVISIBLE",
        encoding="utf-8",
    )
    text = load_latex_project(main)
    assert "VISIBLE" in text
    assert "\\input{missing}" in text


def test_escaped_percent_does_not_comment_out_include(tmp_path: Path):
    main = tmp_path / "main.tex"
    included = tmp_path / "included.tex"
    main.write_text(
        "\\% literal \\input{included}",
        encoding="utf-8",
    )
    included.write_text("EXPANDED", encoding="utf-8")
    assert "EXPANDED" in load_latex_project(main)


def test_repeated_include_is_expanded_twice(tmp_path: Path):
    main = tmp_path / "main.tex"
    shared = tmp_path / "shared.tex"
    main.write_text(
        "\\input{shared}\n\\input{shared}",
        encoding="utf-8",
    )
    shared.write_text("SHARED", encoding="utf-8")
    assert load_latex_project(main).count("SHARED") == 2


def test_missing_include_reports_resolved_path(tmp_path: Path):
    main = tmp_path / "main.tex"
    main.write_text("\\input{missing}", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="missing[.]tex"):
        load_latex_project(main)


def test_circular_include_reports_chain(tmp_path: Path):
    first = tmp_path / "first.tex"
    second = tmp_path / "second.tex"
    first.write_text("\\input{second}", encoding="utf-8")
    second.write_text("\\include{first}", encoding="utf-8")
    with pytest.raises(ValueError, match="Circular LaTeX include"):
        load_latex_project(first)
```

- [ ] **Step 2: Run and verify RED**

Run `uv run pytest tests/test_loader.py -q -p no:cacheprovider`.

Expected: comment and cycle tests fail for missing behavior; the repeated include guard passes.

- [ ] **Step 3: Implement comment and cycle handling**

Add:

```python
def _is_commented(text: str, position: int) -> bool:
    line_start = text.rfind("\n", 0, position) + 1
    for index in range(line_start, position):
        if text[index] != "%":
            continue
        backslashes = 0
        cursor = index - 1
        while cursor >= line_start and text[cursor] == "\\":
            backslashes += 1
            cursor -= 1
        if backslashes % 2 == 0:
            return True
    return False
```

Replace `_load_file` with:

```python
def _load_file(path: Path, stack: tuple[Path, ...]) -> str:
    path = path.resolve()
    if path in stack:
        chain = " -> ".join(str(item) for item in (*stack, path))
        raise ValueError(f"Circular LaTeX include: {chain}")
    if not path.exists():
        raise FileNotFoundError(
            f"LaTeX file does not exist: {path}"
        )
    if not path.is_file():
        raise IsADirectoryError(
            f"LaTeX path is not a file: {path}"
        )

    text = path.read_text(encoding="utf-8", errors="replace")
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
```

- [ ] **Step 4: Verify GREEN and commit**

Run:

```powershell
uv run pytest -q -p no:cacheprovider
git add src/papergraph/loader.py tests/test_loader.py
git commit -m "Handle LaTeX include errors and comments"
```

Expected: every loader and v0.1 test passes before commit.

---

### Task 4: Integrate loader, parser, graph, and MCP

**Files:**
- Create: `tests/fixtures/multifile/main.tex`
- Create: `tests/fixtures/multifile/sections/preliminaries.tex`
- Create: `tests/fixtures/multifile/sections/results.tex`
- Create: `tests/test_multifile.py`
- Modify: `src/papergraph/server.py`

**Interfaces:**
- Consumes: `load_latex_project`, `parse_latex`, and `PaperGraph`
- Produces: cross-file graphs and project-aware MCP `load_paper(path)`

- [ ] **Step 1: Add a multi-file fixture**

`tests/fixtures/multifile/main.tex`:

```latex
\documentclass{article}
\newtheorem{lemma}{Lemma}
\newtheorem{theorem}{Theorem}
\begin{document}
\input{sections/preliminaries}
\include{sections/results}
\end{document}
```

`tests/fixtures/multifile/sections/preliminaries.tex`:

```latex
\begin{lemma}
\label{lem:base}
Every finite nonempty set has an element.
\end{lemma}
```

`tests/fixtures/multifile/sections/results.tex`:

```latex
\begin{theorem}
\label{thm:result}
By Lemma~\ref{lem:base}, the result follows.
\end{theorem}
```

- [ ] **Step 2: Write the integration test**

Create `tests/test_multifile.py`:

```python
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from papergraph import server
from papergraph.graph import PaperGraph
from papergraph.loader import load_latex_project
from papergraph.parser import parse_latex


PROJECT = (
    Path(__file__).parent
    / "fixtures"
    / "multifile"
    / "main.tex"
)


def test_multifile_project_builds_cross_file_graph():
    nodes = parse_latex(load_latex_project(PROJECT))
    graph = PaperGraph(nodes)
    assert [node.id for node in nodes] == [
        "lem:base",
        "thm:result",
    ]
    assert [
        node.id
        for node in graph.dependencies("thm:result")
    ] == ["lem:base"]


def test_mcp_load_paper_loads_the_complete_project():
    result = server.load_paper(str(PROJECT))

    assert result["nodes"] == 2
    assert result["kinds"] == {
        "lemma": 1,
        "theorem": 1,
    }


def test_mcp_load_paper_translates_missing_include_error(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    main.write_text("\\input{missing}", encoding="utf-8")

    with pytest.raises(ToolError, match="missing[.]tex"):
        server.load_paper(str(main))
```

- [ ] **Step 3: Run and verify RED**

Run `uv run pytest tests/test_multifile.py -q -p no:cacheprovider`.

Expected: the direct loader/parser/graph test passes, while both MCP tests fail because v0.1 still parses only the root file and does not visit the missing include.

- [ ] **Step 4: Integrate MCP error translation**

In `server.py`, import:

```python
from papergraph.loader import load_latex_project
from papergraph.parser import parse_latex
```

Change the suffix error to:

```python
raise ToolError(
    "PaperGraph only accepts a .tex root file."
)
```

Replace `nodes = parse_file(paper_path)`:

```python
try:
    text = load_latex_project(paper_path)
except (OSError, ValueError) as exc:
    raise ToolError(str(exc)) from exc

nodes = parse_latex(text)
```

- [ ] **Step 5: Verify and commit**

Run:

```powershell
uv run pytest -q -p no:cacheprovider
git add src/papergraph/server.py tests/fixtures/multifile tests/test_multifile.py
git commit -m "Load multi-file projects through MCP"
```

Expected: all tests pass before commit.

---

### Task 5: Publish v0.2 metadata and documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `README.md`

**Interfaces:**
- Produces: package version `0.2.0` and root-file usage documentation

- [ ] **Step 1: Update package metadata**

Set `version = "0.2.0"` in `pyproject.toml`, then run `uv lock`.

Expected: the local package entry in `uv.lock` becomes `0.2.0` without unrelated upgrades.

- [ ] **Step 2: Document usage**

Write `README.md`:

```markdown
# PaperGraph MCP

PaperGraph turns theorem-like environments in local LaTeX papers into a dependency graph exposed through MCP.

## Development

~~~powershell
uv sync
uv run pytest -q -p no:cacheprovider
~~~

## Load a paper

Call the MCP `load_paper` tool with the root `.tex` file. PaperGraph v0.2 recursively follows standard `\input{...}` and `\include{...}` commands. Included paths are resolved relative to the containing file, and `.tex` is optional in those commands.

The `list_theorems`, `get_theorem`, `get_dependencies`, and `where_used` tools operate on the combined graph.
```

- [ ] **Step 3: Validate and commit**

Run:

```powershell
uv run python -c "import papergraph; import mcp; print('imports OK')"
uv run pytest -q -p no:cacheprovider
git diff --check
git add pyproject.toml uv.lock README.md
git commit -m "Document PaperGraph MCP v0.2"
```

Expected: `imports OK`, all tests pass, and no whitespace errors appear before commit.

---

### Task 6: Final review and acceptance

**Files:**
- Review: all changes from `main` through `feature/v0.2-multifile`

**Interfaces:**
- Produces: evidence-backed acceptance without merging to `main` or pushing

- [ ] **Step 1: Run final verification**

Run:

```powershell
uv run pytest -q -p no:cacheprovider
uv run python -c "from pathlib import Path; from papergraph.graph import PaperGraph; from papergraph.loader import load_latex_project; from papergraph.parser import parse_latex; p=Path('tests/fixtures/multifile/main.tex'); g=PaperGraph(parse_latex(load_latex_project(p))); print([(n.id, n.kind, n.refs) for n in g.nodes])"
git status --short --branch
git log --graph --oneline --decorate -10
```

Expected: all tests pass; smoke output lists `lem:base` then `thm:result`, with the theorem referencing `lem:base`; the tree is clean; history contains v0.1 and v0.2.

- [ ] **Step 2: Review branch scope**

Run:

```powershell
git diff --stat main...HEAD
git diff --check main...HEAD
```

Expected: only source, tests, fixtures, documentation, metadata, spec, and plan changes; no whitespace errors.

- [ ] **Step 3: Report completion**

Report the migration method, loader behavior, files changed, exact test result, smoke-test result, current branch, and confirmation that nothing was merged into `main` or pushed.
