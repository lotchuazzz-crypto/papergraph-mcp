# PyPI distribution preparation

The user separately approved the Trusted Publisher/environment configuration and,
on 2026-10-03, activation and the first public PyPI upload of the reviewed 1.2.0
files. Publication still requires the user's GitHub environment approval. This
document does not authorize MCPVault listing changes or email. The current verified
installation remains the immutable Git tag until public-index acceptance succeeds.
Public PyPI project/JSON/simple endpoints returned 404 during the 2026-10-02
assessment. That does not establish ownership or guarantee name availability.

## Reviewed source and artifacts

- Project: `papergraph-mcp`, first proposed PyPI version: `1.2.0`.
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

Git source (available now) requires Git, uv and uvx:

```text
uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v1.2.0 papergraph-mcp --version
python scripts/check_onboarding.py --install-source git --smoke-test
```

PyPI (not published/verified yet) requires uv/uvx and index access, not Git.
These commands are **post-publication candidates**, not usable setup commands now:

```text
uvx --from papergraph-mcp==1.2.0 papergraph-mcp
uvx --from papergraph-mcp==1.2.0 papergraph-mcp --version
uvx --from papergraph-mcp==1.2.0 papergraph-mcp doctor
```

Read-only prerequisite inspection is available now:

```text
python scripts/check_onboarding.py --install-source pypi
```

`prerequisites_satisfied` can be true without Git, while `publication_verified`
and `ready_for_smoke_test` remain false. PyPI smoke is blocked before execution
with `pypi_publication_not_verified`. There is no command-line bypass. A future
reviewed change may enable it only after authorized official publication and
clean-cache index validation. Repository freshness is a separate optional check.
The v1.2.0 installed doctor still recommends the Git source and emits a nonfatal
Git-context warning when Git is absent; that warning is not a failed MCP startup.
Changing installed-package behavior would require a new reviewed release.

## Actual no-Git acceptance

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

## Human review and remaining acceptance

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
   Git-free consumer. Only then review enabling the onboarding PyPI guard and
   changing MCPVault's listing. Listing changes and emails remain separately
   authorized.

References: [PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[PyPA reusable-workflow restriction](https://github.com/pypa/gh-action-pypi-publish/blob/release/v1/README.md),
and [GitHub environment reviews](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
