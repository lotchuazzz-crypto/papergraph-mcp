from pathlib import Path

import pytest

from papergraph.loader import load_latex_project
from papergraph.parser import parse_project
from papergraph.project import load_project


def test_load_project_preserves_sources_bibliographies_metadata_and_nodes(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    section = tmp_path / "sections" / "results.tex"
    bibliography = tmp_path / "refs.bib"
    section.parent.mkdir()
    main.write_text(
        r"\title{Graph Paper}\author{Ada}\input{sections/results}"
        r"\bibliography{refs}",
        encoding="utf-8",
    )
    section.write_text(
        r"\begin{theorem}\label{thm:x}X\end{theorem}",
        encoding="utf-8",
    )
    bibliography.write_text("@article{x, title={X}}", encoding="utf-8")

    project = load_project(main)

    assert project.root_file == main.resolve()
    assert project.project_root == tmp_path.resolve()
    assert project.bibliography_files == (bibliography.resolve(),)
    assert project.title == "Graph Paper"
    assert project.authors == ("Ada",)
    assert {span.path for span in project.spans} == {
        main.resolve(),
        section.resolve(),
    }
    assert parse_project(project)[0].source_file == "sections/results.tex"


def test_load_project_reads_addbibresource_and_splits_author_command(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    bibliography = tmp_path / "refs.bib"
    main.write_text(
        r"\author{ Ada \and Bob }\addbibresource{refs.bib}",
        encoding="utf-8",
    )
    bibliography.write_text("", encoding="utf-8")

    project = load_project(main)

    assert project.authors == ("Ada", "Bob")
    assert project.bibliography_files == (bibliography.resolve(),)


def test_load_project_resolves_bibliographies_relative_to_declaring_file(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    section = tmp_path / "sections" / "results.tex"
    bibliography = tmp_path / "refs" / "results.bib"
    section.parent.mkdir()
    bibliography.parent.mkdir()
    main.write_text(r"\input{sections/results}", encoding="utf-8")
    section.write_text(r"\bibliography{../refs/results}", encoding="utf-8")
    bibliography.write_text("", encoding="utf-8")

    project = load_project(main)

    assert project.bibliography_files == (bibliography.resolve(),)


def test_load_project_ignores_commented_metadata_and_bibliographies(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    bibliography = tmp_path / "visible.bib"
    main.write_text(
        "% \\title{Hidden}\n"
        "% \\bibliography{missing}\n"
        r"\title{Visible}\addbibresource{visible.bib}",
        encoding="utf-8",
    )
    bibliography.write_text("", encoding="utf-8")

    project = load_project(main)

    assert project.title == "Visible"
    assert project.bibliography_files == (bibliography.resolve(),)


def test_load_project_ignores_escaped_title_and_bibliography_commands(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    bibliography = tmp_path / "real.bib"
    main.write_text(
        r"\\title{Fake}\\bibliography{missing}"
        r"\title{Real}\bibliography{real}",
        encoding="utf-8",
    )
    bibliography.write_text("", encoding="utf-8")

    project = load_project(main)

    assert project.title == "Real"
    assert project.bibliography_files == (bibliography.resolve(),)


def test_load_project_does_not_extend_child_comments_into_parent_source(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    bibliography = tmp_path / "refs.bib"
    main.write_text(
        r"\input{child}\title{Parent}\bibliography{refs}",
        encoding="utf-8",
    )
    child.write_text("% child comment", encoding="utf-8")
    bibliography.write_text("", encoding="utf-8")

    project = load_project(main)

    assert project.title == "Parent"
    assert project.bibliography_files == (bibliography.resolve(),)


def test_load_project_does_not_create_commands_across_include_boundaries(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    child = tmp_path / "child.tex"
    main.write_text(r"\bibliog\input{child}", encoding="utf-8")
    child.write_text("raphy{refs}", encoding="utf-8")

    project = load_project(main)

    assert project.bibliography_files == ()


def test_load_project_rejects_missing_bibliography_file(tmp_path: Path):
    main = tmp_path / "main.tex"
    main.write_text(r"\bibliography{missing}", encoding="utf-8")

    with pytest.raises(ValueError, match="does not exist"):
        load_project(main)


def test_load_project_rejects_bibliography_outside_project_root(
    tmp_path: Path,
):
    project_root = tmp_path / "paper"
    main = project_root / "main.tex"
    outside = tmp_path / "outside.bib"
    project_root.mkdir()
    main.write_text(r"\bibliography{../outside}", encoding="utf-8")
    outside.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="outside project root"):
        load_project(main)


def test_load_project_rejects_include_outside_root_but_legacy_loader_allows_it(
    tmp_path: Path,
):
    project_root = tmp_path / "paper"
    main = project_root / "main.tex"
    outside = tmp_path / "outside.tex"
    project_root.mkdir()
    main.write_text(r"\input{../outside}", encoding="utf-8")
    outside.write_text("OUTSIDE", encoding="utf-8")

    assert load_latex_project(main) == "OUTSIDE"

    with pytest.raises(ValueError, match="outside project root"):
        load_project(main)


def test_load_project_rejects_bibliography_symlink_escaping_project_root(
    tmp_path: Path,
):
    project_root = tmp_path / "paper"
    main = project_root / "main.tex"
    outside = tmp_path / "outside.bib"
    linked = project_root / "linked.bib"
    project_root.mkdir()
    main.write_text(r"\bibliography{linked}", encoding="utf-8")
    outside.write_text("", encoding="utf-8")

    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this host")

    with pytest.raises(ValueError, match="outside project root"):
        load_project(main)


def test_load_project_deduplicates_bibliographies_and_repeated_includes(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    shared = tmp_path / "shared.tex"
    bibliography = tmp_path / "refs.bib"
    main.write_text(
        r"\input{shared}\input{shared}\bibliography{refs,refs}",
        encoding="utf-8",
    )
    shared.write_text(r"\addbibresource{refs.bib}", encoding="utf-8")
    bibliography.write_text("", encoding="utf-8")

    project = load_project(main)

    assert project.text.count(r"\addbibresource{refs.bib}") == 2
    shared_spans = [
        span
        for span in project.spans
        if span.path == shared.resolve()
    ]
    assert len(shared_spans) == 2
    assert all(
        project.text[span.start:span.end]
        == r"\addbibresource{refs.bib}"
        for span in shared_spans
    )
    assert project.bibliography_files == (bibliography.resolve(),)
