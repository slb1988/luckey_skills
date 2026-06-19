#!/usr/bin/env bun
/**
 * Generate WeChat article cover image (1800x766)
 * Uses Chrome headless to render an HTML template with background + title overlay.
 * The original background image is never modified.
 *
 * Usage:
 *   bun generate-cover.ts --title "文章标题" --output imgs/cover.png --bg common-bgs/bg.png
 */

import { parseArgs } from "util";
import fs from "fs";
import path from "path";
import os from "os";

const COVER_WIDTH = 1800;
const COVER_HEIGHT = 766;

const SKILL_DIR = path.dirname(path.dirname(import.meta.url.replace("file://", "")));
const TEMPLATE_PATH = path.join(SKILL_DIR, "assets", "cover-template.html");

const { values } = parseArgs({
  args: process.argv.slice(2),
  options: {
    title: { type: "string" },
    output: { type: "string" },
    bg: { type: "string" },
  },
});

if (!values.title || !values.output) {
  console.error("Usage: bun generate-cover.ts --title <title> --output <output.png> [--bg <background.png>]");
  process.exit(1);
}

// Resolve background image
const vaultRoot = path.resolve(SKILL_DIR, "../../..");
const commonBgsDir = path.join(vaultRoot, "writing", "common-bgs");

let bgPath = values.bg;
if (!bgPath) {
  // Pick a random image from common-bgs/
  const bgs = fs.existsSync(commonBgsDir)
    ? fs.readdirSync(commonBgsDir).filter(f => /\.(png|jpg|jpeg|webp)$/i.test(f))
    : [];
  if (bgs.length === 0) {
    console.error(`No background images found in ${commonBgsDir}. Add at least one .png file.`);
    process.exit(1);
  }
  bgPath = path.join(commonBgsDir, bgs[Math.floor(Math.random() * bgs.length)]);
}

bgPath = path.resolve(bgPath);
if (!fs.existsSync(bgPath)) {
  console.error(`Background image not found: ${bgPath}`);
  process.exit(1);
}

// Read and populate HTML template
const templateHtml = fs.readFileSync(TEMPLATE_PATH, "utf-8");
const html = templateHtml
  .replace("__BG_PATH__", `file://${bgPath}`)
  .replace("__TITLE__", values.title.replace(/</g, "&lt;").replace(/>/g, "&gt;"));

// Write HTML to a temp file
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "cover-"));
const tmpHtml = path.join(tmpDir, "cover.html");
fs.writeFileSync(tmpHtml, html, "utf-8");

// Ensure output directory exists
const outputPath = path.resolve(values.output);
fs.mkdirSync(path.dirname(outputPath), { recursive: true });

// Find Chrome
function findChrome(): string {
  const candidates = [
    process.env.WECHAT_BROWSER_CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
  ].filter(Boolean) as string[];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  throw new Error("Chrome not found. Set WECHAT_BROWSER_CHROME_PATH or install Google Chrome.");
}

const chromePath = findChrome();
console.log(`[cover] Chrome: ${chromePath}`);
console.log(`[cover] Title: ${values.title}`);
console.log(`[cover] Background: ${bgPath}`);

// Run Chrome headless screenshot
const proc = Bun.spawnSync([
  chromePath,
  "--headless=new",
  "--disable-gpu",
  "--no-sandbox",
  "--disable-setuid-sandbox",
  "--disable-dev-shm-usage",
  `--window-size=${COVER_WIDTH},${COVER_HEIGHT}`,
  `--screenshot=${outputPath}`,
  `--virtual-time-budget=2000`,
  `file://${tmpHtml}`,
], { stderr: "pipe" });

// Cleanup temp files
fs.rmSync(tmpDir, { recursive: true, force: true });

if (!fs.existsSync(outputPath)) {
  console.error("[cover] Screenshot failed.");
  console.error(new TextDecoder().decode(proc.stderr));
  process.exit(1);
}

const stat = fs.statSync(outputPath);
console.log(`[cover] Saved: ${outputPath} (${Math.round(stat.size / 1024)}KB)`);
