# PyPI distribution preparation

This is preparation only. No PyPI release, Trusted Publisher, account/token,
GitHub publishing environment, MCPVault listing change or email is authorized by
this document. The current usable installation remains the immutable Git tag.
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

## Proposed later publishing authorization

Preparation does not reserve the PyPI name. A PyPI pending publisher also does
not reserve it until first upload. See the [official pending-publisher flow](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

The proposed future configuration, **not created or activated**, is:

| Field | Proposed value |
| --- | --- |
| PyPI project | `papergraph-mcp` (availability/ownership checked again) |
| PyPI account | `Jonathan`, user-confirmed; repository tests do not verify account settings |
| GitHub owner | `lotchuazzz-crypto` |
| GitHub repository | `papergraph-mcp` |
| Future workflow filename | `pypi-publish.yml` |
| GitHub environment | `pypi`, required reviewer `lotchuazzz-crypto` (user-confirmed) |
| Target for first upload | Exact v1.2.0 commit above |

After preparation review, the user separately approves persistent Trusted
Publisher/environment configuration. The future publisher would retrieve verified
artifacts in a separate publish job, use only job-scoped `id-token: write` plus
minimal read permissions, and use a fixed reviewed PyPA publish-action revision.
No long-lived token is needed. Those permissions and that job are absent now.
See [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/).

The user then separately approves first upload after reviewing artifact hashes,
source identity and no-Git results. After public index version/doctor/MCP checks,
obtain approval to change MCPVault's listing to command `uvx`, args
`["--from", "papergraph-mcp==1.2.0", "papergraph-mcp"]`. Email sending is a
separate authorization. Do not treat prior GitHub release permission as PyPI or
MCPVault permission. Rebuild/review is required if artifacts need repair; do not
overwrite published artifacts or silently change v1.2.0 source.

## Publishing workflow draft

`.github/workflows/pypi-publish.yml` is non-reusable, manually dispatched, and
permits builds only from this repository's `main`. Its `publish` job is fixed to
`${{ false }}`: no input can enable it. There is no publisher action, credential
request or actual publishing-environment reference. All jobs have only
`contents: read`. Dispatching this draft cannot upload to PyPI; activation needs
a separately reviewed change and authorization.

The preparation workflow optionally saves exactly the two verified distributions
as immutable GitHub artifacts with seven-day retention and no overwrite. CI and
the manual draft exercise this path. These are public package files, without
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
at the exact v1.2.0 commit above, not current main's same-version build. A future
publish job must retrieve this run's already verified artifact ID and must not
rebuild or replace the distributions after review.

## Remaining approval and configuration steps

1. Review the draft workflow PR separately from its later activation.
2. Separately approve persistent delegation. In PyPI account **Jonathan**, use
   account **Publishing** to add a GitHub pending publisher with the exact five
   fields above. Recheck project-name availability; pending registration does not
   reserve it. Enter `pypi-publish.yml`, not a full path or the reusable workflow.
3. Configure GitHub environment `pypi`: selected deployment branch `main`, required
   reviewer `lotchuazzz-crypto`, disable administrator bypass. If this sole reviewer
   also triggers the run, leave "Prevent self-review" off; enabling it requires
   another reviewer. This code does not create or configure the environment.
4. Review an activation change that adds `environment: pypi` and job-scoped
   `id-token: write` only to the independent Linux publish job, keeping only manual
   main dispatch. Retrieve the validated artifacts, recheck approved hashes and
   use a fixed reviewed PyPA publish-action commit. Build/test jobs retain no OIDC
   permission; do not add a long-lived token or secret.
5. Separately approve first upload after reviewing source, hashes and no-Git
   results; dispatch and approve the environment gate for the validated two-file
   set. First use converts the pending publisher into a persistent project
   publisher. This is continuing delegation, not a version-only credential;
   revoke it through PyPI Publishing when needed.
6. Verify public-index digests and clean-cache index uvx/doctor/MCP/PDF in a truly
   Git-free consumer. Only then review enabling the onboarding PyPI guard and
   changing MCPVault's listing. Listing changes and emails remain separately
   authorized.

References: [PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[PyPA reusable-workflow restriction](https://github.com/pypa/gh-action-pypi-publish/blob/release/v1/README.md),
and [GitHub environment reviews](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).
