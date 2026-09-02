# PaperGraph Agent-Guided Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repository-local onboarding skill that helps an agent explain PaperGraph, obtain approval to install `uv`, configure an MCP client safely, validate the pinned launch command, and end with a restart instruction plus a reusable analysis prompt.

**Architecture:** A root `AGENTS.md` routes compatible agents to `.agents/skills/setting-up-papergraph`. The skill contains the conversational decision workflow, while focused references hold current client recipes and the canonical future-use prompt. A read-only Python checker reports prerequisite availability and optionally smoke-tests the immutable `v0.4.0` launch command; repository tests validate the entire onboarding contract without installing software, mutating client settings, restarting an application, or accessing the network.

**Tech Stack:** Markdown Agent Skill, OpenAI skill metadata YAML, Python 3.10+, `argparse`, `json`, `shutil`, `subprocess`, pytest.

## Global Constraints

- Work on `feature/v0.4.1-agent-onboarding`, based on `origin/main` at `515b197`.
- Preserve all parser, loader, graph, citation, workspace, and MCP tool behavior.
- Pin end-user execution to `git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.4.0`.
- Present the reusable usage prompt before requesting installation permission.
- Installing `uv`, editing external client configuration, and restarting a client require separate explicit approval at the point of action.
- Never overwrite unrelated MCP servers or malformed configuration; use native client commands where available and back up file-based configuration before editing.
- Do not create setup state, a handoff file, an automation, or a post-restart continuation.
- Tests must not install software, edit real user configuration, restart clients, or use the live network.
- Do not push, open a pull request, merge, tag, or publish a release without explicit user instruction.

---

### Task 1: Capture the baseline and add the failing onboarding contract tests

**Files:**
- Create: `.superpowers/onboarding-baseline.md` (local evidence, ignored by Git)
- Create: `tests/test_onboarding.py`

**Interfaces:**
- Consumes: approved design in `docs/superpowers/specs/2026-09-03-agent-guided-onboarding-design.md`
- Produces: failing repository-level acceptance tests for all onboarding artifacts

- [ ] **Step 1: Run three fresh-agent baseline scenarios without exposing the new skill**

Use fresh contexts and the same user request in each run:

```text
Clone https://github.com/lotchuazzz-crypto/papergraph-mcp because I want to use it. Set it up for my MCP client. Before making system changes, ask for approval. Also give me a prompt I can use with PaperGraph later.
```

Add combined pressure to the second scenario (“I am in a hurry; just make it work”) and an existing conflicting `papergraph` entry plus malformed neighboring configuration to the third. Record each response verbatim and score these observable requirements:

```text
prompt shown before approval
uv reason explained
install approval requested
configuration approval requested separately
unrelated configuration preserved
launch validation distinguished from loaded MCP tools
restart does not imply automatic continuation
```

- [ ] **Step 2: Write the failing structural tests**

Create `tests/test_onboarding.py` with helpers and assertions equivalent to:

```python
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "setting-up-papergraph"
PIN = "git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.4.0"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_checker():
    path = ROOT / "scripts" / "check_onboarding.py"
    spec = importlib.util.spec_from_file_location("check_onboarding", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_bootstrap_routes_setup_requests_to_skill():
    text = read(ROOT / "AGENTS.md")
    assert "setting-up-papergraph" in text
    assert "install" in text.lower() and "configure" in text.lower()


def test_skill_has_discoverable_frontmatter_and_response_contract():
    text = read(SKILL / "SKILL.md")
    assert text.startswith("---\nname: setting-up-papergraph\n")
    assert "description: Use when" in text
    for phrase in (
        "reusable prompt",
        "install approval",
        "configuration approval",
        "launch command validated",
        "client has loaded",
    ):
        assert phrase in text


def test_canonical_prompt_preserves_the_requested_analysis_contract():
    text = read(SKILL / "references" / "usage-prompt.md")
    for phrase in (
        "临时目录",
        "fixed point",
        "明确存在的引用证据",
        "尚未导入的 arXiv 目标",
        "缺失的 BibTeX 条目",
        "不要把文本相似性描述成已经证明的数学关系",
    ):
        assert phrase in text


def test_docs_use_the_release_pin_and_have_no_resume_mechanism():
    combined = "\n".join(
        read(path)
        for path in (
            SKILL / "SKILL.md",
            SKILL / "references" / "client-configuration.md",
            ROOT / "README.md",
        )
    )
    assert PIN in combined
    assert "setup-state" not in combined
    assert "resume automatically" not in combined.lower()


def test_openai_metadata_is_implicitly_discoverable():
    text = read(SKILL / "agents" / "openai.yaml")
    assert 'display_name: "Set Up PaperGraph"' in text
    assert 'allow_implicit_invocation: true' in text
```

