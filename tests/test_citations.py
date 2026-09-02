from pathlib import Path

import pytest

from papergraph.citations import (
    BibliographyParseError,
    build_citation_records,
    extract_citation_uses,
)
from papergraph.project import load_project


@pytest.fixture
def project_factory(tmp_path: Path):
    def make_project(
        *,
        body: str,
        bib: str = "",
        bibliography: str = "refs.bib",
        extra_sources: dict[str, str] | None = None,
    ):
        main = tmp_path / "main.tex"
        main.write_text(
            body + (rf"\bibliography{{{bibliography.removesuffix('.bib')}}}" if bib else ""),
            encoding="utf-8",
        )
        if bib:
            (tmp_path / bibliography).write_text(bib, encoding="utf-8")
        for relative_path, source in (extra_sources or {}).items():
            path = tmp_path / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source, encoding="utf-8")
        return load_project(main)

    return make_project


def test_extracts_supported_commands_in_source_order(project_factory):
    project = project_factory(
        body=(
            r"\cite{one,two}\citep{parenthetical}\citet{three}"
            r"\autocite{four}\parencite{five}\textcite{six}"
        )
    )

    uses = extract_citation_uses(project)

    assert [(use.command, use.key) for use in uses] == [
        ("cite", "one"), ("cite", "two"), ("citep", "parenthetical"),
        ("citet", "three"),
        ("autocite", "four"), ("parencite", "five"), ("textcite", "six"),
    ]


def test_extracts_starred_commands_with_optional_arguments_in_key_order(
    project_factory,
):
    project = project_factory(
        body=(
            r"\cite[p. 4]{one,two}"
            r"\citep*[see][§2]{three,one}"
            "\n% \\citet*[hidden]{ignored}"
        )
    )

    uses = extract_citation_uses(project)

    assert [(use.command, use.key) for use in uses] == [
        ("cite", "one"),
        ("cite", "two"),
        ("citep*", "three"),
        ("citep*", "one"),
    ]


def test_resolves_arxiv_evidence_and_preserves_version(project_factory):
    project = project_factory(
        body=r"\cite{target}",
        bib="@article{target, eprint={2401.12345v2}, archivePrefix={arXiv}}",
    )

    record = build_citation_records(project)[0]

    assert record.cited_arxiv_id == "2401.12345"
    assert record.cited_version == "v2"
    assert record.resolution_status == "resolved_candidate"


@pytest.mark.parametrize(
    ("field", "value", "version"),
    [
        ("arxiv", "arXiv:2401.12345v3", "v3"),
        ("url", "https://arxiv.org/abs/2401.12345v4", "v4"),
        ("note", "See arXiv:2401.12345v5 for details", "v5"),
    ],
)
def test_resolves_arxiv_evidence_from_supported_fields(
    project_factory,
    field: str,
    value: str,
    version: str,
):
    project = project_factory(
        body=r"\cite{target}",
        bib=f"@article{{target, {field}={{{value}}}}}",
    )

    record = build_citation_records(project)[0]

    assert (record.cited_arxiv_id, record.cited_version) == ("2401.12345", version)
    assert record.resolution_status == "resolved_candidate"


@pytest.mark.parametrize(
    ("value", "expected_id", "version"),
    [
        ("https://arxiv.org/abs/2401.12345?context=math", "2401.12345", None),
        ("https://arxiv.org/abs/2401.12345v2#details", "2401.12345", "v2"),
        (
            "https://arxiv.org/pdf/Math/0307200v3.pdf?download=1#page=2",
            "math/0307200",
            "v3",
        ),
    ],
)
def test_url_arxiv_evidence_accepts_only_supported_terminators(
    project_factory,
    value: str,
    expected_id: str,
    version: str | None,
):
    project = project_factory(
        body=r"\cite{target}",
        bib=f"@article{{target, url={{{value}}}}}",
    )

    record = build_citation_records(project)[0]

    assert (record.cited_arxiv_id, record.cited_version) == (expected_id, version)
    assert record.resolution_status == "resolved_candidate"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "https://arxiv.org/abs/2401.123456"),
        ("url", "https://arxiv.org/abs/2401.12345x"),
        ("url", "https://arxiv.org/abs/Math/03072000"),
        ("url", "https://arxiv.org/abs/Math/0307200x"),
        ("note", "See arXiv:2401.123456 for details"),
        ("note", "See arXiv:Math/0307200x for details"),
    ],
)
def test_does_not_truncate_invalid_arxiv_identifier_prefixes(
    project_factory,
    field: str,
    value: str,
):
    project = project_factory(
        body=r"\cite{target}",
        bib=f"@article{{target, {field}={{{value}}}}}",
    )

    record = build_citation_records(project)[0]

    assert record.cited_arxiv_id is None
    assert record.cited_version is None
    assert record.resolution_status == "unsupported_identifier"


