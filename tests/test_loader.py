from pathlib import Path

import pytest

from papergraph.loader import load_latex_project, resolve_tex_path
from papergraph.project import load_project


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


def test_commented_include_is_not_expanded(tmp_path: Path):
    main = tmp_path / "main.tex"
    main.write_text(
        "% \\input{missing}\nVISIBLE",
        encoding="utf-8",
    )

    text = load_latex_project(main)

    assert "VISIBLE" in text
    assert "\\input{missing}" in text


def test_escaped_percent_does_not_comment_out_include(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    included = tmp_path / "included.tex"
    main.write_text(
        "\\% literal percent \\input{included}",
        encoding="utf-8",
    )
    included.write_text("EXPANDED", encoding="utf-8")

    assert "EXPANDED" in load_latex_project(main)


def test_repeated_non_cyclic_include_is_expanded_twice(
    tmp_path: Path,
):
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

    with pytest.raises(
        FileNotFoundError,
        match="missing[.]tex",
    ):
        load_latex_project(main)


def test_circular_include_reports_chain(tmp_path: Path):
    first = tmp_path / "first.tex"
    second = tmp_path / "second.tex"
    first.write_text("\\input{second}", encoding="utf-8")
    second.write_text("\\include{first}", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="Circular LaTeX include",
    ):
        load_latex_project(first)


def test_string_loader_returns_the_same_expanded_text_as_structured_loading(
    tmp_path: Path,
):
    main = tmp_path / "main.tex"
    section = tmp_path / "section.tex"
    main.write_text("before\\input{section}after", encoding="utf-8")
    section.write_text("middle", encoding="utf-8")

    assert load_latex_project(main) == load_project(main).text
