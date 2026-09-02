from pathlib import Path

import httpx
import pytest

from papergraph.arxiv import (
    ArxivDownloadError,
    InvalidArxivIdError,
    MainFileSelectionError,
    download_arxiv_source,
    normalize_arxiv_id,
    select_main_file,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2401.12345", "2401.12345"),
        ("2401.12345v2", "2401.12345v2"),
        (" arXiv:2401.12345 ", "2401.12345"),
        ("ARXIV:math/0307200", "math/0307200"),
        ("hep-th/9901001v3", "hep-th/9901001v3"),
    ],
)
def test_normalizes_supported_arxiv_ids(value: str, expected: str):
    assert normalize_arxiv_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "https://arxiv.org/abs/2401.12345",
        "2401. 12345",
        "../2401.12345",
        "/2401.12345",
        "2401.123",
        "2401.123456",
        "2401.12345v0",
        "math/030720",
        "math//0307200",
        "arXiv:arXiv:2401.12345",
    ],
)
def test_rejects_invalid_arxiv_ids(value: str):
    with pytest.raises(InvalidArxivIdError):
        normalize_arxiv_id(value)


def test_download_uses_fixed_endpoint_headers_redirects_and_streaming(
    tmp_path: Path,
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(302, headers={"Location": "/e-print/2401.12345/source"})
        return httpx.Response(200, content=b"source body")

    destination = tmp_path / "source"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        download_arxiv_source("arXiv:2401.12345", destination, client=client)

    assert [str(request.url) for request in requests] == [
        "https://export.arxiv.org/e-print/2401.12345",
        "https://export.arxiv.org/e-print/2401.12345/source",
    ]
    assert requests[0].headers["user-agent"].startswith("PaperGraph/")
    assert destination.read_bytes() == b"source body"


def test_download_rejects_declared_oversize(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": "6"}, content=b"123456")

    destination = tmp_path / "source"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ArxivDownloadError, match="1001.00001"):
            download_arxiv_source(
                "1001.00001",
                destination,
                client=client,
                max_bytes=5,
            )

    assert not destination.exists()


def test_download_rejects_observed_oversize(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"123456")

    destination = tmp_path / "source"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ArxivDownloadError, match="size limit"):
            download_arxiv_source(
                "1001.00001",
                destination,
                client=client,
                max_bytes=5,
            )

    assert not destination.exists()


def test_download_rejects_empty_response(tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ArxivDownloadError, match="empty"):
            download_arxiv_source("1001.00001", tmp_path / "source", client=client)


def test_download_translates_http_status_without_response_body(tmp_path: Path):
    secret = "server-secret-that-must-not-leak"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text=secret)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ArxivDownloadError) as caught:
            download_arxiv_source("1001.00001", tmp_path / "source", client=client)

    assert "1001.00001" in str(caught.value)
    assert secret not in str(caught.value)


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_download_translates_network_failures(
    tmp_path: Path,
    error_type: type[httpx.HTTPError],
):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_type("private network detail", request=request)

    destination = tmp_path / "private" / "source"
    destination.parent.mkdir()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ArxivDownloadError) as caught:
            download_arxiv_source("1001.00001", destination, client=client)

    message = str(caught.value)
    assert "1001.00001" in message
    assert "private network detail" not in message
    assert str(destination) not in message
    assert not destination.exists()


def write_tex(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def document_text(body: str = "") -> str:
    return f"\\documentclass{{article}}\n\\begin{{document}}\n{body}"


def test_selects_only_root_document(tmp_path: Path):
    root = tmp_path / "project"
    expected = write_tex(root / "article.tex", document_text())
    write_tex(root / "section.tex", "Section only")

    assert select_main_file(root) == expected.resolve()


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["draft.tex", "main.tex", "paper.tex"], "main.tex"),
        (["draft.tex", "paper.tex", "manuscript.tex"], "paper.tex"),
        (["draft.tex", "manuscript.tex"], "manuscript.tex"),
    ],
)
def test_prefers_conventional_unique_basename(
    tmp_path: Path,
    names: list[str],
    expected: str,
):
    root = tmp_path / "project"
    for name in names:
        write_tex(root / name, document_text(name))

    assert select_main_file(root) == (root / expected).resolve()


def test_reports_sorted_ambiguous_candidates(tmp_path: Path):
    root = tmp_path / "project"
    write_tex(root / "zeta.tex", document_text())
    write_tex(root / "parts" / "alpha.tex", document_text())

    with pytest.raises(MainFileSelectionError) as caught:
        select_main_file(root)

    message = str(caught.value)
    assert "parts/alpha.tex" in message
    assert "zeta.tex" in message
    assert message.index("parts/alpha.tex") < message.index("zeta.tex")


def test_reports_discovered_tex_files_when_no_candidate(tmp_path: Path):
    root = tmp_path / "project"
    write_tex(root / "sections" / "body.tex", "Body")

    with pytest.raises(MainFileSelectionError, match="sections/body.tex"):
        select_main_file(root)


def test_ignores_hidden_tex_candidates(tmp_path: Path):
    root = tmp_path / "project"
    expected = write_tex(root / "visible.tex", document_text())
    write_tex(root / ".hidden" / "main.tex", document_text())

    assert select_main_file(root) == expected.resolve()


def test_ignores_commented_root_commands(tmp_path: Path):
    root = tmp_path / "project"
    write_tex(
        root / "commented.tex",
        "% \\documentclass{article}\n% \\begin{document}\n",
    )

    with pytest.raises(MainFileSelectionError):
        select_main_file(root)


def test_escaped_percent_does_not_hide_root_commands(tmp_path: Path):
    root = tmp_path / "project"
    expected = write_tex(
        root / "main.tex",
        "\\% literal \\documentclass{article}\n\\begin{document}",
    )

    assert select_main_file(root) == expected.resolve()


@pytest.mark.parametrize("override", ["sections/root.tex", "sections\\root.tex"])
def test_accepts_safe_explicit_main_file(tmp_path: Path, override: str):
    root = tmp_path / "project"
    expected = write_tex(root / "sections" / "root.tex", "custom root")

    assert select_main_file(root, override) == expected.resolve()


@pytest.mark.parametrize(
    "override",
    [
        "missing.tex",
        "notes.txt",
        "../outside.tex",
        "nested/../../outside.tex",
        "/absolute.tex",
        "C:/absolute.tex",
        "C:\\absolute.tex",
    ],
)
def test_rejects_invalid_explicit_main_file(tmp_path: Path, override: str):
    root = tmp_path / "project"
    root.mkdir()
    write_tex(tmp_path / "outside.tex", document_text())
    write_tex(root / "notes.txt", "notes")

    with pytest.raises(MainFileSelectionError):
        select_main_file(root, override)
