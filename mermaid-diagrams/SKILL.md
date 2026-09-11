---
name: mermaid-diagrams
description: Create, edit, validate, and preview lightweight Mermaid diagrams as standalone .mmd files. Use for workflows, flowcharts, decision trees, sequences, state machines, component or data flows, mind maps, timelines, or explanations with several dependent steps, branches, mappings, or feedback loops that become clearer as a diagram. Prefer this text-first format over draw.io, HTML, or an Obsidian-only canvas unless the user requests another format; skip it for simple relationships that prose explains more clearly.
---

# Mermaid Diagrams

Make the diagram a small, durable source artifact rather than a screenshot.

## Workflow

1. Identify the question the diagram must answer. Show conclusions, evidence, assumptions, decisions, and actions when relevant; never expose hidden chain-of-thought.
2. Choose the smallest fitting diagram type:
   - workflow, dependency, decision, architecture: `flowchart`
   - messages over time: `sequenceDiagram`
   - lifecycle and transitions: `stateDiagram-v2`
   - hierarchy or topic decomposition: `mindmap`
   - schedule: `gantt`; chronological events: `timeline`
3. Save raw Mermaid source in a standalone `.mmd` file near the related work. Follow the repository convention if one exists; otherwise use `docs/diagrams/<descriptive-name>.mmd`. Do not wrap standalone source in a Markdown code fence.
4. Keep one diagram focused on one question. Aim for 5-15 nodes and split diagrams once scanning becomes difficult. Prefer `LR` for short processes; use `TD` for hierarchies, long labels, or flows with about 10 or more nodes.
5. Use stable ASCII node IDs and concise quoted labels. Label decision edges and feedback loops. Use subgraphs for meaningful boundaries, not decoration.
6. Validate every created or edited file with `scripts/Test-Mermaid.ps1`. Fix all parser errors before handing off.
7. If Mermaid Code is installed, open the `.mmd` file for visual review. When its optional MCP is available, use `list_diagrams` to inspect saved-file context and `preview_diagram` only for an unsaved draft; saved files refresh through the file watcher.
8. Return a clickable link to the `.mmd` source and mention any exported SVG/PNG separately.

For an inline Markdown-only request, return a fenced `mermaid` block instead of creating a standalone file. For editable freehand layout, pixel-perfect design, or unsupported notation, use the explicitly requested diagram tool.

Read [references/syntax.md](references/syntax.md) while authoring or repairing Mermaid. Read [references/tooling.md](references/tooling.md) when installing, opening, exporting, or configuring MCP integration.
