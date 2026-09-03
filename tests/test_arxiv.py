import io
import json
import tarfile
from pathlib import Path

import httpx
import pytest

from papergraph.arxiv import (
    ArxivImportError,
    ArxivDownloadError,
    InvalidArxivIdError,
    MainFileSelectionError,
    default_cache_root,
    download_arxiv_source,
    extract_arxiv_id_from_url,
    normalize_arxiv_id,
    prepare_arxiv_project,
    select_main_file,
    validate_arxiv_input,
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


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://arxiv.org/abs/2609.01574", "2609.01574"),
        ("https://arxiv.org/abs/2609.01574v2", "2609.01574v2"),
        ("https://arxiv.org/pdf/math/0307200", "math/0307200"),
        ("https://export.arxiv.org/abs/hep-th/9901001v3", "hep-th/9901001v3"),
    ],
)
def test_extracts_arxiv_id_from_supported_urls(url: str, expected: str):
    assert extract_arxiv_id_from_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/abs/2609.01574",
        "https://arxiv.org/",
        "https://arxiv.org/abs/not-an-id",
        "not a url",
    ],
)
def test_rejects_unsupported_arxiv_urls(url: str):
    with pytest.raises(InvalidArxivIdError):
        extract_arxiv_id_from_url(url)


def test_validate_arxiv_input_allows_matching_text_and_url():
    result = validate_arxiv_input(
        text_id="arXiv:2609.01574",
        url="https://arxiv.org/abs/2609.01574",
    )

    assert result == {
        "text_id": "arXiv:2609.01574",
        "url": "https://arxiv.org/abs/2609.01574",
        "normalized_text_id": "2609.01574",
        "normalized_url_id": "2609.01574",
        "status": "match",
        "action": "safe_to_load",
        "selected_id": "2609.01574",
        "message": "The text arXiv ID and arXiv URL identify the same paper. It is safe to load 2609.01574.",
        "errors": [],
    }


def test_validate_arxiv_input_stops_on_conflict():
    result = validate_arxiv_input(
        text_id="math/0307200",
        url="https://arxiv.org/abs/2609.01574",
    )

    assert result["normalized_text_id"] == "math/0307200"
    assert result["normalized_url_id"] == "2609.01574"
    assert result["status"] == "conflict"
    assert result["action"] == "ask_user_to_choose"
    assert result["selected_id"] is None
    assert "ask the user" in result["message"].lower()
    assert result["errors"] == []


@pytest.mark.parametrize(
    ("text_id", "url", "selected"),
    [
        ("math/0307200", None, "math/0307200"),
        (None, "https://arxiv.org/abs/2609.01574", "2609.01574"),
    ],
)
def test_validate_arxiv_input_accepts_single_input(text_id, url, selected):
    result = validate_arxiv_input(text_id=text_id, url=url)

    assert result["status"] == "single_input"
    assert result["action"] == "safe_to_load"
    assert result["selected_id"] == selected
    assert result["errors"] == []


def test_validate_arxiv_input_reports_invalid_inputs_without_selection():
    result = validate_arxiv_input(
        text_id="not-an-id",
        url="https://example.com/abs/2609.01574",
    )

    assert result["status"] == "invalid"
    assert result["action"] == "ask_user_to_choose"
    assert result["selected_id"] is None
    assert result["normalized_text_id"] is None
    assert result["normalized_url_id"] is None
    assert len(result["errors"]) == 2


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


def source_tar(files: dict[str, str]) -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        for name, content in files.items():
            encoded = content.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(encoded)
            archive.addfile(info, io.BytesIO(encoded))
    return payload.getvalue()


def test_default_cache_root_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    local = tmp_path / "local"
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg))
    assert default_cache_root() == local / "papergraph" / "arxiv"

    monkeypatch.delenv("LOCALAPPDATA")
    assert default_cache_root() == xdg / "papergraph" / "arxiv"

    monkeypatch.delenv("XDG_CACHE_HOME")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert default_cache_root() == tmp_path / "home" / ".cache" / "papergraph" / "arxiv"


