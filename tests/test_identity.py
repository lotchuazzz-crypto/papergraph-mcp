import pytest

from papergraph.identity import (
    global_theorem_id,
    normalize_paper_id,
    paper_id_from_arxiv,
    split_global_theorem_id,
)


@pytest.mark.parametrize("value", ["local:my-preprint", "arxiv:2401.12345"])
def test_normalizes_valid_paper_ids(value):
    assert normalize_paper_id(value) == value


@pytest.mark.parametrize("value", ["paper", "local:UPPER", "local:two words", "arxiv:bad"])
def test_rejects_invalid_paper_ids(value):
    with pytest.raises(ValueError, match="Invalid paper id"):
        normalize_paper_id(value)


def test_arxiv_identity_ignores_version_but_preserves_it():
    assert paper_id_from_arxiv("2401.12345v3") == ("arxiv:2401.12345", "v3")


def test_round_trips_global_theorem_id():
    value = global_theorem_id("local:paper-a", "thm:main")
    assert value == "local:paper-a::thm:main"
    assert split_global_theorem_id(value) == ("local:paper-a", "thm:main")
