"""Download and prepare arXiv source projects."""

from __future__ import annotations

import re
from pathlib import Path

import httpx


ARXIV_SOURCE_BASE = "https://export.arxiv.org/e-print"
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
_USER_AGENT = "PaperGraph/0.3 (+https://github.com/lotchuazzz-crypto/papergraph-mcp)"
_MODERN_ID_RE = re.compile(r"\d{4}\.\d{4,5}(?:v[1-9]\d*)?")
_LEGACY_ID_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9.-]*/\d{7}(?:v[1-9]\d*)?"
)
_HTTP_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)


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
