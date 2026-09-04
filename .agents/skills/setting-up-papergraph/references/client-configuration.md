# Verified installation and client recipes

Use only the matching recipe below. In every recipe, detection and configuration inspection are read-only; installation, a native add command, or a configuration edit requires approval at the point of mutation. The pinned `uvx` launch validation may access the network, populate the `uv` cache, build an environment, and execute PaperGraph, so disclose those effects before running it. Never claim automatic configuration support for Cursor or Claude Desktop.

The pinned source is always:

```text
git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1
```

## Install `uv` and `uvx`

- **Detection:** run `uv --version` and `uvx --version` without modifying the host. Do nothing when both work.
- **Proposed mutation:** on Windows, display the source `https://astral.sh/uv/install.ps1` and propose:

  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

  On macOS or Linux, display the source `https://astral.sh/uv/install.sh` and propose:

  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- **Approval:** ask explicitly before downloading or running either installer. Do not reinstall or upgrade an existing `uv` automatically.
- **Validation:** run `uv --version` and `uvx --version`. Stop before client configuration if either fails.
- **Restart:** if the new executables are not visible, ask the user to reopen the terminal or refresh its environment; this is separate from the later MCP client restart.
- **Official source:** https://docs.astral.sh/uv/getting-started/installation/

## Codex desktop, CLI, and IDE extension

- **Detection:** run `codex mcp list` and inspect whether `papergraph` already exists. Codex surfaces share `~/.codex/config.toml` for this MCP configuration. If `~/.codex/config.toml` exists, parse it before proposing a mutation. If parsing fails, stop without mutation. If the `papergraph` entry is equivalent, do not rewrite it. When a mutation is needed, propose to create a timestamped adjacent backup before running the native add command.
- **Proposed mutation:** show this exact native command:

  ```text
  codex mcp add papergraph -- uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1 papergraph-mcp
  ```

- **Approval:** ask before creating the backup or running the command because both change user-level files outside the repository. If an existing `papergraph` entry differs, show the difference and ask before replacing only that entry. After approval, create the backup first and then run the command.
- **Validation:** run `codex mcp list`, then validate `uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1 papergraph-mcp --version` and `papergraph-mcp doctor`.
- **Restart:** ask before restarting a controllable Codex client; otherwise tell the user to restart Codex or reload the IDE window.
- **Official source:** https://learn.chatgpt.com/docs/extend/mcp

## Claude Code

- **Detection:** run `claude --version` and `claude mcp get papergraph` read-only to identify an existing entry. The user-scoped native command is backed by `~/.claude.json`. If `~/.claude.json` exists, parse it before proposing a mutation. If parsing fails, stop without mutation. If the `papergraph` entry is equivalent, do not rewrite it. When a mutation is needed, propose to create a timestamped adjacent backup before running the native add command.
- **Proposed mutation:** show this exact user-scoped native command:

  ```text
  claude mcp add --transport stdio --scope user papergraph -- uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1 papergraph-mcp
  ```

- **Approval:** ask before creating the backup or running the command because both mutate user-scoped files. Show any differing existing entry before asking to replace only it. After approval, create the backup first and then run the command.
- **Validation:** run `claude mcp get papergraph`, then validate `uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1 papergraph-mcp --version` and `papergraph-mcp doctor`.
- **Restart:** ask before restarting Claude Code; after restart, direct the user to `/mcp` to inspect the server connection.
- **Official source:** https://code.claude.com/docs/en/mcp

## VS Code

- **Detection:** confirm that VS Code is the selected client and inspect its MCP configuration through the MCP configuration UI or command when available. Do not guess a filesystem path.
- **Proposed mutation:** add only the `papergraph` member under the top-level `servers` object in user or workspace MCP configuration:

  ```json
  {
    "servers": {
      "papergraph": {
        "type": "stdio",
        "command": "uvx",
        "args": [
          "--from",
          "git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1",
          "papergraph-mcp"
        ]
      }
    }
  }
  ```

- **Approval:** show the entry and ask before opening or changing user/workspace configuration. Prefer the MCP configuration UI or command. If editing a file, parse it, preserve other servers, and create a timestamped adjacent backup.
- **Validation:** parse the resulting configuration, confirm only the intended entry changed, and validate `uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1 papergraph-mcp --version` and `papergraph-mcp doctor`.
- **Restart:** ask before restarting or reloading VS Code; otherwise give one direct reload-window instruction.
- **Official source:** https://code.visualstudio.com/docs/agent-customization/mcp-servers

## Generic JSON stdio client

- **Detection:** use this fallback only for an identified unsupported client or when the user explicitly requests the generic route. Ask for the client's official MCP documentation and do not infer a configuration path.
- **Proposed mutation:** ask the user to place this entry where that client's official documentation specifies:

  ```json
  {
    "mcpServers": {
      "papergraph": {
        "command": "uvx",
        "args": [
          "--from",
          "git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1",
          "papergraph-mcp"
        ]
      }
    }
  }
  ```

- **Approval:** ask before editing any discovered client file. Parse it, preserve unrelated entries, and create a timestamped adjacent backup; if safe editing is unavailable, leave the snippet for the user instead.
- **Validation:** parse the result, compare the `papergraph` command and arguments, and validate `uvx --from git+https://github.com/lotchuazzz-crypto/papergraph-mcp.git@v0.6.1 papergraph-mcp --version` and `papergraph-mcp doctor`.
- **Restart:** ask before any restart; if the client cannot be controlled, tell the user to restart it manually and consult its server-status view after reopening.
- **Official source:** use the selected client's own MCP documentation for placement; do not substitute an unverified path.
