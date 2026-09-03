from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "setting-up-papergraph"
PIN = "git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.4.2"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def markdown_section(text: str, heading: str) -> str:
    section = text.split(heading, maxsplit=1)[1]
    return section.split("\n## ", maxsplit=1)[0]


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


def test_onboarding_artifacts_have_no_personal_user_profile_paths():
    artifacts = (
        ROOT / "docs" / "superpowers" / "specs" / "2026-09-03-agent-guided-onboarding-design.md",
        ROOT / "docs" / "superpowers" / "plans" / "2026-09-03-agent-guided-onboarding.md",
        ROOT / "AGENTS.md",
        SKILL / "SKILL.md",
        SKILL / "agents" / "openai.yaml",
        SKILL / "references" / "usage-prompt.md",
        SKILL / "references" / "client-configuration.md",
        ROOT / "scripts" / "check_onboarding.py",
        ROOT / "README.md",
    )
    forbidden_prefixes = ("C:\\Users\\", "C:/Users/", "/Users/", "/home/")

    for path in artifacts:
        text = read(path)
        for prefix in forbidden_prefixes:
            assert prefix not in text, f"{path.relative_to(ROOT)} contains {prefix!r}"


def test_openai_metadata_is_implicitly_discoverable():
    text = read(SKILL / "agents" / "openai.yaml")
    assert 'display_name: "Set Up PaperGraph"' in text
    assert "allow_implicit_invocation: true" in text


def test_checker_reports_available_and_missing_commands():
    checker = load_checker()
    paths = {"git": "/tools/git", "uv": "/tools/uv", "uvx": None}

    result = checker.inspect_prerequisites(locator=paths.get)

    assert result["platform"] == result["platform"].lower()
    assert result["commands"] == paths
    assert result["ready_for_smoke_test"] is False


def test_checker_runs_the_exact_pinned_launch_command():
    checker = load_checker()
    calls = []

    class Result:
        returncode = 0
        stdout = "papergraph-mcp 0.4.2\n"
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
    assert result["version"] == "papergraph-mcp 0.4.2"


def test_checker_rejects_an_unexpected_version_even_on_exit_zero():
    checker = load_checker()

    class Result:
        returncode = 0
        stdout = "papergraph-mcp 0.3.1\n"
        stderr = ""

    result = checker.validate_launch(runner=lambda *_args, **_kwargs: Result())

    assert result["ok"] is False
    assert result["reason"] == "unexpected_version"


def test_checker_main_defaults_to_json_without_launching(monkeypatch, capsys):
    checker = load_checker()
    prerequisites = {
        "platform": "test",
        "commands": {"git": "/tools/git", "uv": None, "uvx": None},
        "ready_for_smoke_test": False,
    }
    monkeypatch.setattr(checker, "inspect_prerequisites", lambda: prerequisites)

    def unexpected_launch():
        raise AssertionError("default checker invocation must not launch PaperGraph")

    monkeypatch.setattr(checker, "validate_launch", unexpected_launch)

    returncode = checker.main([])
    payload = json.loads(capsys.readouterr().out)

    assert returncode == 0
    assert payload == prerequisites
    assert "launch" not in payload


def test_checker_main_smoke_test_emits_successful_launch_json(monkeypatch, capsys):
    checker = load_checker()
    prerequisites = {
        "platform": "test",
        "commands": {"git": "/tools/git", "uv": "/tools/uv", "uvx": "/tools/uvx"},
        "ready_for_smoke_test": True,
    }
    launch = {"ok": True, "reason": "ok", "version": "papergraph-mcp 0.4.2"}
    monkeypatch.setattr(checker, "inspect_prerequisites", lambda: prerequisites)
    monkeypatch.setattr(checker, "validate_launch", lambda: launch)

    returncode = checker.main(["--smoke-test"])
    payload = json.loads(capsys.readouterr().out)

    assert returncode == 0
    assert payload == {**prerequisites, "launch": launch}


