"""Download and prepare arXiv source projects."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx

from papergraph.archive import (
    ArchiveError,
    ArchiveLimitError,
    UnsafeArchiveError,
    UnsupportedArchiveError,
    extract_source_package,
)
from papergraph.loader import _is_commented


ARXIV_SOURCE_BASE = "https://export.arxiv.org/e-print"
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
_USER_AGENT = "PaperGraph/0.4.4 (+https://github.com/lotchuazzz-crypto/papergraph-mcp)"
_MODERN_ID_RE = re.compile(r"\d{4}\.\d{4,5}(?:v[1-9]\d*)?")
_LEGACY_ID_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9.-]*/\d{7}(?:v[1-9]\d*)?"
)
_ARXIV_ID_SEARCH_RE = re.compile(
    r"(?<![A-Za-z0-9./:-])(?:arXiv:)?"
    r"(\d{4}\.\d{4,5}(?:v[1-9]\d*)?|[A-Za-z][A-Za-z0-9.-]*/\d{7}(?:v[1-9]\d*)?)"
    r"(?![A-Za-z0-9./-])",
    re.IGNORECASE,
)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_URL_RE = re.compile(r"https?://[^\s<>)\]]+")
_ARXIV_URL_HOSTS = {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}
_ARXIV_URL_PREFIXES = {"/abs/", "/pdf/"}
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")
_ROOT_COMMAND_READ_LIMIT = 1024 * 1024
_DOCUMENTCLASS_RE = re.compile(r"\\documentclass\b")
_BEGIN_DOCUMENT_RE = re.compile(r"\\begin\s*\{document\}")
_PREFERRED_MAIN_NAMES = ("main.tex", "paper.tex", "manuscript.tex")


class ArxivImportError(Exception):
    """Base error for arXiv imports."""


class InvalidArxivIdError(ArxivImportError):
    """The caller supplied an unsupported arXiv identifier."""


class ArxivDownloadError(ArxivImportError):
    """The arXiv source response could not be downloaded safely."""


class ArxivCacheError(ArxivImportError):
    """A persistent source cache entry is invalid or unavailable."""


class MainFileSelectionError(ArxivImportError):
    """A root LaTeX document could not be selected."""


class ArxivArchiveError(ArxivImportError):
    """The downloaded source package cannot be extracted safely."""


@dataclass(frozen=True, slots=True)
class ArxivProject:
    arxiv_id: str
    project_dir: Path
    main_file: Path
    cached: bool


def normalize_arxiv_id(value: str) -> str:
    """Validate and return an arXiv identifier without its optional prefix."""

    if not isinstance(value, str):
        raise InvalidArxivIdError("arXiv identifier must be text")
    normalized = value.strip()
    if normalized[:6].lower() == "arxiv:":
        normalized = normalized[6:]
    if not (
        _MODERN_ID_RE.fullmatch(normalized)
        or _LEGACY_ID_RE.fullmatch(normalized)
    ):
        raise InvalidArxivIdError(f"Invalid arXiv identifier: {value!r}")
    return normalized


def extract_arxiv_id_from_url(url: str) -> str:
    """Extract and validate an arXiv identifier from a supported arXiv URL."""

    if not isinstance(url, str):
        raise InvalidArxivIdError("arXiv URL must be text")
    parsed = urlparse(url.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.netloc.lower() not in _ARXIV_URL_HOSTS
    ):
        raise InvalidArxivIdError(f"Unsupported arXiv URL: {url!r}")

    path = parsed.path.rstrip("/")
    for prefix in _ARXIV_URL_PREFIXES:
        if path.startswith(prefix):
            candidate = path[len(prefix):]
            if prefix == "/pdf/" and candidate.endswith(".pdf"):
                candidate = candidate[:-4]
            return normalize_arxiv_id(candidate)

    raise InvalidArxivIdError(f"Unsupported arXiv URL: {url!r}")


def validate_arxiv_input(
    text_id: str | None = None,
    url: str | None = None,
) -> dict:
    """Normalize text and URL arXiv inputs and return the safe next action."""

    normalized_text_id: str | None = None
    normalized_url_id: str | None = None
    errors: list[str] = []

    if text_id is not None:
        try:
            normalized_text_id = normalize_arxiv_id(text_id)
        except InvalidArxivIdError as exc:
            errors.append(str(exc))

    if url is not None:
        try:
            normalized_url_id = extract_arxiv_id_from_url(url)
        except InvalidArxivIdError as exc:
            errors.append(str(exc))

    if errors or (normalized_text_id is None and normalized_url_id is None):
        if not errors:
            errors.append("Provide an arXiv text ID, an arXiv URL, or both.")
        return {
            "text_id": text_id,
            "url": url,
            "normalized_text_id": normalized_text_id,
            "normalized_url_id": normalized_url_id,
            "status": "invalid",
            "action": "ask_user_to_choose",
            "selected_id": None,
            "message": (
                "The arXiv input is invalid. Ask the user for one supported "
                "arXiv ID or URL before loading a paper."
            ),
            "errors": errors,
        }

    if normalized_text_id is not None and normalized_url_id is not None:
        if normalized_text_id != normalized_url_id:
            return {
                "text_id": text_id,
                "url": url,
                "normalized_text_id": normalized_text_id,
                "normalized_url_id": normalized_url_id,
                "status": "conflict",
                "action": "ask_user_to_choose",
                "selected_id": None,
                "message": (
                    "The text arXiv ID and arXiv URL identify different "
                    "papers. Ask the user which one to analyze before "
                    "calling load_arxiv_paper."
                ),
                "errors": [],
            }
        return {
            "text_id": text_id,
            "url": url,
            "normalized_text_id": normalized_text_id,
            "normalized_url_id": normalized_url_id,
            "status": "match",
            "action": "safe_to_load",
            "selected_id": normalized_text_id,
            "message": (
                "The text arXiv ID and arXiv URL identify the same paper. "
                f"It is safe to load {normalized_text_id}."
            ),
            "errors": [],
        }

    selected_id = normalized_text_id or normalized_url_id
    return {
        "text_id": text_id,
        "url": url,
        "normalized_text_id": normalized_text_id,
        "normalized_url_id": normalized_url_id,
        "status": "single_input",
        "action": "safe_to_load",
        "selected_id": selected_id,
        "message": f"One arXiv input was provided. It is safe to load {selected_id}.",
        "errors": [],
    }


def _candidate(kind: str, raw: str, normalized_id: str) -> dict:
    return {
        "kind": kind,
        "raw": raw,
        "normalized_id": normalized_id,
    }


def _span_is_consumed(span: tuple[int, int], consumed_spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start >= used_start and end <= used_end for used_start, used_end in consumed_spans)


def _append_unique_normalized_id(normalized_ids: list[str], normalized_id: str) -> None:
    if normalized_id not in normalized_ids:
        normalized_ids.append(normalized_id)


def _extract_request_candidates(value: str) -> list[dict]:
    candidates: list[dict] = []
    consumed_spans: list[tuple[int, int]] = []

    for match in _MARKDOWN_LINK_RE.finditer(value):
        consumed_spans.append(match.span())
        text, url = match.groups()
        try:
            candidates.append(
                _candidate("markdown_text", text, normalize_arxiv_id(text))
            )
        except InvalidArxivIdError:
            pass
        try:
            candidates.append(
                _candidate("markdown_url", url, extract_arxiv_id_from_url(url))
            )
        except InvalidArxivIdError:
            pass

    for match in _URL_RE.finditer(value):
        if _span_is_consumed(match.span(), consumed_spans):
            continue
        consumed_spans.append(match.span())
        url = match.group(0)
        try:
            candidates.append(
                _candidate("plain_url", url, extract_arxiv_id_from_url(url))
            )
        except InvalidArxivIdError:
            pass

    for match in _ARXIV_ID_SEARCH_RE.finditer(value):
        if _span_is_consumed(match.span(), consumed_spans):
            continue
        raw = match.group(0)
        try:
            candidates.append(_candidate("bare_id", raw, normalize_arxiv_id(raw)))
        except InvalidArxivIdError:
            pass

    return candidates


def validate_arxiv_request(input: str) -> dict:
    """Extract arXiv IDs from a raw user request and return the safe next action."""

    if not isinstance(input, str):
        return {
            "input": input,
            "candidates": [],
            "normalized_ids": [],
            "status": "invalid",
            "action": "ask_user_to_choose",
            "selected_id": None,
            "message": (
                "The arXiv request must be text. Ask the user for one supported "
                "arXiv ID, URL, or Markdown link before loading a paper."
            ),
            "errors": ["arXiv request must be text."],
        }

    candidates = _extract_request_candidates(input)
    normalized_ids: list[str] = []
    for item in candidates:
        _append_unique_normalized_id(normalized_ids, item["normalized_id"])

    if not normalized_ids:
        return {
            "input": input,
            "candidates": candidates,
            "normalized_ids": normalized_ids,
            "status": "invalid",
            "action": "ask_user_to_choose",
            "selected_id": None,
            "message": (
                "No supported arXiv ID or arXiv URL was found. Ask the user for "
                "one supported arXiv ID, URL, or Markdown arXiv link."
            ),
            "errors": ["Provide one arXiv ID, arXiv URL, or Markdown arXiv link."],
        }

    if len(normalized_ids) > 1:
        return {
            "input": input,
            "candidates": candidates,
            "normalized_ids": normalized_ids,
            "status": "conflict",
            "action": "ask_user_to_choose",
            "selected_id": None,
            "message": (
                "The request contains multiple different arXiv IDs. Ask the user "
                "which paper to analyze before loading anything."
            ),
            "errors": [],
        }

    selected_id = normalized_ids[0]
    status = "match" if len(candidates) > 1 else "single_input"
    return {
        "input": input,
        "candidates": candidates,
        "normalized_ids": normalized_ids,
        "status": status,
        "action": "safe_to_load",
        "selected_id": selected_id,
        "message": f"The request identifies one paper. It is safe to load {selected_id}.",
        "errors": [],
    }


def _write_response(
    response: httpx.Response,
    destination: Path,
    *,
    arxiv_id: str,
    max_bytes: int,
) -> None:
    if not response.is_success:
        raise ArxivDownloadError(
            f"arXiv source download failed for {arxiv_id} "
            f"with HTTP {response.status_code}"
        )

    declared_length = response.headers.get("content-length")
    if declared_length is not None:
        try:
            declared_bytes = int(declared_length)
        except ValueError as exc:
            raise ArxivDownloadError(
                f"arXiv returned an invalid source length for {arxiv_id}"
            ) from exc
        if declared_bytes > max_bytes:
            raise ArxivDownloadError(
                f"arXiv source for {arxiv_id} exceeds the download size limit"
            )

    received = 0
    with destination.open("wb") as output:
        for chunk in response.iter_bytes():
            received += len(chunk)
            if received > max_bytes:
                raise ArxivDownloadError(
                    f"arXiv source for {arxiv_id} exceeds the download size limit"
                )
            output.write(chunk)
    if received == 0:
        raise ArxivDownloadError(f"arXiv returned an empty source for {arxiv_id}")


def download_arxiv_source(
    arxiv_id: str,
    destination: Path,
    *,
    client: httpx.Client | None = None,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> None:
    """Stream one source response from arXiv's fixed e-print endpoint."""

    normalized_id = normalize_arxiv_id(arxiv_id)
    if max_bytes < 1:
        raise ValueError("Download size limit must be positive")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"{ARXIV_SOURCE_BASE}/{normalized_id}"
    owned_client = client is None
    active_client = client or httpx.Client()
    try:
        with active_client.stream(
            "GET",
            url,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=_HTTP_TIMEOUT,
        ) as response:
            _write_response(
                response,
                destination,
                arxiv_id=normalized_id,
                max_bytes=max_bytes,
            )
    except ArxivDownloadError:
        destination.unlink(missing_ok=True)
        raise
    except httpx.HTTPError as exc:
        destination.unlink(missing_ok=True)
        raise ArxivDownloadError(
            f"Could not download arXiv source for {normalized_id}"
        ) from exc
    finally:
        if owned_client:
            active_client.close()