def test_prepares_and_manifests_arxiv_project(tmp_path: Path):
    payload = source_tar(
        {
            "main.tex": document_text("\\input{sections/proof}"),
            "sections/proof.tex": "Proof",
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    cache_root = tmp_path / "cache"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        project = prepare_arxiv_project(
            "arXiv:2401.12345",
            cache_root=cache_root,
            client=client,
        )

    assert project.arxiv_id == "2401.12345"
    assert project.project_dir == cache_root / "2401.12345"
    assert project.main_file == project.project_dir / "main.tex"
    assert project.cached is False
    assert (project.project_dir / "sections" / "proof.tex").read_text() == "Proof"
    assert json.loads((project.project_dir / ".papergraph.json").read_text()) == {
        "arxiv_id": "2401.12345",
        "main_file": "main.tex",
    }


def test_cache_hit_avoids_second_download(tmp_path: Path):
    calls = 0
    payload = source_tar({"main.tex": document_text()})

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise AssertionError("cache hit attempted a network request")
        return httpx.Response(200, content=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = prepare_arxiv_project("2401.12345", cache_root=tmp_path, client=client)
        second = prepare_arxiv_project("2401.12345", cache_root=tmp_path, client=client)

    assert first.cached is False
    assert second.cached is True
    assert second.main_file == first.main_file
    assert calls == 1


def test_legacy_id_uses_filesystem_safe_cache_name(tmp_path: Path):
    payload = source_tar({"main.tex": document_text()})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        project = prepare_arxiv_project(
            "math/0307200",
            cache_root=tmp_path,
            client=client,
        )

    assert project.project_dir.name == "math__0307200"


def test_successful_refresh_replaces_cache(tmp_path: Path):
    payloads = iter(
        [
            source_tar({"main.tex": document_text("OLD")}),
            source_tar({"main.tex": document_text("NEW")}),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=next(payloads))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        prepare_arxiv_project("2401.12345", cache_root=tmp_path, client=client)
        refreshed = prepare_arxiv_project(
            "2401.12345",
            refresh=True,
            cache_root=tmp_path,
            client=client,
        )

    assert refreshed.cached is False
    assert "NEW" in refreshed.main_file.read_text()
    assert "OLD" not in refreshed.main_file.read_text()


def test_failed_refresh_preserves_valid_cache_and_cleans_temporary_data(
    tmp_path: Path,
):
    calls = 0
    original = source_tar({"main.tex": document_text("ORIGINAL")})

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, content=original)
        return httpx.Response(503, text="failure")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        project = prepare_arxiv_project("2401.12345", cache_root=tmp_path, client=client)
        before = project.main_file.read_bytes()
        with pytest.raises(ArxivDownloadError):
            prepare_arxiv_project(
                "2401.12345",
                refresh=True,
                cache_root=tmp_path,
                client=client,
            )

    assert project.main_file.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["2401.12345"]


@pytest.mark.parametrize(
    "manifest",
    [
        "not json",
        json.dumps({"arxiv_id": "9999.99999", "main_file": "main.tex"}),
        json.dumps({"arxiv_id": "2401.12345", "main_file": "../escape.tex"}),
        json.dumps({"arxiv_id": "2401.12345", "main_file": "missing.tex"}),
    ],
)
def test_invalid_manifest_is_rebuilt(tmp_path: Path, manifest: str):
    entry = tmp_path / "2401.12345"
    entry.mkdir()
    (entry / "main.tex").write_text(document_text("STALE"))
    (entry / ".papergraph.json").write_text(manifest)
    payload = source_tar({"main.tex": document_text("FRESH")})
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        project = prepare_arxiv_project("2401.12345", cache_root=tmp_path, client=client)

    assert calls == 1
    assert project.cached is False
    assert "FRESH" in project.main_file.read_text()


def test_non_directory_cache_entry_is_rebuilt(tmp_path: Path):
    (tmp_path / "2401.12345").write_text("invalid entry")
    payload = source_tar({"main.tex": document_text("FRESH")})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        project = prepare_arxiv_project("2401.12345", cache_root=tmp_path, client=client)

    assert project.project_dir.is_dir()
    assert "FRESH" in project.main_file.read_text()


def test_main_file_override_can_change_on_cache_hit(tmp_path: Path):
    payload = source_tar(
        {
            "first.tex": document_text("FIRST"),
            "nested/second.tex": document_text("SECOND"),
        }
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = prepare_arxiv_project(
            "2401.12345",
            main_file="first.tex",
            cache_root=tmp_path,
            client=client,
        )
        second = prepare_arxiv_project(
            "2401.12345",
            main_file="nested/second.tex",
            cache_root=tmp_path,
            client=client,
        )

    assert first.main_file.name == "first.tex"
    assert second.main_file.name == "second.tex"
    assert second.cached is True
    assert calls == 1


def test_unsafe_archive_is_translated_and_not_published(tmp_path: Path):
    payload = source_tar({"../escape.tex": "BAD"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ArxivImportError, match="unsafe"):
            prepare_arxiv_project("2401.12345", cache_root=tmp_path, client=client)

    assert not (tmp_path / "2401.12345").exists()
    assert not (tmp_path.parent / "escape.tex").exists()