def test_checker_main_failed_smoke_test_emits_json_and_returns_nonzero(
    monkeypatch, capsys
):
    checker = load_checker()
    prerequisites = {
        "platform": "test",
        "commands": {"git": "/tools/git", "uv": "/tools/uv", "uvx": "/tools/uvx"},
        "ready_for_smoke_test": True,
    }
    launch = {"ok": False, "reason": "nonzero_exit", "returncode": 1}
    monkeypatch.setattr(checker, "inspect_prerequisites", lambda: prerequisites)
    monkeypatch.setattr(checker, "validate_launch", lambda: launch)

    returncode = checker.main(["--smoke-test"])
    payload = json.loads(capsys.readouterr().out)

    assert returncode != 0
    assert payload == {**prerequisites, "launch": launch}


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


def test_skill_resolves_an_ambiguous_client_before_showing_generic_json():
    text = read(SKILL / "SKILL.md")
    assert (
        "If the client remains ambiguous, ask for its name before showing "
        "configuration"
    ) in text
    assert (
        "If the identified client is unsupported or the user explicitly chooses a "
        "generic route, show the generic JSON entry"
    ) in text
    assert "If the client is unsupported or ambiguous, show" not in text

    reference = read(SKILL / "references" / "client-configuration.md")
    generic = markdown_section(reference, "## Generic JSON stdio client")
    assert "only after the client is unknown" not in generic
    assert (
        "only for an identified unsupported client or when the user explicitly "
        "requests the generic route"
    ) in generic

    design = read(
        ROOT
        / "docs"
        / "superpowers"
        / "specs"
        / "2026-09-03-agent-guided-onboarding-design.md"
    )
    assert (
        "If the client remains ambiguous, ask for its name before showing "
        "configuration"
    ) in design
    assert (
        "If the identified client is unsupported or the user explicitly chooses a "
        "generic route, provide the generic JSON server entry"
    ) in design
    assert "For an unknown client, the skill must provide" not in design
    assert "Unsupported or ambiguous client: provide" not in design


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


def test_codex_native_route_backs_up_existing_file_before_add():
    text = read(SKILL / "references" / "client-configuration.md")
    section = markdown_section(text, "## Codex desktop, CLI, and IDE extension")
    add_command = f"codex mcp add papergraph -- uvx --from {PIN} papergraph-mcp"

    assert "If `~/.codex/config.toml` exists, parse it" in section
    assert "If parsing fails, stop without mutation" in section
    assert "If the `papergraph` entry is equivalent, do not rewrite it" in section
    backup = "create a timestamped adjacent backup"
    assert backup in section
    assert section.index(backup) < section.index(add_command)


def test_claude_native_route_backs_up_existing_file_before_add():
    text = read(SKILL / "references" / "client-configuration.md")
    section = markdown_section(text, "## Claude Code")
    add_command = (
        "claude mcp add --transport stdio --scope user papergraph -- "
        f"uvx --from {PIN} papergraph-mcp"
    )

    assert "If `~/.claude.json` exists, parse it" in section
    assert "If parsing fails, stop without mutation" in section
    assert "If the `papergraph` entry is equivalent, do not rewrite it" in section
    backup = "create a timestamped adjacent backup"
    assert backup in section
    assert section.index(backup) < section.index(add_command)


def test_client_reference_distinguishes_vscode_and_generic_json():
    text = read(SKILL / "references" / "client-configuration.md")
    assert '"servers": {' in text
    assert '"type": "stdio"' in text
    assert '"mcpServers": {' in text
    assert text.count(PIN) >= 4


def test_client_reference_discloses_launch_validation_side_effects():
    text = read(SKILL / "references" / "client-configuration.md")
    assert "detection and configuration inspection are read-only" in text
    assert "may access the network" in text
    assert "populate the `uv` cache" in text


def test_readme_exposes_agent_guided_setup():
    text = read(ROOT / "README.md")
    assert "Ask your agent to set it up" in text
    assert "https://github.com/lotchuazzz-crypto/papergraph-mcp" in text
    assert ".agents/skills/setting-up-papergraph/SKILL.md" in text


def test_all_onboarding_source_pins_match_v042():
    import re

    combined = "\n".join(
        (
            read(ROOT / "README.md"),
            read(SKILL / "references" / "client-configuration.md"),
        )
    )
    refs = re.findall(r"papergraph-mcp\.git@(v[^\s\"'\],)]+)", combined)
    assert refs
    assert set(refs) == {"v0.4.2"}
