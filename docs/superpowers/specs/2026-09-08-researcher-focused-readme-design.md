# Researcher-Focused README Design

## Goal

Rewrite `README.md` so a first-time mathematical researcher can understand PaperGraph's purpose, main value, and first action before seeing implementation details.

## Reader Priority

The README must serve three readers in this order:

1. A researcher deciding whether PaperGraph helps them read papers with an AI agent.
2. A user setting up PaperGraph in an MCP client.
3. A developer or agent needing exact tool names and technical constraints.

## Information Architecture

The top of the README must present:

- Project name and badges.
- A short tagline: "Read math papers with evidence, not guesses."
- A compact value paragraph that explains theorem-centered reading, proof evidence, reading plans, and reviewable imports without listing every tool.
- Language anchors: English and Chinese.

The English section must use this order:

1. `What PaperGraph Helps You Do`
2. `Why Researchers Use It`
3. `Quick Start`
4. `Ask your agent to set it up`
5. `A Typical Reading Flow`
6. `What PaperGraph Does Not Do`
7. `Reference`

The Chinese section must mirror the same practical structure, but may be more compact. Full tool details should appear only once in the reference area.

## Visual Style

Use GitHub-rendered Markdown and HTML only:

- Centered title block for a cleaner first impression.
- Three-column value cards using a Markdown table.
- A compact `Do / Does not do` table.
- One Mermaid workflow diagram.
- `<details>` blocks for dense tool lists, CLI shortcuts, release history, and safety limits.

Do not add external images, scripts, generated assets, or styling that GitHub strips.

## Compatibility Constraints

The README must preserve the strings asserted by repository tests:

- Version pin: `papergraph-mcp.git@v0.9.3`.
- Launch command: `uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.9.3 papergraph-mcp --version`.
- MCP JSON with `"command": "uvx"`.
- All current single-paper, workspace, reading, queue, external-import, and CLI tool names.
- Evidence boundary phrases including `statement_explicit_latex_refs_only`, `TeX proof environments`, `immediately preceding result`, `not evidence that the theorem has no mathematical dependencies`, `raw_kind`, `display_kind`, and `normalized_kind`.
- First-use safety phrases including `For raw user requests, prefer`, `Use \`load_arxiv_paper\` only after`, and `detecting a conflict and then continuing is a failure`.
- Local walkthrough phrases including `does not resolve to \`local:paper-b\``, `target_paper_id: null`, `cited arXiv ID is imported`, and `workspace_add_arxiv_paper`.
- Safety phrases including `100 MiB`, `500 MiB`, `10,000`, `scanned PDFs`, `does not verify proofs`, `arbitrary URLs are not accepted`, and `main_file`.

## Success Criteria

- A first-time reader can describe PaperGraph's main value after the first screen.
- Dense technical content is still present but visually tucked behind reference sections.
- Existing README and onboarding tests pass.
- The new structure test verifies that the overview appears before complete tool reference material.