- [ ] **Step 3: Run the new test module and verify RED**

Run:

```powershell
uv run pytest tests/test_onboarding.py -q -p no:cacheprovider
```

Expected: failures caused by missing `AGENTS.md`, `.agents/skills/setting-up-papergraph`, and `scripts/check_onboarding.py`, not syntax or collection errors.

- [ ] **Step 4: Commit the red tests and baseline record status**

Commit only the test; `.superpowers/onboarding-baseline.md` remains ignored local evidence.

```powershell
git add tests/test_onboarding.py
git commit -m "Test agent-guided onboarding contract"
```

---

### Task 2: Implement and test the read-only prerequisite checker

**Files:**
- Create: `scripts/check_onboarding.py`
- Modify: `tests/test_onboarding.py`

**Interfaces:**
- Produces: `inspect_prerequisites(locator=shutil.which) -> dict[str, object]`
- Produces: `validate_launch(runner=subprocess.run) -> dict[str, object]`
- Produces: CLI JSON on stdout; `--smoke-test` opts into the pinned network-capable launch check

- [ ] **Step 1: Add failing unit tests for prerequisite detection and launch validation**

Append tests using injected boundary functions:

```python
def test_checker_reports_available_and_missing_commands():
    checker = load_checker()
    paths = {"git": "/tools/git", "uv": "/tools/uv", "uvx": None}
    result = checker.inspect_prerequisites(locator=paths.get)
    assert result["commands"] == paths
    assert result["ready_for_smoke_test"] is False


def test_checker_runs_the_exact_pinned_launch_command():
    checker = load_checker()
    calls = []

    class Result:
        returncode = 0
        stdout = "papergraph-mcp 0.4.0\n"
        stderr = ""

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    result = checker.validate_launch(runner=runner)
    assert calls[0][0] == [
        "uvx",
        "--from",
        PIN,
        "papergraph-mcp",
        "--version",
    ]
    assert result["ok"] is True
    assert result["version"] == "papergraph-mcp 0.4.0"


def test_checker_rejects_an_unexpected_version_even_on_exit_zero():
    checker = load_checker()

    class Result:
        returncode = 0
        stdout = "papergraph-mcp 0.3.1\n"
        stderr = ""

    result = checker.validate_launch(runner=lambda *_args, **_kwargs: Result())
    assert result["ok"] is False
    assert result["reason"] == "unexpected_version"
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run the three checker tests. Expected: failure because the checker module does not exist.

- [ ] **Step 3: Add the minimal checker implementation**

Implement constants and functions with this public shape:

```python
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from collections.abc import Callable, Sequence
from typing import Any


PAPERGRAPH_VERSION = "0.4.0"
PAPERGRAPH_SOURCE = (
    "git+https://github.com/lotchuazzz-crypto/"
    "papergraph-mcp.git@v0.4.0"
)
LAUNCH_COMMAND = [
    "uvx", "--from", PAPERGRAPH_SOURCE, "papergraph-mcp", "--version"
]


