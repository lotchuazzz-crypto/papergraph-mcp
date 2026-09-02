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
