/**
 * Automated screenshot capture for the presentation deck.
 *
 * Saves 15 screenshots to docs/screens/ (01–16, excluding 04/17/18 — manual).
 * Filenames match the image: references in docs/presentation/deck.md exactly.
 *
 * Prerequisites (one-time):
 *   cd poc/frontend && npm install && npx playwright install chromium
 *
 * Run (stack must already be running via bash scripts/run_all.sh):
 *   node scripts/capture_screenshots.mjs
 */

import { chromium } from "../frontend/node_modules/playwright/index.mjs";
import { mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCREENS_DIR = resolve(__dirname, "../../docs/screens");
const UI     = "http://localhost:5173";
const ASPIRE = "http://localhost:18888";
const W = 1440, H = 900;

mkdirSync(SCREENS_DIR, { recursive: true });

// ── helpers ──────────────────────────────────────────────────────────────────

async function shot(page, name) {
  await page.screenshot({ path: `${SCREENS_DIR}/${name}`, clip: { x: 0, y: 0, width: W, height: H } });
  console.log(`  ✓  ${name}`);
}

async function send(page, text) {
  const ta = page.locator("textarea").first();
  await ta.waitFor({ state: "visible" });
  await ta.fill(text);
  await ta.press("Enter");
}

async function waitDone(page, timeout = 120_000) {
  const textareaLocator = page.locator("textarea:not([disabled])").first();
  const approvalLocator = page.getByText("Manager Approval Required", { exact: false }).first();

  // Race: textarea becomes enabled (normal) vs approval gate appears (unexpected on
  // non-report turns, e.g. a drill-down that the LLM routes as a report).
  const result = await Promise.race([
    textareaLocator.waitFor({ state: "visible", timeout }).then(() => "ready"),
    approvalLocator.waitFor({ state: "visible", timeout }).then(() => "approval"),
  ]);

  if (result === "approval") {
    const bypassBtn = page.getByText("Approve or Reject here instead", { exact: false }).first();
    if (await bypassBtn.isVisible()) await bypassBtn.click();
    await page.waitForTimeout(300);
    await page.getByText("✅ Approve").first().click();
    // Report streaming can exceed the default 120 s — use at least 180 s here.
    await textareaLocator.waitFor({ state: "visible", timeout: Math.max(timeout, 180_000) });
  }
  await page.waitForTimeout(600);
}

async function newConv(page) {
  await page.getByText("New conversation", { exact: false }).first().click();
  await page.waitForTimeout(500);
}

// ── launch ────────────────────────────────────────────────────────────────────

console.log("\n📸  Screenshot capture starting…");
console.log(`   Output dir: ${SCREENS_DIR}\n`);
console.log("   Slide → filename mapping:");
console.log("   01 acme-brand-header   02 react-ui-full      03 full-topology-stepper");
console.log("   04 langgraph-topology  05 clarifier-turn     06 data-turn-with-table");
console.log("   07 data-drilldown      08 exec-report        09 risk-badges");
console.log("   10 downloads           11 approval-card      12 approval-manual");
console.log("   13 admin-conversations 14 admin-audit-log    15 ux-polish");
console.log("   16 aspire-trace        17 audit-csv*         18 azure-northstar*");
console.log("   (* = manual capture)\n");

const browser = await chromium.launch({ headless: false, slowMo: 80 });
const ctx     = await browser.newContext({ viewport: { width: W, height: H } });
const page    = await ctx.newPage();

await page.goto(UI);
await page.waitForTimeout(2500);

// ── 02  React SPA — full interface (first impression on load) ─────────────────
console.log("[02] React SPA full UI overview");
await shot(page, "02.react-ui-full.png");

// ── 01  ACME brand header + citation panel open ───────────────────────────────
console.log("[01] ACME brand header + citation");
await newConv(page);
await send(page, "What is the maximum liability coverage in the 2022 policy?");
await waitDone(page);
const citTrigger = page.getByText(/\d+\s+source/, { exact: false }).first();
if (await citTrigger.isVisible()) await citTrigger.click();
await page.waitForTimeout(400);
await shot(page, "01.acme-brand-header.png");

// ── 15  UX polish — feedback + timestamp (same completed turn) ────────────────
console.log("[15] UX polish — feedback + timestamps");
await shot(page, "15.ux-polish.png");

// ── 03  Full topology stepper mid-flight ──────────────────────────────────────
console.log("[03] Pipeline stepper mid-flight");
await newConv(page);
await send(page, "What is the deductible for comprehensive cover in the 2024 policy?");
// The stepper is collapsed for non-agentic routes (PipelineStepper defaults
// open=false). Wait for the "Pipeline" trigger to appear mid-flight, then
// expand it so the Planner→…→Assembler chips are in the DOM for the shot.
const pipelineTrigger = page.getByText("Pipeline", { exact: false }).first();
await pipelineTrigger.waitFor({ state: "visible", timeout: 20_000 });
await pipelineTrigger.click();
await page.waitForSelector("text=Planner", { timeout: 20_000 });
await page.waitForTimeout(300);
await shot(page, "03.full-topology-stepper.png");
await waitDone(page);

// ── 05  Clarifier turn ────────────────────────────────────────────────────────
console.log("[05] Clarifier turn");
await newConv(page);
await send(page, "What is the excess on my policy?");
await waitDone(page);
await shot(page, "05.clarifier-turn.png");

// ── 06  Talk-to-Data + operation expander ─────────────────────────────────────
// renewal_rate_pct values (~80%) are well under the €1 M KPI-gate threshold,
// so this turn completes cleanly without an approval card in the screenshot.
console.log("[06] Data turn with table");
await newConv(page);
await send(page, "What was the renewal rate by product line in 2024?");
await waitDone(page);
const expander = page.getByText("How this was computed").first();
if (await expander.isVisible()) await expander.click();
await page.waitForTimeout(400);
await shot(page, "06.data-turn-with-table.png");

// ── 07  Drill-down inherited/changed chips ────────────────────────────────────
// Fresh conversation — avoids the GWP/executive context from [06] that causes
// the planner to pick executive-section-summary (approval gate) instead of
// compute-kpi. renewal_rate_pct is named explicitly in the planner's compute-kpi
// examples so it routes reliably to data.
// Two turns in the same conv: second turn sends last_data_operation from the
// first → _inherited / _changed chips appear in the OperationExpander.
console.log("[07] Drill-down chips");
await newConv(page);
await send(page, "What was the renewal rate by product line in 2024?");
await waitDone(page, 60_000);
await send(page, "What was the renewal rate by distribution channel in 2024?");
await waitDone(page, 60_000);
const drillExpander = page.getByText("How this was computed").last();
if (await drillExpander.isVisible()) await drillExpander.click();
await page.waitForTimeout(500);
await shot(page, "07.data-drilldown-chips.png");

// ── 08–10 + 11–12  Executive report → approval gate ──────────────────────────
console.log("[11-12] Approval card (Telegram + manual modes)");
console.log("[08-10] Executive report");
await newConv(page);
await send(page, "Generate the executive annual report for 2024");

await page.waitForSelector("text=Manager Approval Required", { timeout: 90_000 });
await page.waitForTimeout(700);

// 11 — ApprovalCard in default "Telegram watching" mode
await shot(page, "11.approval-card.png");

// 12 — ApprovalCard in manual Approve/Reject mode
const bypassBtn = page.getByText("Approve or Reject here instead", { exact: false }).first();
if (await bypassBtn.isVisible()) await bypassBtn.click();
await page.waitForTimeout(400);
await shot(page, "12.approval-manual.png");

// Approve and wait for the full report to stream.
// Executive reports invoke multiple LLM calls — allow up to 5 minutes.
await page.getByText("✅ Approve").first().click();
await waitDone(page, 300_000);

// 08 — top of report
await page.evaluate(() => window.scrollTo(0, 0));
await page.waitForTimeout(400);
await shot(page, "08.executive-report-rendered.png");

// 09 — risk badges section
await page.getByText("Risk", { exact: false }).first().scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(400);
await shot(page, "09.executive-risk-badges.png");

// 10 — download buttons
const dlSection = page.getByText("Word Document", { exact: false }).first();
if (await dlSection.isVisible()) await dlSection.scrollIntoViewIfNeeded();
await page.waitForTimeout(400);
await shot(page, "10.executive-downloads.png");

// ── 13–14  Admin panel ────────────────────────────────────────────────────────
console.log("[13-14] Admin panel");
await page.getByText("Admin", { exact: false }).first().click();
await page.waitForTimeout(1000);

// 13 — Conversations tab (default), expand first row
const firstConvRow = page.locator("table tbody tr").first();
if (await firstConvRow.isVisible()) await firstConvRow.click();
await page.waitForTimeout(600);
await shot(page, "13.admin-conversations.png");

// 14 — Audit Log tab
await page.getByText("Audit Log", { exact: false }).first().click();
await page.waitForTimeout(600);
await shot(page, "14.admin-audit-log.png");

// Back to chat
await page.getByText("Admin", { exact: false }).first().click();
await page.waitForTimeout(400);

// ── 16  Aspire trace detail ───────────────────────────────────────────────────
console.log("[16] Aspire trace detail");
const aspire = await ctx.newPage();
await aspire.goto(ASPIRE);
await aspire.waitForTimeout(2000);

const tracesTab = aspire.getByRole("link", { name: /traces/i }).first();
if (await tracesTab.isVisible()) await tracesTab.click();
await aspire.waitForTimeout(1500);

const firstTrace = aspire.locator("table tbody tr").first();
if (await firstTrace.isVisible()) await firstTrace.click();
await aspire.waitForTimeout(2000);
await aspire.screenshot({ path: `${SCREENS_DIR}/16.aspire-trace-detail.png`, clip: { x: 0, y: 0, width: W, height: H } });
console.log("  ✓  16.aspire-trace-detail.png");
await aspire.close();

// ── done ─────────────────────────────────────────────────────────────────────
await browser.close();

// Deck coverage check — read deck.md, extract every `image:` reference, and
// report which files are present vs still missing. Acts as a smoke-test summary.
import { readFileSync, existsSync } from "fs";
const deckPath = resolve(__dirname, "../../docs/presentation/deck.md");
const deckLines = readFileSync(deckPath, "utf8").split("\n");
const deckImages = deckLines
  .map(l => l.match(/^image:\s*(\S+)/))
  .filter(Boolean)
  .map(m => m[1]);

const present = deckImages.filter(f => existsSync(`${SCREENS_DIR}/${f}`));
const missing = deckImages.filter(f => !existsSync(`${SCREENS_DIR}/${f}`));

console.log(`\n${"─".repeat(54)}`);
console.log(`  Deck coverage: ${present.length}/${deckImages.length} images present`);
console.log(`${"─".repeat(54)}`);
present.forEach(f => console.log(`  ✅  ${f}`));
if (missing.length) {
  console.log("");
  missing.forEach(f => console.log(`  ❌  ${f}  ← still missing`));
  console.log(`\nManual captures needed:`);
  console.log(`  04.langgraph-topology.png  →  LangGraph compiled graph diagram`);
  console.log(`  17.audit-export-csv.png    →  python scripts/audit_export.py then open CSV`);
  console.log(`  18.azure-northstar.png     →  architecture diagram (draw.io / Excalidraw)`);
} else {
  console.log(`\n  All deck images are present — run build_pptx.py to rebuild the deck.`);
}
console.log(`${"─".repeat(54)}\n`);
