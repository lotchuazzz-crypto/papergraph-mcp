# PaperGraph Agent-Guided Onboarding Design

## Goal

Let a prospective user ask an agent to clone the PaperGraph repository and then complete a safe, guided MCP setup conversation. The onboarding must explain and, with approval, install `uv`; configure PaperGraph for the user's MCP client; validate the setup; tell the user to restart the client; and provide a reusable prompt for later PaperGraph sessions.

This is a one-time setup conversation. It does not persist conversational state or attempt to resume the setup automatically after the client restarts.

## User experience

The intended entry request is equivalent to:

```text
克隆 https://github.com/lotchuazzz-crypto/papergraph-mcp 这个仓库，我想使用 PaperGraph。
```

An agent cannot discover repository-local instructions before it has cloned and opened the repository. After cloning, the repository entry instructions direct the agent to the onboarding skill. The skill then follows this order:

1. Briefly introduce PaperGraph and immediately give the user a reusable post-installation prompt.
2. Detect whether `git`, `uv`, `uvx`, and the selected MCP client are available.
3. If the client cannot be inferred reliably, ask one concise question identifying it.
4. If `uv` is missing, explain that PaperGraph is launched reproducibly through `uvx` and request permission before installing it.
5. After permission, use the official platform-appropriate `uv` installation method and verify both `uv --version` and `uvx --version`.
6. Show the exact PaperGraph MCP configuration change and request permission before writing outside the cloned repository.
7. Merge the PaperGraph entry without deleting or replacing unrelated MCP servers, then validate the configured launch command with `papergraph-mcp --version`.
8. Report the completed checks and tell the user that the MCP client must be restarted. Ask before attempting any client restart; when restart control is unavailable, give one direct instruction instead.
9. Stop after the restart instruction. Do not create a handoff file, schedule a continuation, or imply that the old setup task will resume automatically.

Approvals necessarily make this an interactive conversation rather than a single assistant message. The complete installation remains within one setup conversation and requires no post-restart continuation.

## Repository structure

Add these components:

- `AGENTS.md`: a short repository-level bootstrap instruction. When a user asks to install, initialize, configure, or start using PaperGraph, it requires the agent to load the repository-local onboarding skill.
- `.agents/skills/setting-up-papergraph/SKILL.md`: the concise decision workflow, response contract, approval boundaries, verification gates, and failure behavior.
- `.agents/skills/setting-up-papergraph/agents/openai.yaml`: discoverability metadata for Codex-compatible runtimes.
- `.agents/skills/setting-up-papergraph/references/client-configuration.md`: exact, source-linked configuration recipes for explicitly supported clients and a generic JSON stdio fallback.
- `.agents/skills/setting-up-papergraph/references/usage-prompt.md`: the canonical reusable prompt, kept separate so the onboarding response can reproduce it accurately.
- `scripts/check_onboarding.py`: a read-only, cross-platform checker that emits machine-readable facts about prerequisites and validates the pinned PaperGraph launch command when requested. It never installs software, edits configuration, or restarts applications.
- `tests/test_onboarding.py`: repository-level structural and behavioral tests for the checker, bootstrap, skill, client recipes, response contract, version pin, and reusable prompt.
- `README.md`: a short “Ask your agent to set it up” path alongside the existing manual Quick Start.

No PaperGraph parser, loader, graph, workspace, citation, or MCP tool behavior changes in this release.

## Discovery and portability

The repository uses `.agents/skills`, the repository-local Agent Skills location recognized by Codex. `AGENTS.md` provides a second, explicit bootstrap for agents that read repository instructions. The README provides a human-visible fallback for clients that do not discover either mechanism.

The project must not claim that the phrase “clone this repository” can activate a skill before the repository exists locally, or that every agent product supports repository-local skills. The guaranteed behavior is narrower: once a compatible agent has cloned and opened the repository, it can discover or be directed to the onboarding workflow.

Codex is the first-class client because the repository-local skill and bootstrap can be tested directly in this environment. The reference also documents current configuration routes for common stdio-capable clients where official documentation supplies a stable route. For an unknown client, the skill must provide the generic JSON server entry and ask the user to place it using that client's documentation; it must not guess a configuration path.

## Reusable usage prompt

The onboarding response presents this prompt before asking for installation permission, so the user understands the value of the setup and can save the prompt even if installation is deferred:

```text
请使用 PaperGraph MCP 分析这些 LaTeX 论文，并建立一个多论文工作区。

工作区数据库保存在临时目录，不要放进 Git 仓库。依次导入我提供的论文，然后：

1. 列出成功导入的论文；
2. 搜索与“fixed point”相关的定理；
3. 比较这些定理分别来自哪篇论文；
4. 查询论文之间明确存在的引用证据；
5. 区分已解析引用、尚未导入的 arXiv 目标和缺失的 BibTeX 条目；
6. 不要把文本相似性描述成已经证明的数学关系。
```

