from pathlib import Path

from papergraph.parser import parse_file


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