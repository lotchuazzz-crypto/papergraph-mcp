# PyPI publication and installation

Status, checked 2026-10-04: [PyPI 1.2.0](https://pypi.org/project/papergraph-mcp/1.2.0/)
is published. The authorized, human-approved [first upload](https://github.com/lotchuazzz-crypto/papergraph-mcp/actions/runs/37119385521)
completed on 2026-10-03; [Git-free public-index acceptance](https://github.com/lotchuazzz-crypto/papergraph-mcp/actions/runs/37123289066)
passed with fresh caches. Ordinary installation now defaults to fixed PyPI 1.2.0.
The [GitHub Release](https://github.com/lotchuazzz-crypto/papergraph-mcp/releases/tag/v1.2.0)
was published on 2026-10-02. This document does not authorize another upload,
MCPVault listing changes or email.

Historical assessment: public PyPI project/JSON/simple endpoints returned 404 on
2026-10-02. That observation did not establish ownership or reserve the name;
it is not the current publication status.

## Reviewed source and artifacts

- Project: `papergraph-mcp`, first published PyPI version: `1.2.0`.
- Immutable source: tag `v1.2.0`, commit
  `60977c06217905e5c1db15fbf27aff4ca208a517`. Never move that tag.
- Build with `uv build --no-sources`. Upload candidates are
  `papergraph_mcp-1.2.0-py3-none-any.whl` and `papergraph_mcp-1.2.0.tar.gz`.
- The preparation workflow verifies the exact tag commit, checks metadata with
  Twine, prints artifact SHA-256 values and verifies installed build provenance.
  It does not upload distributions. A local preparation-commit wheel with a
  different manifest SHA is not substituted for this release build.
- Python requires >=3.10. There is no new runtime dependency or package-code change.
  The wheel includes its entry point, source manifest and MIT license; the sdist
  includes the custom Hatch build hook and source manifest.

The repository's own code is MIT licensed. PyMuPDF has separate AGPL/commercial
licensing; the project license does not replace dependency licenses. This is not
a legal compliance determination. See [PyMuPDF licensing](https://pymupdf.io/licensing).

## Installation paths

Optional Git-source installation requires Git, uv and uvx:

```text
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.2.0 papergraph-mcp --version
python scripts/check_onboarding.py --install-source git --smoke-test
```

Default PyPI installation is published and verified. It requires uv/uvx and index
access, without Git or a checkout:

```text
uvx --from papergraph-mcp==1.2.0 papergraph-mcp
uvx --from papergraph-mcp==1.2.0 papergraph-mcp --version
uvx --from papergraph-mcp==1.2.0 papergraph-mcp doctor
```

Read-only prerequisite inspection defaults to PyPI:

```text
python scripts/check_onboarding.py
python scripts/check_onboarding.py --install-source pypi
```

Add `--smoke-test` to execute the pinned version check (network/cache/environment
changes are possible); without it the checker does not download or launch.

`publication_verified` records the version-specific public-index acceptance above,
not a live index availability check. With uv/uvx available, prerequisites and
`ready_for_smoke_test` can be true without Git. Actual launch can still fail due
to network, index or host conditions; the checker reports that separately.
Repository freshness is a separate optional check and stays unverified without
a fetch. For a future unverified package version, restore the publication guard
until authorized publication and fresh-cache acceptance have succeeded.
The v1.2.0 installed doctor still recommends the Git source and emits a nonfatal
Git-context warning outside a checkout; that warning is not a failed MCP startup.
Changing installed-package behavior would require a new reviewed release.

## Actual no-Git acceptance

Post-publication public-index acceptance is separate from the local-artifact checks
below. [Run 37123289066](https://github.com/lotchuazzz-crypto/papergraph-mcp/actions/runs/37123289066) completed successfully on Linux/Python 3.12.15,
using resolved official image digest
`python@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3`.
Git executable/package absence was checked before and after bootstrap. Fresh-cache
`uvx --from papergraph-mcp==1.2.0` used the official public index, without a local
artifact. Version/doctor, stdio initialize/tools/diagnostics and generated PDF
reading passed; source commit/digest matched the original release, with
`tracked_dirty=false`. The independent verification workflow has only
`contents: read`, no publishing job, environment or OIDC permission. This validates
Linux/Python 3.12; MCPVault's actual environment remains unverified.

### Earlier wheel and sdist checks

The Windows development host has Git. Hiding its PATH is not acceptance evidence.
Local Docker/Podman availability and every actual CI result must be reported.
The CI reusable workflow `.github/workflows/pypi-preparation.yml` runs automatically
through normal PR CI and can be manually dispatched once the workflow is available.
It has only `contents: read`, no publishing job and no publishing environment.

The complete container invocation is in `scripts/check_no_git_distributions.sh`:

```sh
bash scripts/check_no_git_distributions.sh /path/to/built/distributions
```

It records the resolved digest for the official `python:3.12-slim-bookworm` image
and starts a separate fresh container for wheel and sdist. The root filesystem
and artifact/check mounts are read-only; only a tmpfs is writable. No source
checkout, Git credential, user paper or publishing permission enters the consumer.
Before installing tools, the consumer checks the original PATH, executes a Git
absence probe, checks the Debian Git package database and known executable paths.
It adds the uv virtualenv to the existing PATH without hiding system directories.
The consumer sets `UV_TOOL_DIR` inside its temporary directory so uvx can store
tool state while the root filesystem remains read-only. See the
[uv environment reference](https://docs.astral.sh/uv/reference/environment/#uv_tool_dir).

Each consumer starts with absent bootstrap/uvx caches, installs the local artifact
through uv, then tests the real `uvx --from <artifact>` entry point: CLI version,
doctor, MCP initialize, tools/list, diagnostics, generated local PDF import and
dependency reading. It checks the exact release SHA and `tracked_dirty=false`.
For the sdist, uv must build the package in that Git-free container; the embedded
manifest must survive. Dependency downloads use the index, not Git. No newly
discovered paper is downloaded. This tests Linux/Python 3.12; MCPVault's actual
Python, architecture and index/network policy still need confirmation.

## Publishing identity and authorization

Preparation does not reserve the PyPI name. A PyPI pending publisher also does
not reserve it until first upload. See the [official pending-publisher flow](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

The coordinating thread verified these account/environment settings in the browser
on 2026-10-03. Repository tests do not verify external account configuration:

| Field | Configured value |
| --- | --- |
| PyPI project | `papergraph-mcp` (availability/ownership checked again) |
| PyPI account | `Jonathon`, browser-verified by the coordinating thread |
| GitHub owner | `lotchuazzz-crypto` |
| GitHub repository | `papergraph-mcp` |
| Workflow filename | `pypi-publish.yml` |
| GitHub environment | `pypi`, required reviewer `lotchuazzz-crypto` (user-confirmed) |
| Target for first upload | Exact v1.2.0 commit above |

The user separately approved persistent Trusted Publisher/environment configuration
before approving first upload. The independent publisher retrieves verified
artifacts, has only job-scoped `id-token: write`, and uses the fixed PyPA action
commit `dc37677b2e1c63e2034f94d8a5b11f265b73ba33`. It does not check out project
code, build packages or use a long-lived token.
See [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

The first-upload approval covers the reviewed artifact hashes, source identity and
no-Git results. After public index version/doctor/MCP checks,
obtain approval to change MCPVault's listing to command `uvx`, args
`["--from", "papergraph-mcp==1.2.0", "papergraph-mcp"]`. Email sending is a
separate authorization. Do not treat prior GitHub release permission as PyPI or
MCPVault permission. Rebuild/review is required if artifacts need repair; do not
overwrite published artifacts or silently change v1.2.0 source.

## Protected publishing workflow

`.github/workflows/pypi-publish.yml` is non-reusable, manually dispatched, and
permits builds only from this repository's `main`. After build and same-run artifact
verification succeed, `publish` waits at environment `pypi`. The environment allows
only `main`, requires reviewer `lotchuazzz-crypto`, allows that reviewer to approve
their own run and prohibits administrator bypass. No secrets are configured.
Build, verification and normal CI retain only `contents: read`; only the independent
Linux publisher has OIDC permission, after the environment review.

The publisher downloads the same run's immutable artifact ID into `dist/`. After
approval, an inline standard-library guard rechecks the producer run ID, the exact
two regular files and their approved SHA-256 values below. Those fixed bytes bind
the upload to the source/version manifest already validated before the gate.
No package execution or rebuild occurs in this guard. Digest mismatch stops upload.
The pinned PyPA action uploads to public PyPI with metadata checking and attestations;
`skip-existing: false` makes existing-file conflicts fail visibly.

uv writes a `.gitignore` in its build output. Staging accepts only the two approved
filenames and this known marker, validates both packages, and copies only the
packages to a new candidate directory without overwriting. It rechecks the copied
bytes; saved and downloaded candidates still require exactly two regular files.
The marker stays in build output and is not uploaded. Packages are not rebuilt.

The preparation workflow optionally saves exactly the two verified distributions
as immutable GitHub artifacts with seven-day retention and no overwrite. CI and
the manual publishing workflow exercise this path. These are public package files, without
credentials or user papers, and are not PyPI releases. The artifact ID and producer
run ID go to a separate verification job. Download is scoped to the same run,
not a latest run or mutable name; no extra repository-write or OIDC permission is
requested. `scripts/check_release_artifacts.py` checks approved bytes, package
name/version and embedded source identity before saving and after downloading.
The consumer checks its `GITHUB_RUN_ID` against the producer ID. Archives are
read without extraction or package execution. The GitHub artifact ZIP digest is
separate from these individual package digests:

| Distribution | Approved SHA-256 |
| --- | --- |
| `papergraph_mcp-1.2.0-py3-none-any.whl` | `3b66a763783359baf09f04402813e4e281840a67a3067bf5a6338b61b2c26690` |
| `papergraph_mcp-1.2.0.tar.gz` | `f1e8680b51ce47a6d1a80dc0569260487218083e299c87c0f4969b5705f2748b` |

PR #41 CI #88 and merged-main CI #89 reproduced these digests. A mismatch stops
the run for review; do not silently replace the approved checksums. Source stays
at the exact v1.2.0 commit above, not current main's same-version build. The
publisher retrieves this run's already verified artifact ID and must not
rebuild or replace the distributions after review.

## Historical first-upload procedure

The following steps describe the completed 1.2.0 first upload and acceptance.
Do not dispatch the fixed v1.2.0 publisher again or replace existing files.

1. Merge the activation PR only after its CI checks pass. In repository **Actions**,
   select **Publish reviewed v1.2.0 to PyPI**, click **Run workflow**, choose `main`
   and run it. PR/push CI never invokes the publisher.
2. Wait for build and artifact verification. Open that run, click **Review deployments**,
   select **pypi**, then **Approve and deploy**. This user action permits the first
   public upload; the assistant must not approve or bypass it. If review is not yet
   shown, the prerequisite jobs may still be running.
3. First successful upload converts the pending publisher into a persistent project
   publisher. This is continuing delegation, not a version-only credential;
   revoke it through PyPI Publishing when needed. Published version files cannot
   be replaced in place.
4. Verify public-index digests and clean-cache index uvx/doctor/MCP/PDF in a truly
   Git-free consumer. That acceptance now supports the reviewed onboarding PyPI guard change;
   changing MCPVault's listing remains a separate request. Listing changes and emails remain separately
   authorized.

## Future version preparation

Prepare a new version in a separately approved change: finalize README before
building, update version-specific source identities, artifact hashes and workflow
guards, and verify metadata, wheel/sdist provenance and Git-free installation.
Only after review should an immutable tag identify that exact source. Obtain
separate publication authorization and the protected environment's human approval.
After upload, verify official-index hashes and fresh-cache CLI/MCP/PDF behavior
before enabling that version's installation guard or recommending its commands.
The current workflows and hashes are fixed to 1.2.0; this record does not authorize
changing their permissions or reusing them to overwrite that release.

The PyPI 1.2.0 long description came from the README in the original tagged
build, including its old v1.1.7/preparation examples. Editing main updates GitHub,
not that uploaded package's description. Correct it with a separately approved
new version. Never move the v1.2.0 tag, rebuild different bytes under its filenames
or replace published files; [PyPI filenames cannot be reused](https://pypi.org/help/#file-name-reuse).

References: [PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[PyPA reusable-workflow restriction](https://github.com/pypa/gh-action-pypi-publish/blob/release/v1/README.md),
and [GitHub environment reviews](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
