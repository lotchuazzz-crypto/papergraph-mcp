import gzip
import io
import tarfile
from pathlib import Path

import pytest

from papergraph.archive import (
    ArchiveLimitError,
    UnsupportedArchiveError,
    UnsafeArchiveError,
    extract_source_package,
)


def make_tar(
    path: Path,
    members: list[tuple[tarfile.TarInfo, bytes]],
    mode: str = "w",
) -> None:
    with tarfile.open(path, mode) as archive:
        for info, content in members:
            archive.addfile(info, io.BytesIO(content) if info.isfile() else None)


def regular_member(name: str, content: bytes) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    return info, content


@pytest.mark.parametrize("mode,suffix", [("w", ".tar"), ("w:gz", ".tar.gz")])
def test_extracts_tar_sources(
    tmp_path: Path,
    mode: str,
    suffix: str,
):
    source = tmp_path / f"source{suffix}"
    destination = tmp_path / "project"
    make_tar(
        source,
        [
            regular_member("main.tex", b"MAIN"),
            regular_member("sections/proof.tex", b"PROOF"),
        ],
        mode,
    )

    extract_source_package(source, destination)

    assert (destination / "main.tex").read_bytes() == b"MAIN"
    assert (destination / "sections" / "proof.tex").read_bytes() == b"PROOF"


@pytest.mark.parametrize(
    "member_name",
    [
        "/absolute.tex",
        "../escape.tex",
        "nested/../../escape.tex",
        "..\\escape.tex",
        "C:/escape.tex",
        "C:\\escape.tex",
    ],
)
def test_rejects_unsafe_tar_paths(tmp_path: Path, member_name: str):
    source = tmp_path / "source.tar"
    destination = tmp_path / "project"
    make_tar(source, [regular_member(member_name, b"BAD")])

    with pytest.raises(UnsafeArchiveError):
        extract_source_package(source, destination)

    assert not (tmp_path / "escape.tex").exists()


@pytest.mark.parametrize(
    "member_type",
    [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE],
)
def test_rejects_links_and_special_members(
    tmp_path: Path,
    member_type: bytes,
):
    source = tmp_path / "source.tar"
    destination = tmp_path / "project"
    info = tarfile.TarInfo("unsafe")
    info.type = member_type
    info.linkname = "main.tex"
    make_tar(source, [(info, b"")])

    with pytest.raises(UnsafeArchiveError):
        extract_source_package(source, destination)


def test_enforces_member_limit(tmp_path: Path):
    source = tmp_path / "source.tar"
    destination = tmp_path / "project"
    make_tar(
        source,
        [regular_member(f"{index}.tex", b"x") for index in range(3)],
    )

    with pytest.raises(ArchiveLimitError, match="members"):
        extract_source_package(source, destination, max_members=2)


def test_enforces_extracted_size_limit(tmp_path: Path):
    source = tmp_path / "source.tar"
    destination = tmp_path / "project"
    make_tar(source, [regular_member("main.tex", b"12345")])

    with pytest.raises(ArchiveLimitError, match="size"):
        extract_source_package(source, destination, max_bytes=4)


def test_extracts_single_file_gzip_as_main_tex(tmp_path: Path):
    source = tmp_path / "source.gz"
    destination = tmp_path / "project"
    source.write_bytes(gzip.compress(b"\\documentclass{article}"))

    extract_source_package(source, destination)

    assert (destination / "main.tex").read_bytes() == b"\\documentclass{article}"


def test_extracts_plain_tex_as_main_tex(tmp_path: Path):
    source = tmp_path / "source"
    destination = tmp_path / "project"
    source.write_bytes(b"\\documentclass{article}\n\\begin{document}\nHello")

    extract_source_package(source, destination)

    assert (destination / "main.tex").read_bytes() == source.read_bytes()


@pytest.mark.parametrize(
    "payload",
    [b"", b"PK\x03\x04not-a-supported-zip", b"\x00\x01\x02binary"],
)
def test_rejects_unsupported_source_packages(tmp_path: Path, payload: bytes):
    source = tmp_path / "source"
    destination = tmp_path / "project"
    source.write_bytes(payload)

    with pytest.raises(UnsupportedArchiveError):
        extract_source_package(source, destination)


def test_enforces_single_file_gzip_size_limit(tmp_path: Path):
    source = tmp_path / "source.gz"
    destination = tmp_path / "project"
    source.write_bytes(gzip.compress(b"\\documentclass{article}"))

    with pytest.raises(ArchiveLimitError, match="size"):
        extract_source_package(source, destination, max_bytes=5)


def test_failure_does_not_leave_partial_destination(tmp_path: Path):
    source = tmp_path / "source.tar"
    destination = tmp_path / "project"
    make_tar(
        source,
        [
            regular_member("safe.tex", b"SAFE"),
            regular_member("../escape.tex", b"BAD"),
        ],
    )

    with pytest.raises(UnsafeArchiveError):
        extract_source_package(source, destination)

    assert not destination.exists()
