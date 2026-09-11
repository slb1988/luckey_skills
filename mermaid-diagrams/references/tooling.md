# Tooling, preview, and MCP

## Recommended stack

1. `.mmd` is the source of truth.
2. Mermaid Code is the lightweight cross-platform editor and visual preview.
3. Mermaid CLI (`mmdc`) is the deterministic syntax check and SVG/PNG/PDF exporter.
4. Mermaid Code MCP is optional. It exposes editor context and an unsaved Draft preview; it does not replace filesystem editing or CLI validation.

## Install on Windows

Run the bundled installer from PowerShell:

```powershell
& .\scripts\Install-MermaidTooling.ps1 -ConfigureMcp -Launch
```

The script downloads the latest Windows x64 Mermaid Code installer from its GitHub release, installs the official Mermaid CLI with npm, and adds the local HTTP MCP to available Codex and Claude Code clients. Re-running it is safe: existing matching MCP entries are left in place.

Mermaid Code registers `.mmd` and `.mermaid` file associations. It can open a single file from any folder, watch external changes, edit the source, and export SVG or PNG.

## Validate or export

Validate without keeping output:

```powershell
& .\scripts\Test-Mermaid.ps1 .\docs\diagrams\workflow.mmd
```

Keep an SVG render:

```powershell
& .\scripts\Test-Mermaid.ps1 .\docs\diagrams\workflow.mmd -OutputPath .\docs\diagrams\workflow.svg
```

Open a file in Mermaid Code through its registered file association:

```powershell
Invoke-Item .\docs\diagrams\workflow.mmd
```

## Mermaid Code MCP

The MCP server is local-only at `http://127.0.0.1:37079/mcp` and currently exposes:

- `list_diagrams`: return the open folder, known `.mmd` files, and active file.
- `preview_diagram`: replace the unsaved Draft tab with supplied Mermaid source.

One-time app step: open Mermaid Code, open the top-left menu, and enable **MCP Server**. The preference persists, and the server restarts with the app on later launches.

Codex configuration:

```powershell
codex mcp add mermaid-code-mcp --url http://127.0.0.1:37079/mcp
```

Claude Code user configuration:

```powershell
claude mcp add --scope user --transport http mermaid-code-mcp http://127.0.0.1:37079/mcp
```

Test while Mermaid Code is running and the switch is on:

```powershell
codex mcp list
claude mcp get mermaid-code-mcp
```

For saved files, call `list_diagrams`, read and edit the returned path with normal filesystem tools, and let Mermaid Code's watcher refresh the preview. Call `preview_diagram` only when the user wants a temporary preview that is not yet saved.

Sources:

- Mermaid Code: <https://github.com/m8524769/mermaid-code>
- Mermaid CLI: <https://github.com/mermaid-js/mermaid-cli>
- Codex MCP configuration: <https://learn.chatgpt.com/docs/extend/mcp?surface=cli>
