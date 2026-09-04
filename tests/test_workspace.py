import json
import sqlite3
from pathlib import Path

import pytest

from papergraph.citations import BibliographyParseError
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
            joined_authors = r" \and ".join(authors)
            metadata += rf"\author{{{joined_authors}}}"
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
        "source_spans",
        "results",
        "result_source_spans",
        "proofs",
        "proof_source_spans",
        "bibliography_entries",
        "local_result_mentions",
        "citation_mentions",
        "external_result_mentions",
        "evidence_edges",
        "evidence_edge_source_spans",
    }
    assert fetch_all(
        path,
        "SELECT value FROM workspace_meta WHERE key = 'schema_version'",
    ) == [("3",)]


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
            "INSERT INTO workspace_meta VALUES ('schema_version', '4')"
        )

    import papergraph.workspace as workspace_module

    real_connect = sqlite3.connect
    opened: list[sqlite3.Connection] = []

    def tracking_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(workspace_module.sqlite3, "connect", tracking_connect)

    with pytest.raises(WorkspaceSchemaError, match="schema version 4"):
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
            "INSERT INTO workspace_meta VALUES ('schema_version', '3')"
        )

    with pytest.raises(WorkspaceSchemaError, match="missing required tables.*papers"):
        Workspace.open(path)


def test_workspace_enables_and_enforces_foreign_keys(workspace: Workspace):
    assert workspace._connection.execute("PRAGMA foreign_keys").fetchone() == (1,)

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        workspace._connection.execute(
            """
            INSERT INTO theorems (
                global_id, paper_id, local_id, kind, raw_kind, display_kind,
                normalized_kind, title, label, content, source_file, position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "local:missing::thm:x",
                "local:missing",
                "thm:x",
                "theorem",
                "theorem",
                "theorem",
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


def test_workspace_persists_theorem_kind_metadata(
    workspace: Workspace,
    project_factory,
):
    project = project_factory(
        r"\newtheorem{thm}{Theorem}"
        r"\begin{thm}\label{thm:main}Main.\end{thm}"
    )

    workspace.import_project("local:kinds", "local", "main.tex", None, project)

    assert workspace._connection.execute(
        "SELECT kind, raw_kind, display_kind, normalized_kind FROM theorems"
    ).fetchall() == [("thm", "thm", "Theorem", "theorem")]
    assert workspace.get_paper("local:kinds")["kinds"] == {"theorem": 1}
    result = workspace.search_theorems("Main")[0]
    assert {
        key: result[key]
        for key in ("kind", "raw_kind", "display_kind", "normalized_kind")
    } == {
        "kind": "thm",
        "raw_kind": "thm",
        "display_kind": "Theorem",
        "normalized_kind": "theorem",
    }


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


def test_malformed_bibliography_does_not_replace_existing_paper(
    workspace: Workspace,
    loaded_project,
    project_factory,
):
    workspace.import_project(
        "local:paper-a", "local", "original.tex", None, loaded_project
    )
    malformed = project_factory(
        r"\cite{broken}",
        bibliography="@article{broken, title = {unterminated",
    )

    with pytest.raises(BibliographyParseError):
        workspace.import_project(
            "local:paper-a", "local", "replacement.tex", None, malformed
        )

    assert workspace.get_paper("local:paper-a")["source_ref"] == "original.tex"
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

    assert (result.citation_count, result.unresolved_citation_count) == (2, 2)
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


def test_lists_papers_with_metadata_and_current_graph_counts_in_id_order(
    workspace: Workspace,
    project_factory,
):
    citing = project_factory(
        r"\begin{theorem}\label{thm:a}Compactness theorem.\end{theorem}"
        r"\cite{known}\cite{missing}",
        title="Paper A",
        authors=("Ada Lovelace",),
        bibliography="@article{known, arxiv={2401.12345}}",
    )
    target = project_factory(
        r"\begin{lemma}\label{lem:b}Target lemma.\end{lemma}",
        title="Paper B",
    )

    workspace.import_project("local:paper-a", "local", "a/main.tex", None, citing)
    workspace.import_project(
        "arxiv:2401.12345", "arxiv", "2401.12345", "v2", target
    )

    papers = workspace.list_papers()
    assert [paper["paper_id"] for paper in papers] == [
        "arxiv:2401.12345",
        "local:paper-a",
    ]
    assert papers[1]["authors"] == ["Ada Lovelace"]
    assert papers[1]["theorem_count"] == 1
    assert papers[1]["citation_count"] == 2
    assert papers[1]["unresolved_citation_count"] == 1

    paper = workspace.get_paper(" local:paper-a ")
    assert paper["paper_id"] == "local:paper-a"
    assert paper["kinds"] == {"theorem": 1}
    assert paper["outgoing_citation_count"] == 1
    assert paper["incoming_citation_count"] == 0


def test_paper_queries_reject_unknown_ids(workspace: Workspace):
    with pytest.raises(KeyError, match="Unknown paper id: local:missing"):
        workspace.get_paper("local:missing")
    with pytest.raises(KeyError, match="Unknown paper id: local:missing"):
        workspace.get_citations("local:missing")


def test_resolves_citation_when_target_arrives_later_and_on_reimport(
    workspace: Workspace,
    project_factory,
):
    citing = project_factory(
        r"\cite{target}",
        bibliography="@article{target, arxiv={2401.12345v2}}",
    )
    target = project_factory(
        r"\begin{theorem}\label{thm:target}Target.\end{theorem}"
    )

    imported = workspace.import_project(
        "local:paper-a", "local", "a/main.tex", None, citing
    )
    assert imported.unresolved_citation_count == 1
    before = workspace.get_citations("local:paper-a")[0]
    assert before["target_paper_id"] is None
    assert before["resolution_status"] == "resolved_candidate"

    workspace.import_project(
        "arxiv:2401.12345", "arxiv", "2401.12345", None, target
    )
    resolved = workspace.get_citations("local:paper-a")[0]
    assert resolved["target_paper_id"] == "arxiv:2401.12345"
    assert resolved["resolution_status"] == "resolved_candidate"

    workspace.import_project(
        "arxiv:2401.12345", "arxiv", "2401.12345", "v3", target
    )
    assert workspace.get_citations("local:paper-a")[0][
        "target_paper_id"
    ] == "arxiv:2401.12345"


def test_import_result_counts_only_evidence_without_a_workspace_target(
    workspace: Workspace,
    project_factory,
):
    target = project_factory(
        r"\begin{theorem}\label{thm:target}Target.\end{theorem}"
    )
    workspace.import_project(
        "arxiv:2401.12345", "arxiv", "2401.12345", None, target
    )
    citing = project_factory(
        r"\cite{resolved,absent,unsupported,missing}",
        bibliography=(
            "@article{resolved, arxiv={2401.12345}}\n"
            "@article{absent, arxiv={2401.99999}}\n"
            "@article{unsupported, doi={10.1000/example}}"
        ),
    )

    result = workspace.import_project(
        "local:source", "local", "main.tex", None, citing
    )

    assert result.citation_count == 4
    assert result.unresolved_citation_count == 3
    assert {
        row["citation_key"]: row["target_paper_id"]
        for row in workspace.get_citations("local:source")
    } == {
        "absent": None,
        "missing": None,
        "resolved": "arxiv:2401.12345",
        "unsupported": None,
    }


def test_legacy_citation_id_is_canonicalized_for_late_resolution(
    workspace: Workspace,
    project_factory,
):
    citing = project_factory(
        r"\cite{target}",
        bibliography="@article{target, arxiv={Math/0307200v2}}",
    )
    target = project_factory(
        r"\begin{theorem}\label{thm:target}Target.\end{theorem}"
    )

    workspace.import_project("local:source", "local", "main.tex", None, citing)
    before = workspace.get_citations("local:source")[0]
    assert before["cited_arxiv_id"] == "math/0307200"
    assert before["target_paper_id"] is None

    workspace.import_project(
        "arxiv:math/0307200", "arxiv", "math/0307200", None, target
    )

    assert workspace.get_citations("local:source")[0][
        "target_paper_id"
    ] == "arxiv:math/0307200"


def test_citation_resolution_failure_rolls_back_paper_replacement(
    workspace: Workspace,
    project_factory,
):
    original = project_factory(
        r"\begin{theorem}\label{thm:old}Old.\end{theorem}\cite{old}",
        bibliography="@article{old, arxiv={2401.12345}}",
    )
    replacement = project_factory(
        r"\begin{theorem}\label{thm:new}New.\end{theorem}\cite{new}",
        bibliography="@article{new, arxiv={2401.99999}}",
    )
    workspace.import_project(
        "local:paper-a", "local", "original.tex", None, original
    )
    workspace._connection.execute(
        """
        CREATE TRIGGER fail_citation_resolution
        BEFORE UPDATE OF target_paper_id ON citation_evidence
        WHEN NEW.source_paper_id = 'local:paper-a'
        BEGIN
            SELECT RAISE(ABORT, 'injected citation resolution failure');
        END
        """
    )

    with pytest.raises(
        sqlite3.IntegrityError,
        match="injected citation resolution failure",
    ):
        workspace.import_project(
            "local:paper-a", "local", "replacement.tex", None, replacement
        )

    assert workspace.get_paper("local:paper-a")["source_ref"] == "original.tex"
    citations = workspace.get_citations("local:paper-a")
    assert [row["citation_key"] for row in citations] == ["old"]


def test_citation_queries_preserve_evidence_rows_reasons_and_direction(
    workspace: Workspace,
    project_factory,
):
    first = project_factory(
        r"\cite{target}\citet{target}\cite{missing}\cite{unsupported}",
        bibliography=(
            "@article{target, arxiv={2401.12345}}\n"
            "@article{unsupported, doi={10.1000/example}}"
        ),
    )
    second = project_factory(
        r"\cite{target}",
        bibliography="@article{target, arxiv={2401.12345}}",
    )
    target = project_factory(
        r"\begin{theorem}\label{thm:target}Target.\end{theorem}"
    )
    workspace.import_project("local:z-paper", "local", "z/main.tex", None, first)
    workspace.import_project("local:a-paper", "local", "a/main.tex", None, second)
    workspace.import_project(
        "arxiv:2401.12345", "arxiv", "2401.12345", None, target
    )

    outgoing = workspace.get_citations("local:z-paper")
    assert [(row["citation_key"], row["command"]) for row in outgoing] == [
        ("missing", "cite"),
        ("target", "cite"),
        ("target", "citet"),
        ("unsupported", "cite"),
    ]
    assert {
        (row["citation_key"], row["resolution_status"])
        for row in outgoing
    } == {
        ("missing", "missing_bib_entry"),
        ("target", "resolved_candidate"),
        ("unsupported", "unsupported_identifier"),
    }
    resolved = workspace.get_citations(
        "local:z-paper",
        include_unresolved=False,
    )
    assert [row["citation_key"] for row in resolved] == ["target", "target"]

    incoming = workspace.get_citations(
        "arxiv:2401.12345", direction="incoming"
    )
    assert [row["source_paper_id"] for row in incoming] == [
        "local:a-paper",
        "local:z-paper",
        "local:z-paper",
    ]
    assert all(row["target_paper_id"] == "arxiv:2401.12345" for row in incoming)


@pytest.mark.parametrize("direction", ["", "sideways", "OUTGOING"])
def test_citation_queries_reject_invalid_direction_before_sql(
    workspace: Workspace,
    monkeypatch,
    direction: str,
):
    monkeypatch.setattr(
        workspace,
        "_paper_exists",
        lambda paper_id: pytest.fail(
            "paper lookup must not happen before direction validation"
        ),
    )
    with pytest.raises(ValueError, match="direction"):
        workspace.get_citations("local:missing", direction=direction)


def test_searches_theorems_across_papers_with_filters_and_stable_order(
    workspace: Workspace,
    project_factory,
):
    local = project_factory(
        r"\begin{theorem}[Compactness]\label{thm:z}Title match.\end{theorem}"
        r"\begin{lemma}\label{lem:a}Body compactness match.\end{lemma}"
    )
    arxiv = project_factory(
        r"\begin{proposition}\label{prop:b}COMPACTNESS elsewhere.\end{proposition}"
    )
    other = project_factory(
        r"\begin{theorem}\label{thm:none}No match.\end{theorem}"
    )
    workspace.import_project("local:paper-a", "local", "a/main.tex", None, local)
    workspace.import_project(
        "arxiv:2401.12345", "arxiv", "2401.12345", None, arxiv
    )
    workspace.import_project("local:paper-c", "local", "c/main.tex", None, other)

    results = workspace.search_theorems("compactness", limit=20)
    assert [item["global_id"] for item in results] == [
        "arxiv:2401.12345::prop:b",
        "local:paper-a::lem:a",
        "local:paper-a::thm:z",
    ]
    assert {item["paper_id"] for item in results} == {
        "local:paper-a",
        "arxiv:2401.12345",
    }
    filtered = workspace.search_theorems(
        "compactness",
        paper_id="local:paper-a",
        kind="lemma",
    )
    assert [item["global_id"] for item in filtered] == ["local:paper-a::lem:a"]


def test_search_excerpt_is_bounded_and_limit_is_applied_after_ordering(
    workspace: Workspace,
    project_factory,
):
    project = project_factory(
        r"\begin{theorem}\label{thm:z}needle " + "x" * 300 + r"\end{theorem}"
        r"\begin{lemma}\label{lem:a}needle short\end{lemma}"
    )
    workspace.import_project("local:paper", "local", "main.tex", None, project)

    result = workspace.search_theorems("needle", limit=1)
    assert [item["global_id"] for item in result] == ["local:paper::lem:a"]
    all_results = workspace.search_theorems("needle", limit=20)
    assert len(all_results[1]["excerpt"]) == 240


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_search_rejects_empty_queries(workspace: Workspace, query: str):
    with pytest.raises(ValueError, match="query"):
        workspace.search_theorems(query)


@pytest.mark.parametrize("limit", [0, 101, -1, 1.5, True])
def test_search_rejects_invalid_limit(workspace: Workspace, limit):
    with pytest.raises(ValueError, match="limit"):
        workspace.search_theorems("theorem", limit=limit)


def test_dependencies_are_deterministic_cycle_safe_and_match_graph_semantics(
    workspace: Workspace,
    project_factory,
):
    project = project_factory(
        r"\begin{theorem}\label{thm:a}Uses \ref{thm:c} and \ref{thm:b}.\end{theorem}"
        r"\begin{lemma}\label{thm:b}Uses \ref{thm:a}.\end{lemma}"
        r"\begin{proposition}\label{thm:c}Leaf.\end{proposition}"
    )
    workspace.import_project("local:cycles", "local", "main.tex", None, project)

    direct = workspace.get_dependencies("local:cycles::thm:a")
    assert [item["global_id"] for item in direct] == [
        "local:cycles::thm:b",
        "local:cycles::thm:c",
    ]
    recursive = workspace.get_dependencies(
        "local:cycles::thm:a",
        recursive=True,
    )
    assert [item["global_id"] for item in recursive] == [
        "local:cycles::thm:b",
        "local:cycles::thm:a",
        "local:cycles::thm:c",
    ]


def test_dependencies_reject_unknown_global_id(workspace: Workspace):
    with pytest.raises(KeyError, match="Unknown theorem id: local:missing::thm:x"):
        workspace.get_dependencies("local:missing::thm:x")


def test_workspace_dependency_diagnostics_include_unresolved_refs(
    workspace: Workspace,
    loaded_project,
):
    workspace.import_project(
        "local:paper-a", "local", "paper-a/main.tex", None, loaded_project
    )

    diagnostics = workspace.get_dependency_diagnostics(
        "local:paper-a::thm:main"
    )

    assert diagnostics == {
        "global_theorem_id": "local:paper-a::thm:main",
        "recursive": False,
        "extraction_basis": "statement_explicit_latex_refs_only",
        "referenced_labels": ["lem:base", "missing"],
        "resolved_labels": ["lem:base"],
        "unresolved_labels": ["missing"],
        "dependency_ids": ["local:paper-a::lem:base"],
        "warnings": [],
    }


def test_workspace_dependency_diagnostics_warn_for_empty_results(
    workspace: Workspace,
    project_factory,
):
    project = project_factory(
        r"\begin{theorem}\label{thm:isolated}No references.\end{theorem}"
    )
    workspace.import_project("local:paper", "local", "main.tex", None, project)

    diagnostics = workspace.get_dependency_diagnostics(
        "local:paper::thm:isolated"
    )

    assert diagnostics["dependency_ids"] == []
    assert diagnostics["warnings"] == [
        "No explicit theorem-label dependencies were detected in the theorem statement. This is not evidence that the theorem has no mathematical dependencies."
    ]
