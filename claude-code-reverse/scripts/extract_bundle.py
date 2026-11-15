#!/usr/bin/env python3
"""extract_bundle.py: Extract and beautify the JS bundle embedded in the Claude Code binary.

Claude Code 2.x ships as a Bun standalone executable. The JS application is
embedded as plaintext interleaved with binary blobs (native .node modules,
WASM, ICU data). This tool locates the JS region, extracts printable text
runs, joins them with ";\n" so tree-sitter can parse the result, splits it
into modules, classifies app vs vendored, and beautifies app modules.

Deps:  pip install click jsbeautifier tree-sitter tree-sitter-javascript

Usage:
    extract_bundle.py info    --binary PATH
    extract_bundle.py extract --binary PATH [--output DIR] [--include-vendored]

Origin: adapted from the proven pipeline documented in
references/extraction-methodology.md (community methodology, validated in
this repo against Claude Code 2.1.321, where it found 2207 modules).
"""

import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import click
import jsbeautifier
import tree_sitter as ts
import tree_sitter_javascript as tsjs

JS_LANG = ts.Language(tsjs.language())

# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def find_binary() -> Path:
    """Locate the Claude Code binary."""
    found = shutil.which("claude")
    if not found:
        raise click.ClickException("'claude' not found on PATH")
    return Path(found).resolve()


MODULE_DECL_RE = re.compile(rb"var [A-Za-z0-9_$]{1,8}=([A-Za-z0-9_$]{1,3})\(\(\)=>")


def detect_wrappers(content: bytes) -> tuple[list[bytes], int]:
    """Auto-detect Bun's minified module-wrapper helper names.

    Bun wraps every module as `var <name>=<helper>(()=>{...})`. The helper is a
    minified identifier the minifier reassigns on essentially every build
    (observed: `A` at 2.1.91, `V` at 2.1.170, `b` at 2.1.217, `S` at 2.1.220,
    `p`/`El` at 2.1.321), so it must never be hardcoded. The real helper is
    simply the modal one: it accounts for thousands of declarations, while
    incidental matches account for a handful. Returns (helpers by descending
    frequency, modal helper's count).
    """
    counts = Counter(m.group(1) for m in MODULE_DECL_RE.finditer(content))
    if not counts:
        raise click.ClickException(
            "No `var X=Y(()=>` module declarations found in binary. "
            "The Bun module wrapper structure may have changed."
        )
    modal, modal_count = counts.most_common(1)[0]
    if modal_count < 500:
        raise click.ClickException(
            f"Modal module wrapper {modal.decode()!r} occurs only {modal_count} "
            "times; expected thousands. Detection is unreliable — inspect the "
            "binary before trusting any output."
        )
    return [h for h, n in counts.most_common() if n >= 50], modal_count


def extract_js_region(binary_path: Path) -> bytes:
    """Extract the JS bundle from the binary as clean bytes.

    The Bun-compiled binary contains plaintext JS interleaved with binary
    blobs (native .node modules, WASM, ICU data). We find the JS region,
    extract all printable text runs, and join them with semicolons at
    binary boundaries to produce parseable JS.
    """
    content = binary_path.read_bytes()

    helpers, _ = detect_wrappers(content)
    modal = helpers[0]

    # Start at the FIRST module declaration using the modal helper. Do NOT back
    # up over preceding printable bytes: that lands inside an earlier template
    # literal, and the unterminated backtick makes tree-sitter swallow the whole
    # file and return ZERO modules *without* raising.
    pos = min(m.start() for m in MODULE_DECL_RE.finditer(content)
              if m.group(1) == modal)

    # The binary can carry the `---- Bun! ----` trailer away from EOF (Windows
    # builds append ~10KB of signature/padding after it), so search from the end.
    second = content.rfind(b"\n---- Bun! ----\n")
    if second == -1 or second <= pos:
        raise click.ClickException("Could not find end of JS region")

    region = content[pos:second]

    # Extract printable text runs (>20 bytes), join with ";\n"
    parts: list[bytes] = []
    current: bytearray = bytearray()
    for byte in region:
        if 32 <= byte < 127 or byte in (9, 10, 13):
            current.append(byte)
        else:
            if len(current) > 20:
                parts.append(bytes(current))
            current = bytearray()
    if len(current) > 20:
        parts.append(bytes(current))

    return b";\n".join(parts)


# ---------------------------------------------------------------------------
# Module parsing and classification
# ---------------------------------------------------------------------------

