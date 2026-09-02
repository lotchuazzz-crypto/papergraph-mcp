import json
import sqlite3
from pathlib import Path

import pytest

from papergraph.project import load_project
from papergraph.workspace import (
    DuplicateTheoremIdError,
    Workspace,
    WorkspaceSchemaError,
)


@pytest.fixture
def project_factory(tmp_path: Path):
    counter = 0

    def make_project(
        body: str,
        *,
        title: str | None = None,
        authors: tuple[str, ...] = (),
        bibliography: str | None = None,
    ):
        nonlocal counter
        counter += 1
        root = tmp_path / f"project-{counter}"
        root.mkdir()
        metadata = ""
        if title is not None:
            metadata += rf"\title{{{title}}}"
        if authors:
            metadata += rf"\author{{{' \\and '.join(authors)}}}"
        if bibliography is not None:
            (root / "refs.bib").write_text(bibliography, encoding="utf-8")
            body += r"\bibliography{refs}"
        main = root / "main.tex"
        main.write_text(metadata + body, encoding="utf-8")
        return load_project(main)

    return make_project


@pytest.fixture
def loaded_project(project_factory):
    return project_factory(
        r"\begin{lemma}\label{lem:base}Base.\end{lemma}"
        r"\begin{theorem}\label{thm:main}"
        r"Uses \ref{lem:base} and \ref{missing}."
        r"\end{theorem}",
        title="A paper",
        authors=("Ada Lovelace", "Emmy Noether"),
    )


@pytest.fixture
def duplicate_label_project(project_factory):
    return project_factory(
        r"\begin{theorem}\label{thm:duplicate}First.\end{theorem}"
        r"\begin{lemma}\label{thm:duplicate}Second.\end{lemma}"
    )


@pytest.fixture
def workspace(tmp_path: Path):
    opened = Workspace.open(tmp_path / "workspace.sqlite3")
    try:
        yield opened
    finally:
        opened.close()


def fetch_all(path: Path, statement: str, parameters=()):
    with sqlite3.connect(path) as connection:
        return connection.execute(statement, parameters).fetchall()


def test_workspace_creates_versioned_schema_and_only_the_parent(tmp_path: Path):
    path = tmp_path / "nested" / "papers.sqlite3"

    workspace = Workspace.open(path)
    workspace.close()

    assert path.is_file()
    tables = {
        row[0]
        for row in fetch_all(
            path,
            "SELECT name FROM sqlite_master WHERE type = 'table'",
        )
    }
    assert tables == {
        "workspace_meta",
        "papers",
        "theorems",
        "theorem_refs",
        "citation_evidence",
    }
    assert fetch_all(
        path,
        "SELECT value FROM workspace_meta WHERE key = 'schema_version'",
    ) == [("1",)]


def test_workspace_rejects_a_directory_path(tmp_path: Path):
    directory = tmp_path / "not-a-database"
    directory.mkdir()

    with pytest.raises(ValueError, match="directory"):
        Workspace.open(directory)


def test_workspace_rejects_newer_schema_and_closes_connection(
    tmp_path: Path,
    monkeypatch,
):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE workspace_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO workspace_meta VALUES ('schema_version', '2')"
        )

    import papergraph.workspace as workspace_module

    real_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(workspace_module.sqlite3, "connect", tracking_connect)

    with pytest.raises(WorkspaceSchemaError, match="schema version 2"):
        Workspace.open(path)

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_workspace_rejects_partial_current_schema(tmp_path: Path):
    path = tmp_path / "partial.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE workspace_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO workspace_meta VALUES ('schema_version', '1')"
        )

    with pytest.raises(WorkspaceSchemaError, match="missing required tables.*papers"):
        Workspace.open(path)


