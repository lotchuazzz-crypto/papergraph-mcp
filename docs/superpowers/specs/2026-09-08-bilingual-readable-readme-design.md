# Bilingual Readable README Design

## Purpose

Improve README readability for first-time mathematical researchers while preserving the repository's tested setup, safety, tool, and release information.

## Structure

The README will remain a single file so GitHub renders it directly. The top will provide language anchors:

- English
- 中文

The English section comes first for GitHub/package convention. The Chinese section follows as a complete practical guide, not a line-by-line duplicate.

## Content Rules

- Keep v0.9.3 release pins and setup commands intact.
- Keep all tested tool names present.
- Replace the long ungrouped tool paragraph with a grouped capability table.
- Keep workflow examples, but collapse repetitive prose.
- Keep release history in a compact section instead of the opening screen.
- Preserve safety limits: 100 MiB, 500 MiB, 10,000.
- Preserve limitations: scanned PDFs, proof verification, arbitrary URLs, `main_file`.
- Keep relative links to existing files only.

## Bilingual Behavior

GitHub Markdown cannot provide a true interactive language toggle without external assets or scripts. The supported version of "switchable" is an anchor-based toggle at the top and at section boundaries:

- `[English](#english)`
- `[中文](#中文)`

Each language section has enough standalone content for a reader to start using the project.

## Testing

Run README, onboarding, repository, CLI, diagnostics, and server tests after editing. Then run the full suite before pushing.
