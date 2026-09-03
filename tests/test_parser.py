from pathlib import Path

from papergraph.parser import parse_file, parse_latex


SAMPLE = (
    Path(__file__).parent
    / "fixtures"
    / "sample.tex"
)


def test_parse_theorem_environments():
    nodes = parse_file(SAMPLE)

    assert len(nodes) == 3

    assert nodes[0].id == "lem:vanishing"
    assert nodes[0].kind == "lemma"
    summary = nodes[0].summary()
    assert {
        key: summary[key]
        for key in ("kind", "raw_kind", "display_kind", "normalized_kind")
    } == {
        "kind": "lemma",
        "raw_kind": "lemma",
        "display_kind": "Lemma",
        "normalized_kind": "lemma",
    }

    assert nodes[1].id == "prop:key"
    assert nodes[1].kind == "proposition"

    assert nodes[2].id == "thm:main"
    assert nodes[2].kind == "theorem"


def test_extract_references():
    nodes = parse_file(SAMPLE)

    proposition = nodes[1]
    theorem = nodes[2]

    assert proposition.refs == (
        "lem:vanishing",
    )

    assert theorem.refs == (
        "prop:key",
        "lem:vanishing",
    )


def test_newtheorem_display_kind_and_normalized_kind_are_preserved():
    nodes = parse_latex(
        r"\newtheorem{thm}{Theorem}"
        r"\newtheorem{propn}{Proposition}"
        r"\begin{thm}\label{thm:main}Main.\end{thm}"
        r"\begin{propn}[Key step]\label{prop:key}Step.\end{propn}"
    )

    assert nodes[0].kind == "thm"
    assert nodes[0].raw_kind == "thm"
    assert nodes[0].display_kind == "Theorem"
    assert nodes[0].normalized_kind == "theorem"
    assert nodes[0].summary()["display_kind"] == "Theorem"
    assert nodes[0].summary()["normalized_kind"] == "theorem"

    assert nodes[1].kind == "propn"
    assert nodes[1].raw_kind == "propn"
    assert nodes[1].display_kind == "Proposition"
    assert nodes[1].normalized_kind == "proposition"


def test_unknown_theorem_display_kind_falls_back_to_raw_lowercase():
    nodes = parse_latex(
        r"\newtheorem{axiomx}{Axiom}"
        r"\begin{axiomx}\label{ax:one}Axiom text.\end{axiomx}"
    )

    assert nodes[0].kind == "axiomx"
    assert nodes[0].raw_kind == "axiomx"
    assert nodes[0].display_kind == "Axiom"
    assert nodes[0].normalized_kind == "axiomx"