def test_workspace_enables_and_enforces_foreign_keys(workspace: Workspace):
    assert workspace._connection.execute("PRAGMA foreign_keys").fetchone() == (1,)

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        workspace._connection.execute(
            """
            INSERT INTO theorems (
                global_id, paper_id, local_id, kind, title, label,
                content, source_file, position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "local:missing::thm:x",
                "local:missing",
                "thm:x",
                "theorem",
                None,
                "thm:x",
                "content",
                "main.tex",
                0,
            ),
        )


def test_workspace_persists_across_connections(tmp_path: Path, loaded_project):
    path = tmp_path / "papers.sqlite3"
    workspace = Workspace.open(path)
    result = workspace.import_project(
        "local:paper-a", "local", "paper-a/main.tex", None, loaded_project
    )
    workspace.close()

    reopened = Workspace.open(path)
    try:
        assert reopened.counts() == {
            "papers": 1,
            "theorems": result.theorem_count,
        }
    finally:
        reopened.close()


def test_import_persists_theorems_and_resolved_and_unresolved_refs(
    workspace: Workspace,
    loaded_project,
):
    result = workspace.import_project(
        "local:paper-a", "local", "paper-a/main.tex", None, loaded_project
    )

    assert result.theorem_count == 2
    assert workspace._connection.execute(
        "SELECT global_id, source_file FROM theorems ORDER BY position"
    ).fetchall() == [
        ("local:paper-a::lem:base", "main.tex"),
        ("local:paper-a::thm:main", "main.tex"),
    ]
    assert workspace._connection.execute(
        "SELECT ref_label, target_global_id FROM theorem_refs ORDER BY ref_label"
    ).fetchall() == [
        ("lem:base", "local:paper-a::lem:base"),
        ("missing", None),
    ]


def test_import_rejects_duplicate_local_ids_without_replacing_old_data(
    workspace: Workspace,
    loaded_project,
    duplicate_label_project,
):
    workspace.import_project(
        "local:paper-a", "local", "first.tex", None, loaded_project
    )

    with pytest.raises(DuplicateTheoremIdError, match="thm:duplicate"):
        workspace.import_project(
            "local:paper-a", "local", "broken.tex", None, duplicate_label_project
        )

    assert workspace._connection.execute(
        "SELECT source_ref FROM papers WHERE paper_id = 'local:paper-a'"
    ).fetchone() == ("first.tex",)
    assert workspace.counts() == {"papers": 1, "theorems": 2}


@pytest.mark.parametrize(
    ("paper_id", "source_type"),
    [
        ("local:paper-a", "arxiv"),
        ("arxiv:2401.12345", "local"),
    ],
)
def test_import_rejects_source_type_that_disagrees_with_paper_id(
    workspace: Workspace,
    loaded_project,
    paper_id: str,
    source_type: str,
):
    with pytest.raises(ValueError, match="source type.*paper id"):
        workspace.import_project(
            paper_id,
            source_type,
            "main.tex",
            None,
            loaded_project,
        )

    assert workspace.counts() == {"papers": 0, "theorems": 0}


def test_citation_parsing_failure_occurs_before_replacement_mutation(
    workspace: Workspace,
    loaded_project,
    project_factory,
):
    workspace.import_project(
        "local:paper-a", "local", "original.tex", None, loaded_project
    )
    invalid = project_factory(
        r"\cite{target}",
        bibliography="@article{target, arxiv={2401.12345}}",
    )
    (invalid.project_root / "second.bib").write_text(
        "@article{target, arxiv={2401.12346}}",
        encoding="utf-8",
    )
    invalid.root_file.write_text(
        invalid.root_file.read_text(encoding="utf-8")
        + r"\bibliography{second}",
        encoding="utf-8",
    )
    invalid = load_project(invalid.root_file)

    with pytest.raises(ValueError, match="Conflicting bibliography entries.*target"):
        workspace.import_project(
            "local:paper-a", "local", "replacement.tex", None, invalid
        )

    assert workspace._connection.execute(
        "SELECT source_ref FROM papers WHERE paper_id = 'local:paper-a'"
    ).fetchone() == ("original.tex",)
    assert workspace.counts() == {"papers": 1, "theorems": 2}


def test_colliding_local_labels_are_allowed_across_papers(
    workspace: Workspace,
    project_factory,
):
    first = project_factory(
        r"\begin{theorem}\label{thm:shared}First.\end{theorem}"
    )
    second = project_factory(
        r"\begin{theorem}\label{thm:shared}Second.\end{theorem}"
    )

    workspace.import_project("local:first", "local", "first.tex", None, first)
    workspace.import_project("local:second", "local", "second.tex", None, second)

    assert workspace._connection.execute(
        "SELECT global_id FROM theorems ORDER BY global_id"
    ).fetchall() == [
        ("local:first::thm:shared",),
        ("local:second::thm:shared",),
    ]


def test_import_preserves_non_ascii_metadata_and_content(
    workspace: Workspace,
    project_factory,
):
    project = project_factory(
        r"\begin{theorem}[紧致性]\label{thm:compact}任意开覆盖有有限子覆盖。\end{theorem}",
        title="紧致空间",
        authors=("陈省身", "Noémie Dupont"),
    )

    workspace.import_project(
        "local:unicode", "local", "论文/main.tex", None, project
    )

    paper = workspace._connection.execute(
        "SELECT title, authors_json FROM papers WHERE paper_id = 'local:unicode'"
    ).fetchone()
    theorem = workspace._connection.execute(
        "SELECT title, content FROM theorems WHERE paper_id = 'local:unicode'"
    ).fetchone()
    assert paper == (
        "紧致空间",
        json.dumps(["陈省身", "Noémie Dupont"], ensure_ascii=False),
    )
    assert "\\u" not in paper[1]
    assert theorem == ("紧致性", r"\label{thm:compact}任意开覆盖有有限子覆盖。")


def test_import_stores_citation_evidence_and_reports_counts(
    workspace: Workspace,
    project_factory,
):
    project = project_factory(
        r"\cite{known}\cite{missing}",
        bibliography="@article{known, arxiv={2401.12345v2}}",
    )

    result = workspace.import_project(
        "local:citing", "local", "main.tex", None, project
    )

    assert (result.citation_count, result.unresolved_citation_count) == (2, 1)
    assert workspace._connection.execute(
        """
        SELECT citation_key, cited_arxiv_id, cited_version,
               target_paper_id, resolution_status
        FROM citation_evidence ORDER BY id
        """
    ).fetchall() == [
        ("known", "2401.12345", "v2", None, "resolved_candidate"),
        ("missing", None, None, None, "missing_bib_entry"),
    ]


def test_sql_failure_rolls_back_the_entire_replacement(
    workspace: Workspace,
    loaded_project,
    project_factory,
):
    workspace.import_project(
        "local:paper-a", "local", "original.tex", None, loaded_project
    )
    replacement = project_factory(
        r"\begin{theorem}\label{thm:new}Replacement.\end{theorem}"
    )
    workspace._connection.execute(
        """
        CREATE TRIGGER fail_replacement
        BEFORE INSERT ON theorems
        WHEN NEW.paper_id = 'local:paper-a'
        BEGIN
            SELECT RAISE(ABORT, 'injected SQL failure');
        END
        """
    )

    with pytest.raises(sqlite3.IntegrityError, match="injected SQL failure"):
        workspace.import_project(
            "local:paper-a", "local", "replacement.tex", None, replacement
        )

    assert workspace._connection.execute(
        "SELECT source_ref FROM papers WHERE paper_id = 'local:paper-a'"
    ).fetchone() == ("original.tex",)
    assert workspace._connection.execute(
        "SELECT local_id FROM theorems WHERE paper_id = 'local:paper-a' ORDER BY local_id"
    ).fetchall() == [("lem:base",), ("thm:main",)]


def test_successful_replacement_is_atomic_and_leaves_other_papers_unchanged(
    workspace: Workspace,
    loaded_project,
    project_factory,
):
    other = project_factory(
        r"\begin{lemma}\label{lem:other}Other.\end{lemma}"
    )
    replacement = project_factory(
        r"\begin{theorem}\label{thm:new}New.\end{theorem}"
    )
    workspace.import_project(
        "local:paper-a", "local", "original.tex", None, loaded_project
    )
    workspace.import_project("local:paper-b", "local", "other.tex", None, other)

    workspace.import_project(
        "local:paper-a", "local", "replacement.tex", "draft-2", replacement
    )

    assert workspace.counts() == {"papers": 2, "theorems": 2}
    assert workspace._connection.execute(
        "SELECT paper_id, source_ref, source_version FROM papers ORDER BY paper_id"
    ).fetchall() == [
        ("local:paper-a", "replacement.tex", "draft-2"),
        ("local:paper-b", "other.tex", None),
    ]
    assert workspace._connection.execute(
        "SELECT global_id FROM theorems ORDER BY global_id"
    ).fetchall() == [
        ("local:paper-a::thm:new",),
        ("local:paper-b::lem:other",),
    ]
    assert workspace._connection.execute(
        "SELECT COUNT(*) FROM theorem_refs"
    ).fetchone() == (0,)