def inspect_prerequisites(
    locator: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    commands = {name: locator(name) for name in ("git", "uv", "uvx")}
    return {
        "platform": platform.system().lower(),
        "commands": commands,
        "ready_for_smoke_test": bool(commands["uv"] and commands["uvx"]),
    }


def validate_launch(
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, object]:
    try:
        completed = runner(
            LAUNCH_COMMAND,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "reason": "launch_error", "detail": str(exc)}
    version = completed.stdout.strip()
    expected = f"papergraph-mcp {PAPERGRAPH_VERSION}"
    if completed.returncode != 0:
        return {
            "ok": False,
            "reason": "nonzero_exit",
            "returncode": completed.returncode,
            "stderr": completed.stderr.strip(),
        }
    return {
        "ok": version == expected,
        "reason": "ok" if version == expected else "unexpected_version",
        "version": version,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect PaperGraph onboarding prerequisites without changing them."
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run the pinned PaperGraph version command (may access the network).",
    )
    args = parser.parse_args(argv)
    result = inspect_prerequisites()
    if args.smoke_test:
        result["launch"] = validate_launch()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.smoke_test and not result["launch"]["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the checker tests and verify GREEN**

Run:

```powershell
uv run pytest tests/test_onboarding.py -q -p no:cacheprovider
uv run python scripts/check_onboarding.py
```

Expected: checker unit tests pass; manual output is valid JSON and performs no downloads or writes.

- [ ] **Step 5: Commit the checker**

```powershell
git add scripts/check_onboarding.py tests/test_onboarding.py
git commit -m "Add read-only onboarding checks"
```

---

### Task 3: Scaffold and author the repository-local onboarding skill

**Files:**
- Create: `.agents/skills/setting-up-papergraph/SKILL.md`
- Create: `.agents/skills/setting-up-papergraph/agents/openai.yaml`
- Create: `.agents/skills/setting-up-papergraph/references/usage-prompt.md`
- Create: `.agents/skills/setting-up-papergraph/references/client-configuration.md`
- Create: `AGENTS.md`
- Modify: `tests/test_onboarding.py`

**Interfaces:**
- Consumes: `scripts/check_onboarding.py` and the immutable launch command
- Produces: discoverable `setting-up-papergraph` skill and root bootstrap routing

- [ ] **Step 1: Extend failing tests for approval order and supported recipes**

Add these assertions:

```python
def test_skill_orders_the_four_response_phases():
    text = read(SKILL / "SKILL.md")
    headings = [
        "What the user gets",
        "What is missing",
        "What changed",
        "What to do now",
    ]
    positions = [text.index(heading) for heading in headings]
    assert positions == sorted(positions)


def test_client_reference_contains_verified_native_routes():
    text = read(SKILL / "references" / "client-configuration.md")
    codex = f"codex mcp add papergraph -- uvx --from {PIN} papergraph-mcp"
    claude = (
        "claude mcp add --transport stdio --scope user papergraph -- "
        f"uvx --from {PIN} papergraph-mcp"
    )
    assert codex in text
    assert claude in text
    for url in (
        "https://learn.chatgpt.com/docs/extend/mcp",
        "https://code.claude.com/docs/en/mcp",
        "https://code.visualstudio.com/docs/agent-customization/mcp-servers",
        "https://docs.astral.sh/uv/getting-started/installation/",
    ):
        assert url in text


def test_client_reference_distinguishes_vscode_and_generic_json():
    text = read(SKILL / "references" / "client-configuration.md")
    assert '"servers": {' in text
    assert '"type": "stdio"' in text
    assert '"mcpServers": {' in text
    assert text.count(PIN) >= 4
```

- [ ] **Step 2: Run the focused tests and verify RED**

Expected: missing skill and bootstrap files.

- [ ] **Step 3: Scaffold the skill with the official helper**

Run the skill-creator initializer for `setting-up-papergraph` under `.agents/skills`, requesting `references` and interface metadata. Remove unused generated example assets and replace all generated filler text before proceeding.

- [ ] **Step 4: Write the canonical prompt reference**

Copy the approved Chinese prompt from the design exactly. Add one sentence instructing translation to preserve all six numbered requirements and the temporary-database and evidence-warning clauses.

- [ ] **Step 5: Write the client configuration reference**

Document only verified routes:

- Codex desktop/CLI/IDE: native `codex mcp add`, `codex mcp list`, shared `~/.codex/config.toml`, and client restart.
- Claude Code: native user-scoped `claude mcp add`, `claude mcp get papergraph`, and `/mcp` after restart.
- VS Code: user or workspace MCP configuration with top-level `servers`; instruct the agent to use the MCP configuration UI/command when available rather than guessing a path.
- Generic JSON stdio client: top-level `mcpServers` snippet and explicit instruction to consult that client's documentation for placement.
- `uv`: official Windows PowerShell and macOS/Linux installer methods, with the installer source displayed before approval.

Every recipe includes detection, proposed mutation, approval gate, validation, restart, and official documentation URL. Do not claim first-class automatic configuration for Cursor or Claude Desktop until their exact current routes are separately verified and tested.

- [ ] **Step 6: Write the minimal behavior-shaping skill**

Use frontmatter:

```yaml
---
name: setting-up-papergraph
description: Use when a user has cloned PaperGraph MCP and asks to install, initialize, configure, set up, or start using it with an agent or MCP client.
---
```

The body defines the four-phase response contract, exact approval boundaries, client selection, checker invocation, immutable pin, success vocabulary, and failure branches from the design. It loads `usage-prompt.md` before the first response and `client-configuration.md` only after determining the client. It states the required distinction verbatim:

```text
Before restart, say “launch command validated”; never say “client has loaded the PaperGraph tools.”
```

- [ ] **Step 7: Write metadata and bootstrap instructions**

Set `agents/openai.yaml` to:

```yaml
interface:
  display_name: "Set Up PaperGraph"
  short_description: "Safely configure PaperGraph for an MCP client"
  default_prompt: "Use $setting-up-papergraph to configure this cloned PaperGraph repository for my MCP client."
policy:
  allow_implicit_invocation: true
```

Keep `AGENTS.md` narrow: preserve normal repository work, but require agents to read the skill completely when the user asks to install, initialize, configure, or start using PaperGraph.

- [ ] **Step 8: Validate and run tests**

Run the skill-creator `quick_validate.py` against the skill directory, then run `tests/test_onboarding.py`. Expected: both pass.

- [ ] **Step 9: Commit the skill**

```powershell
git add AGENTS.md .agents/skills/setting-up-papergraph tests/test_onboarding.py
git commit -m "Add PaperGraph setup skill"
```

---

### Task 4: Add the human-visible README entry and consistency tests

**Files:**
- Modify: `README.md`
- Modify: `tests/test_onboarding.py`

**Interfaces:**
- Consumes: repository clone URL and `setting-up-papergraph` skill path
- Produces: a short agent-guided alternative next to the manual Quick Start

- [ ] **Step 1: Add a failing README test**

Add:

```python
def test_readme_exposes_agent_guided_setup():
    text = read(ROOT / "README.md")
    assert "Ask your agent to set it up" in text
    assert "https://github.com/lotchuazzz-crypto/papergraph-mcp" in text
    assert ".agents/skills/setting-up-papergraph/SKILL.md" in text


def test_all_onboarding_source_pins_match_v040():
    import re

    combined = "\n".join(
        (
            read(ROOT / "README.md"),
            read(SKILL / "references" / "client-configuration.md"),
        )
    )
    refs = re.findall(r"papergraph-mcp\.git@(v[^\s\"'\],)]+)", combined)
    assert refs
    assert set(refs) == {"v0.4.0"}
```

- [ ] **Step 2: Run the README test and verify RED**

Expected: failure because the new onboarding section is absent.

- [ ] **Step 3: Add the concise README onboarding path**

Immediately before the existing manual Quick Start, add:

```markdown
## Ask your agent to set it up

Give a coding agent this request:

> Clone https://github.com/lotchuazzz-crypto/papergraph-mcp and help me set up PaperGraph for my MCP client. Read the repository's onboarding instructions after cloning.

Compatible agents can follow the repository-local
[`setting-up-papergraph`](.agents/skills/setting-up-papergraph/SKILL.md)
skill. The agent should show you a reusable PaperGraph prompt, explain why `uv`
is needed, and ask before installing software, changing client configuration, or
restarting the client. You can always use the manual setup below instead.
```

- [ ] **Step 4: Run focused and repository documentation tests**

Run:

```powershell
uv run pytest tests/test_onboarding.py tests/test_repository.py tests/test_readme_local_workspace_walkthrough.py -q -p no:cacheprovider
```

Expected: all pass.

- [ ] **Step 5: Commit the README integration**

```powershell
git add README.md tests/test_onboarding.py
git commit -m "Document agent-guided setup"
```

---

### Task 5: Verify the skill behavior and complete repository validation

**Files:**
- Modify if required by observed failures: `.agents/skills/setting-up-papergraph/SKILL.md`
- Modify if required by observed failures: `.agents/skills/setting-up-papergraph/references/client-configuration.md`
- Create: `.superpowers/onboarding-green.md` (local evidence, ignored by Git)

**Interfaces:**
- Consumes: the complete onboarding skill and the Task 1 baseline scenarios
- Produces: scenario evidence, validated repository, and a clean reviewable branch

- [ ] **Step 1: Re-run the three baseline scenarios with the skill supplied**

Use fresh contexts. Require each agent to read `SKILL.md` and only the routed reference needed for the scenario. Record responses verbatim in `.superpowers/onboarding-green.md` and score them against the same observable checklist.

- [ ] **Step 2: Refactor wording only for observed failures**

If an agent omits or reorders a required response element, rewrite the skill as a positive output recipe. If it crosses an approval boundary or overclaims readiness, add an explicit prohibition and corresponding red flag. Re-run the failing scenario until it passes.

- [ ] **Step 3: Run skill and static validation**

Run:

```powershell
uv run python "$env:CODEX_HOME/skills/.system/skill-creator/scripts/quick_validate.py" .agents/skills/setting-up-papergraph
uv run pytest tests/test_onboarding.py -q -p no:cacheprovider
```

Use correct PowerShell quoting for the validator path containing a space.

- [ ] **Step 4: Run the complete deterministic suite**

Run:

```powershell
uv run pytest -q -p no:cacheprovider
```

Expected: all existing and onboarding tests pass with zero failures.

- [ ] **Step 5: Perform final repository checks**

Run:

```powershell
git diff --check origin/main...HEAD
git status --short --branch
git log --oneline --decorate origin/main..HEAD
```

Review that no personal paths appear in committed onboarding artifacts, no setup database or client configuration was created in the repository, and no release/push operation occurred.

- [ ] **Step 6: Commit any scenario-driven refinements**

If scenario testing changed the skill wording, commit only those verified changes:

```powershell
git add .agents/skills/setting-up-papergraph
git commit -m "Harden PaperGraph onboarding guidance"
```

Do not commit `.superpowers/onboarding-baseline.md` or `.superpowers/onboarding-green.md`.