VENDORED_SIGNALS = [
    (r"hljs\.registerLanguage|MATCH_NOTHING_RE|className.*relevance|begin.*end.*contains", "vendored", "highlight-js"),
    (r"application/1d-interleaved|audio/|video/.*text/html", "vendored", "mime-db"),
    (r"IN_ROW_MODE|IN_TABLE_BODY_MODE|ATTRIBUTE_VALUE_DOUBLE_QUOTED", "vendored", "html-parser"),
    (r"@aws-sdk/|com\.amazonaws\.|CredentialsProviderError", "vendored", "aws-sdk"),
    (r"@smithy/", "vendored", "aws-smithy"),
    (r"@azure/|msal-node|msal-common", "vendored", "azure"),
    (r"@grpc/|grpc-js", "vendored", "grpc"),
    (r"@opentelemetry/", "vendored", "opentelemetry"),
    (r"forge\.(pki|cipher|md|hmac|util)|Certificate\.TBSCertificate|TLS record out of order", "vendored", "node-forge"),
    (r"@segment/", "vendored", "segment"),
    (r"ZodType|ZodString|ZodNumber|ZodObject", "vendored", "zod"),
    (r"lodash|__core-js_shared__|LazyWrapper|baseFlatten", "vendored", "lodash"),
    (r'require\("[$]/bunfs/root/', "vendored", "bun-native"),
    (r"no native wasm support|Converting base64 string to bytes", "vendored", "wasm-crypto"),
    (r"AASTriangle|AbelianGroup|AlternatingGroup", "vendored", "math-symbols"),
    (r"InvalidChar.*InvalidAttr|xmlDecl", "vendored", "xml-parser"),
    (r"lheading.*blockquote|marked", "vendored", "markdown-parser"),
]

APP_SIGNALS = [
    (r"CLAUDE\.md|claudeMd|claudeMdExcludes", "app", "claude-md"),
    (r"SKILL\.md|Loading skills", "app", "skills"),
    (r"frontmatter|Failed to parse YAML", "app", "frontmatter"),
    (r"systemPrompt|system_context|user_context|systemPromptSections", "app", "system-prompt"),
    (r"alwaysAllowRules|alwaysDenyRules|alwaysAskRules", "app", "permissions"),
    (r'"hooks"|hookExecution|pre-tool|post-tool', "app", "hooks"),
    (r"tengu_", "app", "telemetry"),
    (r"@anthropic-ai/claude-code", "app", "claude-code-pkg"),
    (r"@anthropic-ai/sdk", "app", "anthropic-sdk"),
    (r"git_status|--no-optional-locks", "app", "git"),
    (r"memory_files|auto.memory|MEMORY\.md", "app", "memory"),
    (r"McpServer|mcp_server|allowedMcpServers", "app", "mcp"),
]


def classify_module(body: str) -> tuple[str, str]:
    """Return (category, subcategory) for a module body."""
    for pattern, cat, subcat in VENDORED_SIGNALS:
        if re.search(pattern, body):
            return cat, subcat
    for pattern, cat, subcat in APP_SIGNALS:
        if re.search(pattern, body):
            return cat, subcat
    if len(body) < 200:
        return "infra", "init-glue"
    return "unknown", ""


def parse_modules(js_bytes: bytes, wrappers: list[bytes] | None = None) -> list[dict]:
    """Parse the JS bundle with tree-sitter, return module descriptors.

    `wrappers` is the auto-detected helper-name set from detect_wrappers(); it
    must not be hardcoded (see that function). Falls back to detecting against
    the extracted region itself.
    """
    if wrappers is None:
        wrappers, _ = detect_wrappers(js_bytes)
    wrappers = set(wrappers)

    parser = ts.Parser(JS_LANG)
    tree = parser.parse(js_bytes)

    modules = []
    for child in tree.root_node.children:
        if child.type != "variable_declaration":
            continue
        for decl in child.children:
            if decl.type != "variable_declarator":
                continue
            name_node = decl.child_by_field_name("name")
            value_node = decl.child_by_field_name("value")
            if not (name_node and value_node and value_node.type == "call_expression"):
                continue
            func_node = value_node.child_by_field_name("function")
            if not func_node or func_node.text not in wrappers:
                continue

            body_text = child.text.decode("utf-8", errors="replace")
            cat, subcat = classify_module(body_text)
            modules.append({
                "name": name_node.text.decode(),
                "wrapper": func_node.text.decode(),
                "start": child.start_byte,
                "end": child.end_byte,
                "size": child.end_byte - child.start_byte,
                "category": cat,
                "subcategory": subcat,
                "body": body_text,
            })

    return modules


# ---------------------------------------------------------------------------
# Beautification
# ---------------------------------------------------------------------------


