---
name: mermaid-diagrams
description: Read, explain, inspect, create, edit, validate, and preview lightweight Mermaid diagrams stored as standalone .mmd or .mermaid files. Always use when a request involves opening, reading, understanding, checking, or changing an existing .mmd/.mermaid file. Also use for workflows, flowcharts, decision trees, sequences, state machines, component or data flows, mind maps, timelines, or explanations with several dependent steps, branches, mappings, or feedback loops that become clearer as a diagram. Prefer this text-first format over draw.io or HTML unless the user requests another format; skip it for simple relationships that prose explains more clearly.
---

# Mermaid Diagrams

Make the diagram a small, durable source artifact rather than a screenshot.

## Workflow

1. For an existing `.mmd` or `.mermaid` file, read the raw source first, identify its diagram type, and explain its nodes, relationships, branches, and constraints as needed. Do not rewrite a file when the request is only to read or explain it.
2. For a new diagram, identify the question it must answer. Show conclusions, evidence, assumptions, decisions, and actions when relevant; never expose hidden chain-of-thought.
3. Choose the smallest fitting diagram type:
   - workflow, dependency, decision, architecture: `flowchart`
   - messages over time: `sequenceDiagram`
   - lifecycle and transitions: `stateDiagram-v2`
   - hierarchy or topic decomposition: `mindmap`
   - schedule: `gantt`; chronological events: `timeline`
4. Save raw Mermaid source in a standalone `.mmd` file near the related work. Follow the repository convention if one exists; otherwise use `docs/diagrams/<descriptive-name>.mmd`. Do not wrap standalone source in a Markdown code fence.
5. Keep one diagram focused on one question. Aim for 5-15 nodes and split diagrams once scanning becomes difficult. Prefer `LR` for short processes; use `TD` for hierarchies, long labels, or flows with about 10 or more nodes.
6. Use stable ASCII node IDs and concise quoted labels. Label decision edges and feedback loops. Use subgraphs for meaningful boundaries, not decoration.
7. Validate every created or edited file with `scripts/Test-Mermaid.ps1`. Fix all parser errors before handing off.
8. If Mermaid Code is installed, open the `.mmd` file for visual review. When its optional MCP is available, use `list_diagrams` to inspect saved-file context and `preview_diagram` only for an unsaved draft; saved files refresh through the file watcher.
9. Return a clickable link to the `.mmd` source and mention any exported SVG/PNG separately.

For an inline Markdown-only request, return a fenced `mermaid` block instead of creating a standalone file. For editable freehand layout, pixel-perfect design, or unsupported notation, use the explicitly requested diagram tool.

Read [references/syntax.md](references/syntax.md) while reading, explaining, authoring, or repairing Mermaid. Read [references/tooling.md](references/tooling.md) when installing, opening, exporting, or configuring MCP integration.