The skill may translate this prompt when the conversation is not in Chinese, but it must preserve the six requirements, the temporary-workspace rule, and the evidence-versus-similarity warning.

## Installation and configuration contract

The skill operates conservatively:

- Read-only detection and validation may run without extra confirmation when permitted by the host.
- Installing `uv`, editing a user-level or client configuration file, and restarting an application each require explicit user approval at the point of action.
- If `uv` is already installed, do not reinstall or upgrade it automatically.
- Pin the end-user command to the latest released PaperGraph tag represented by the repository documentation, initially `v0.4.0`; do not use an unreleased branch or mutable default branch.
- Before editing an existing configuration, parse it, preserve unrelated entries, and create a timestamped adjacent backup when the client uses a file-based configuration.
- If configuration parsing fails, stop and show the exact problem. Do not replace malformed configuration with a fresh file.
- If the host cannot safely edit the target, show a minimal configuration snippet and precise placement instructions.
- Never request credentials, upload papers, or place workspace databases inside the Git repository.

The configured stdio server remains logically equivalent to:

```json
{
  "mcpServers": {
    "papergraph": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.4.0",
        "papergraph-mcp"
      ]
    }
  }
}
```

Clients with a supported native MCP command may use that command instead of direct file editing, provided the resulting server command and arguments are equivalent.

## Response contract

The skill shapes the agent's output into four short phases:

1. **What the user gets:** a plain-language PaperGraph introduction and the reusable prompt in a copyable block.
2. **What is missing:** detected prerequisite and client facts, followed by the next required approval.
3. **What changed:** only after execution, a factual list of completed installation/configuration checks and any backup path.
4. **What to do now:** a restart request or instruction, plus a reminder that future conversations can use the reusable prompt.

The agent must not report successful installation from file presence alone. Success requires executable version checks and a successful pinned `papergraph-mcp --version` smoke test. MCP tool availability itself can only be confirmed after the client restart, so the pre-restart report must distinguish “launch command validated” from “client has loaded the tools.”

## Failure behavior

- No installation permission: leave the system unchanged, retain the reusable prompt in the response, and provide the official manual installation link.
- `uv` installation failure: report the failing check and do not attempt client configuration.
- Unsupported or ambiguous client: provide the generic JSON entry and ask for the client's name or documentation; do not guess.
- Configuration already correct: do not rewrite it; validate the launch command and proceed to the restart instruction.
- Existing `papergraph` entry differs: show the difference and ask before replacing only that entry.
- Launch smoke test failure: keep any valid configuration, explain that setup is incomplete, and do not claim the client is ready.
- Restart unavailable or declined: explain how the user can restart manually. No state or automatic continuation is created.

## Testing strategy

Skill authoring follows a RED-GREEN-REFACTOR cycle:

1. Run fresh-agent baseline scenarios without the new skill and record whether agents omit the reusable prompt, skip approval, overwrite configuration, overclaim readiness, or invent restart continuation.
2. Add repository tests that initially fail because the bootstrap, skill, references, and checker do not exist.
3. Implement the minimal checker and skill materials.
4. Re-run the same fresh-agent scenarios with the skill supplied and verify the response contract and safety decisions.
5. Refine only wording that closes observed gaps, then re-run structural tests and the full PaperGraph suite.

Automated tests cover:

- Skill frontmatter, name, discoverability metadata, and required trigger vocabulary.
- Bootstrap routing from `AGENTS.md`.
- Canonical prompt fidelity and all six requested analysis steps.
- The immutable `v0.4.0` launch pin matching README configuration.
- Read-only checker results for present and absent executables using controlled test inputs.
- No state-file or automatic-resume instructions.
- Approval gates and non-destructive configuration requirements.
- Supported-client recipes and generic fallback.
- README onboarding command and links.

Final validation runs the onboarding tests, the complete existing test suite, skill validation tooling, and a clean repository diff review. Live installation, client configuration mutation, client restart, and network-dependent paper downloads are not performed by the automated suite.

## Release and Git boundaries

Treat this as a small onboarding release after `v0.4.0`, developed on `feature/v0.4.1-agent-onboarding`. Version changes are limited to documentation and onboarding metadata unless implementation reveals a real package change is required.

Commits remain local during implementation. Do not push, open a pull request, merge to `main`, create a tag, or publish a GitHub Release without the user's explicit request.
