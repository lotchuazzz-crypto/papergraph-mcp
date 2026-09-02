"""Safe extraction of arXiv source responses."""

from __future__ import annotations

import gzip
import re
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


MAX_ARCHIVE_MEMBERS = 10_000
MAX_EXTRACTED_BYTES = 500 * 1024 * 1024
_COPY_CHUNK_SIZE = 1024 * 1024
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


class ArchiveError(Exception):
    """Base error for source-package extraction."""


class UnsafeArchiveError(ArchiveError):
    """The package contains an unsafe path or member type."""


class ArchiveLimitError(ArchiveError):
    """The package exceeds a configured extraction limit."""


class UnsupportedArchiveError(ArchiveError):
    """The response is not a supported arXiv source format."""


def _member_target(root: Path, member_name: str) -> Path:
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or _DRIVE_PREFIX_RE.match(normalized):
        raise UnsafeArchiveError(f"Unsafe archive path: {member_name}")

    relative = PurePosixPath(normalized)
    if ".." in relative.parts:
        raise UnsafeArchiveError(f"Unsafe archive path: {member_name}")

    target = root.joinpath(*relative.parts).resolve()
    if not target.is_relative_to(root):
        raise UnsafeArchiveError(f"Unsafe archive path: {member_name}")
    return target


def _copy_bounded(source, destination: Path, *, remaining: int) -> int:
    written = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        while chunk := source.read(_COPY_CHUNK_SIZE):
            written += len(chunk)
            if written > remaining:
                raise ArchiveLimitError("Extracted source size exceeds the limit")
            output.write(chunk)
    return written


def _extract_tar(
    source: Path,
    destination: Path,
    *,
    max_members: int,
    max_bytes: int,
) -> bool:
    try:
        archive = tarfile.open(source, mode="r:*")
    except tarfile.ReadError:
        return False

    with archive:
        members = archive.getmembers()
        if len(members) > max_members:
            raise ArchiveLimitError("Archive contains too many members")

        declared_size = 0
        targets: list[tuple[tarfile.TarInfo, Path]] = []
        for member in members:
            target = _member_target(destination, member.name)
            if member.isdir():
                targets.append((member, target))
                continue
            if not member.isfile():
                raise UnsafeArchiveError(
                    f"Unsupported archive member type: {member.name}"
                )
            if target == destination:
                raise UnsafeArchiveError(f"Unsafe archive path: {member.name}")
            declared_size += member.size
            if declared_size > max_bytes:
                raise ArchiveLimitError("Extracted source size exceeds the limit")
            targets.append((member, target))

        written = 0
        for member, target in targets:
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            member_source = archive.extractfile(member)
            if member_source is None:
                raise UnsupportedArchiveError(
                    f"Could not read archive member: {member.name}"
                )
            with member_source:
                written += _copy_bounded(
                    member_source,
                    target,
                    remaining=max_bytes - written,
                )
    return True


def _extract_gzip(source: Path, destination: Path, *, max_bytes: int) -> None:
    try:
        with gzip.open(source, "rb") as decompressed:
            _copy_bounded(
                decompressed,
                destination / "main.tex",
                remaining=max_bytes,
            )
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise UnsupportedArchiveError("Invalid gzip source package") from exc


def _extract_plain_tex(source: Path, destination: Path, *, max_bytes: int) -> None:
    size = source.stat().st_size
    if size > max_bytes:
        raise ArchiveLimitError("Extracted source size exceeds the limit")
    payload = source.read_bytes()
    if not payload or b"\x00" in payload or b"\\" not in payload:
        raise UnsupportedArchiveError("Response is not a supported source package")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedArchiveError("Response is not a text source package") from exc
    (destination / "main.tex").write_bytes(payload)


def extract_source_package(
    source: Path,
    destination: Path,
    *,
    max_members: int = MAX_ARCHIVE_MEMBERS,
    max_bytes: int = MAX_EXTRACTED_BYTES,
) -> None:
    """Extract one supported source response without publishing partial data."""

    source = Path(source)
    destination = Path(destination)
    if max_members < 1 or max_bytes < 1:
        raise ValueError("Extraction limits must be positive")
    if destination.exists():
        raise FileExistsError(f"Extraction destination already exists: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}-",
            dir=destination.parent,
        )
    )
    try:
        if not _extract_tar(
            source,
            staging,
            max_members=max_members,
            max_bytes=max_bytes,
        ):
            signature = source.read_bytes()[:4]
            if signature.startswith(b"\x1f\x8b"):
                _extract_gzip(source, staging, max_bytes=max_bytes)
            elif signature.startswith(b"PK\x03\x04"):
                raise UnsupportedArchiveError("Zip source packages are not supported")
            else:
                _extract_plain_tex(source, staging, max_bytes=max_bytes)
        staging.rename(destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