def test_parses_nested_braces_and_multiline_bibtex_fields(project_factory):
    project = project_factory(
        body=r"\cite{target}",
        bib="""@article{target,
            title = {A {Nested} Title},
            url = {https://arxiv.org/pdf/2401.12345v6.pdf},
        }""",
    )

    record = build_citation_records(project)[0]

    assert record.cited_arxiv_id == "2401.12345"
    assert record.cited_version == "v6"


def test_ignores_commented_citations(project_factory):
    project = project_factory(
        body="% \\cite{hidden}\n\\cite{visible}",
        bib="@article{visible, arxiv={2401.12345}}",
    )

    assert [use.key for use in extract_citation_uses(project)] == ["visible"]


def test_marks_missing_bibliography_keys(project_factory):
    project = project_factory(
        body=r"\cite{missing}",
        bib="@article{other, arxiv={2401.12345}}",
    )

    record = build_citation_records(project)[0]

    assert record.resolution_status == "missing_bib_entry"
    assert record.bib_file is None
    assert record.bib_entry_type is None


def test_marks_doi_only_entries_as_unsupported(project_factory):
    project = project_factory(
        body=r"\cite{doi-only}",
        bib="@article{doi-only, doi={10.1000/example}}",
    )

    record = build_citation_records(project)[0]

    assert record.resolution_status == "unsupported_identifier"
    assert record.bib_entry_type == "article"


def test_emits_a_record_per_duplicate_citation_use(project_factory):
    project = project_factory(
        body=r"\cite{target}\citet{target}",
        bib="@article{target, arxiv={2401.12345}}",
    )

    records = build_citation_records(project)

    assert [(record.citation_key, record.command) for record in records] == [
        ("target", "cite"),
        ("target", "citet"),
    ]


def test_records_source_file_and_document_position(project_factory):
    project = project_factory(
        body=r"\input{sections/cited}",
        bib="@article{target, arxiv={2401.12345}}",
        extra_sources={"sections/cited.tex": "text \\cite{target}"},
    )

    use = extract_citation_uses(project)[0]
    record = build_citation_records(project)[0]

    assert use.source_file == "sections/cited.tex"
    assert use.position == project.text.index(r"\cite{target}")
    assert record.source_file == "sections/cited.tex"


def test_rejects_conflicting_duplicate_bibliography_entries(project_factory):
    project = project_factory(
        body=r"\cite{target}",
        bib="@article{target, arxiv={2401.12345}}",
        bibliography="first.bib",
    )
    second = project.project_root / "second.bib"
    second.write_text("@article{target, arxiv={2401.12346}}", encoding="utf-8")
    main = project.root_file
    main.write_text(main.read_text(encoding="utf-8") + r"\bibliography{second}", encoding="utf-8")
    project = load_project(main)

    with pytest.raises(ValueError, match="Conflicting bibliography entries.*target"):
        build_citation_records(project)


def test_accepts_identical_duplicate_bibliography_entries_in_first_file_order(
    project_factory,
):
    project = project_factory(
        body=r"\cite{target}",
        bib="@article{target, arxiv={2401.12345v2}}",
        bibliography="first.bib",
    )
    second = project.project_root / "second.bib"
    second.write_text(
        "@article{target, arxiv={2401.12345v2}}",
        encoding="utf-8",
    )
    main = project.root_file
    main.write_text(
        main.read_text(encoding="utf-8") + r"\bibliography{second}",
        encoding="utf-8",
    )

    record = build_citation_records(load_project(main))[0]

    assert record.bib_file == "first.bib"
    assert (record.cited_arxiv_id, record.cited_version) == ("2401.12345", "v2")


def test_malformed_bibliography_raises_safe_error_with_relative_path(
    project_factory,
):
    project = project_factory(
        body=r"\cite{broken}",
        bib="@article{broken, title = {unterminated",
    )

    with pytest.raises(BibliographyParseError) as caught:
        build_citation_records(project)

    assert str(caught.value) == "Could not parse bibliography: refs.bib"
    assert str(project.project_root) not in str(caught.value)