def beautify(source: str) -> str:
    """Beautify minified JS."""
    opts = jsbeautifier.default_options()
    opts.indent_size = 2
    opts.max_preserve_newlines = 2
    return jsbeautifier.beautify(source, opts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli():
    """Extract and analyze the Claude Code JS bundle."""


@cli.command()
@click.option("--binary", type=click.Path(exists=True), default=None,
              help="Path to Claude Code binary. Auto-detected if omitted.")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output directory (default: ./extracted-<version-or-stem>).")
@click.option("--include-vendored", is_flag=True, default=False,
              help="Also output vendored dependency modules.")
def extract(binary, output, include_vendored):
    """Extract, parse, classify, and beautify the JS bundle."""
    binary_path = Path(binary) if binary else find_binary()
    if output is None:
        output = f"extracted-{binary_path.name.rsplit('.', 1)[0]}"
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    click.echo(f"Binary: {binary_path}", err=True)
    click.echo(f"Output: {output_path.resolve()}", err=True)

    # Step 1: Extract
    click.echo("Extracting JS from binary...", err=True)
    js_bytes = extract_js_region(binary_path)
    click.echo(f"  {len(js_bytes):,} bytes of JS extracted", err=True)

    raw_path = output_path / "bundle.js"
    raw_path.write_bytes(js_bytes)

    # Step 2: Parse
    click.echo("Parsing modules with tree-sitter...", err=True)
    wrappers, modal_count = detect_wrappers(binary_path.read_bytes())
    click.echo(f"  module wrappers detected: "
               f"{', '.join(w.decode() for w in wrappers)} "
               f"(modal {wrappers[0].decode()!r} x{modal_count:,})", err=True)
    modules = parse_modules(js_bytes, wrappers)
    click.echo(f"  {len(modules)} modules found", err=True)
    if not modules:
        raise click.ClickException(
            "Parsed 0 modules. This is the silent-failure mode: the region start "
            "is probably inside a template literal, so the unterminated backtick "
            "swallowed the file. Do not trust any output from this run."
        )

    # Step 3: Classify
    cats = Counter(m["category"] for m in modules)
    for cat, count in cats.most_common():
        total_size = sum(m["size"] for m in modules if m["category"] == cat)
        click.echo(f"    {cat}: {count} modules, {total_size:,}B", err=True)

    # Step 4: Beautify
    app_modules = [m for m in modules if m["category"] in ("app", "unknown", "infra")]
    vendored_modules = [m for m in modules if m["category"] == "vendored"]

    click.echo("Beautifying app modules...", err=True)
    app_source = "\n\n".join(m["body"] for m in app_modules)
    app_pretty = beautify(app_source)
    app_file = output_path / "claude-app.js"
    app_file.write_text(app_pretty)
    click.echo(f"  {app_file}: {len(app_pretty):,} chars, {app_pretty.count(chr(10)):,} lines", err=True)

    if include_vendored:
        click.echo("Beautifying vendored modules...", err=True)
        ven_source = "\n\n".join(m["body"] for m in vendored_modules)
        ven_pretty = beautify(ven_source)
        ven_file = output_path / "vendored.js"
        ven_file.write_text(ven_pretty)
        click.echo(f"  {ven_file}: {len(ven_pretty):,} chars", err=True)

    # Step 5: Manifest
    lines = [
        "# Claude Code Bundle Manifest",
        "",
        f"Binary: {binary_path}",
        f"Total modules: {len(modules)}",
        f"App modules: {len(app_modules)}",
        f"Vendored modules: {len(vendored_modules)}",
        "",
        "## App Modules (by size)",
        "",
    ]
    for m in sorted(app_modules, key=lambda x: x["size"], reverse=True)[:50]:
        lines.append(f"  {m['name']:>8} ({m['wrapper']}): {m['size']:>8,}B  [{m['category']}:{m['subcategory']}]")

    lines += ["", "## Vendored Modules (by category)", ""]
    by_subcat: dict[str, list[dict]] = defaultdict(list)
    for m in vendored_modules:
        by_subcat[m["subcategory"]].append(m)
    for subcat, mods in sorted(by_subcat.items(), key=lambda x: -sum(m["size"] for m in x[1])):
        total = sum(m["size"] for m in mods)
        lines.append(f"  {subcat}: {len(mods)} modules, {total:,}B")

    manifest_path = output_path / "manifest.txt"
    manifest_path.write_text("\n".join(lines) + "\n")
    click.echo(f"  {manifest_path}: manifest written", err=True)
    click.echo("Done.", err=True)


@cli.command()
@click.option("--binary", type=click.Path(exists=True), default=None,
              help="Path to Claude Code binary. Auto-detected if omitted.")
def info(binary):
    """Show bundle info without extracting."""
    binary_path = Path(binary) if binary else find_binary()

    click.echo(f"Binary: {binary_path}")
    click.echo(f"Size: {binary_path.stat().st_size:,} bytes")

    # The Bun trailer is NOT at the very end on every platform: Windows builds
    # append ~10KB of padding/signature data after it and aarch64 ELF builds
    # have section headers there, so a last-64-bytes check is a false negative.
    # Scan the tail region instead.
    content = binary_path.read_bytes()
    if content.rfind(b"---- Bun! ----") != -1:
        click.echo("Format: Bun standalone executable")
    else:
        click.echo("Format: Unknown (no Bun trailer)")
        return

    js_bytes = extract_js_region(binary_path)
    click.echo(f"JS bundle: {len(js_bytes):,} bytes")

    counts = Counter(m.group(1) for m in MODULE_DECL_RE.finditer(js_bytes))
    total = sum(n for _, n in counts.most_common() if n >= 50)
    click.echo("Modules: " + " + ".join(
        f"{n} {h.decode()}()" for h, n in counts.most_common() if n >= 50
    ) + f" = {total} total")

    for s in [b"CLAUDE.md", b"SKILL.md", b"systemPrompt", b"frontmatter"]:
        count = js_bytes.count(s)
        status = "found" if count > 0 else "MISSING"
        click.echo(f"  {s.decode()}: {status} ({count}x)")


if __name__ == "__main__":
    cli()