def _safe_relative_path(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or _DRIVE_PREFIX_RE.match(normalized):
        raise MainFileSelectionError(f"Unsafe main_file path: {value}")
    relative = PurePosixPath(normalized)
    if not normalized or ".." in relative.parts:
        raise MainFileSelectionError(f"Unsafe main_file path: {value}")
    return relative


def _is_regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _has_uncommented_match(pattern: re.Pattern[str], text: str) -> bool:
    return any(not _is_commented(text, match.start()) for match in pattern.finditer(text))


def _is_root_document(path: Path) -> bool:
    with path.open("rb") as source:
        text = source.read(_ROOT_COMMAND_READ_LIMIT).decode(
            "utf-8",
            errors="replace",
        )
    return _has_uncommented_match(
        _DOCUMENTCLASS_RE,
        text,
    ) and _has_uncommented_match(_BEGIN_DOCUMENT_RE, text)


def _display_paths(root: Path, paths: list[Path]) -> str:
    return ", ".join(
        sorted(path.relative_to(root).as_posix() for path in paths)
    )


def select_main_file(
    project_root: Path,
    main_file: str | None = None,
) -> Path:
    """Select or validate the root LaTeX file in an extracted project."""

    root = Path(project_root).resolve()
    if not root.is_dir():
        raise MainFileSelectionError("Extracted arXiv project is not a directory")

    if main_file is not None:
        relative = _safe_relative_path(main_file)
        if relative.suffix.lower() != ".tex":
            raise MainFileSelectionError("main_file must name a .tex file")
        selected = root.joinpath(*relative.parts).resolve()
        if not selected.is_relative_to(root) or not _is_regular_file(selected):
            raise MainFileSelectionError(f"main_file does not exist: {main_file}")
        return selected

    tex_files: list[Path] = []
    for path in root.rglob("*.tex"):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        resolved = path.resolve()
        if resolved.is_relative_to(root) and _is_regular_file(path):
            tex_files.append(resolved)

    candidates = [path for path in tex_files if _is_root_document(path)]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        for preferred in _PREFERRED_MAIN_NAMES:
            matches = [
                path for path in candidates if path.name.lower() == preferred
            ]
            if len(matches) == 1:
                return matches[0]
        raise MainFileSelectionError(
            "Multiple root LaTeX files found: "
            f"{_display_paths(root, candidates)}. "
            "Pass main_file to choose one."
        )

    if tex_files:
        detail = f" Discovered: {_display_paths(root, tex_files)}."
    else:
        detail = " No .tex files were discovered."
    raise MainFileSelectionError(f"No root LaTeX file found.{detail}")


def default_cache_root() -> Path:
    """Return the platform-appropriate persistent PaperGraph cache root."""

    if local_app_data := os.environ.get("LOCALAPPDATA"):
        return Path(local_app_data) / "papergraph" / "arxiv"
    if xdg_cache_home := os.environ.get("XDG_CACHE_HOME"):
        return Path(xdg_cache_home) / "papergraph" / "arxiv"
    return Path.home() / ".cache" / "papergraph" / "arxiv"


def _cache_key(arxiv_id: str) -> str:
    return arxiv_id.replace("/", "__")


def _read_cached_main(entry: Path, arxiv_id: str) -> Path | None:
    if not entry.is_dir() or entry.is_symlink():
        return None
    manifest_path = entry / ".papergraph.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("arxiv_id") != arxiv_id:
            return None
        stored_main = manifest.get("main_file")
        if not isinstance(stored_main, str):
            return None
        return select_main_file(entry, stored_main)
    except (OSError, json.JSONDecodeError, MainFileSelectionError):
        return None


def _translate_archive_error(arxiv_id: str, error: ArchiveError) -> ArxivArchiveError:
    if isinstance(error, UnsafeArchiveError):
        reason = "contains unsafe archive content"
    elif isinstance(error, ArchiveLimitError):
        reason = "exceeds archive safety limits"
    elif isinstance(error, UnsupportedArchiveError):
        reason = "uses an unsupported source format"
    else:
        reason = "could not be extracted"
    return ArxivArchiveError(f"arXiv source for {arxiv_id} {reason}")


def _remove_cache_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _publish_cache_entry(project: Path, entry: Path) -> None:
    backup: Path | None = None
    if entry.exists():
        backup = entry.parent / f".{entry.name}.backup-{uuid.uuid4().hex}"
        entry.rename(backup)
    try:
        project.rename(entry)
    except Exception:
        if backup is not None and backup.exists() and not entry.exists():
            backup.rename(entry)
        raise
    else:
        if backup is not None:
            _remove_cache_path(backup)


def prepare_arxiv_project(
    arxiv_id: str,
    main_file: str | None = None,
    refresh: bool = False,
    *,
    cache_root: Path | None = None,
    client: httpx.Client | None = None,
) -> ArxivProject:
    """Download, safely extract, select, and cache one arXiv source project."""

    normalized_id = normalize_arxiv_id(arxiv_id)
    root = Path(cache_root) if cache_root is not None else default_cache_root()
    root = root.expanduser().resolve()
    entry = root / _cache_key(normalized_id)

    cached_main = _read_cached_main(entry, normalized_id)
    if cached_main is not None and not refresh:
        selected = select_main_file(entry, main_file) if main_file else cached_main
        return ArxivProject(normalized_id, entry, selected, True)

    try:
        root.mkdir(parents=True, exist_ok=True)
        work = Path(
            tempfile.mkdtemp(
                prefix=f".{entry.name}-",
                dir=root,
            )
        )
    except OSError as exc:
        raise ArxivCacheError(
            f"Could not create the arXiv cache for {normalized_id}"
        ) from exc

    try:
        source = work / "source-package"
        project = work / "project"
        download_arxiv_source(normalized_id, source, client=client)
        try:
            extract_source_package(source, project)
        except ArchiveError as exc:
            raise _translate_archive_error(normalized_id, exc) from exc

        selected = select_main_file(project, main_file)
        selected_relative = selected.relative_to(project).as_posix()
        manifest = {
            "arxiv_id": normalized_id,
            "main_file": selected_relative,
        }
        (project / ".papergraph.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _publish_cache_entry(project, entry)
        return ArxivProject(
            normalized_id,
            entry,
            entry.joinpath(*PurePosixPath(selected_relative).parts),
            False,
        )
    except ArxivImportError:
        raise
    except OSError as exc:
        raise ArxivCacheError(
            f"Could not update the arXiv cache for {normalized_id}"
        ) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)
