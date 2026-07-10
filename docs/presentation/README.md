# PoC Presentation deck

Phase 10 deliverable — a 14-slide stakeholder deck built from a single
Markdown source of truth.

## Files in this directory

| Path | What |
|---|---|
| `deck.md` | **Source of truth.** All slide titles, prose, image references and captions. Edit this and re-run the builder. |
| `insurance-rag-poc.pptx` | Build artefact (gitignored). Emitted by `src/scripts/build_pptx.py`. |
| _(future)_ `insurance-rag-poc.pdf` | Optional PDF export: `soffice --headless --convert-to pdf insurance-rag-poc.pptx` |

## Build

```bash
cd src && source .venv/bin/activate
python scripts/build_pptx.py
# -> ../docs/presentation/insurance-rag-poc.pptx
```

The builder prints how many slides it wrote and a list of any
screenshots it couldn't find. Missing screenshots render as a
**"📸 TODO: capture &lt;name&gt;.png"** placeholder box on the slide,
so the deck is always buildable — fill the screenshots in as you
collect them.

## Automated screenshot capture (recommended)

```bash
# 1. Install Playwright (one-time)
# Run these from a WSL terminal with the repo on ext4 (see SETUP.md §2).
# Using a Windows terminal or a /mnt/c/ path means npm picks up the Windows
# node.exe, which cannot install or run the Linux Chromium binary.
cd src/frontend
npm install
npx playwright install chromium

# 2. Start the stack
cd ..
bash scripts/run_all.sh

# 3. Run the capture script (new terminal)
node scripts/capture_screenshots.mjs
```

The script opens a headed Chromium window, walks through every scenario automatically, and saves 15 PNGs to `docs/screens/`. Screenshots 04/17/18 still need manual capture (see below).

---

## Manual screenshot capture flow

Capture targets live in [`docs/screens/`](../screens/) at the repo root.
Filenames are numbered `01`–`18` in slide order.

### Where each shot goes in the deck

| File | Slide title | What the shot should show | Auto? |
|---|---|---|---|
| `01.acme-brand-header.png` | What this PoC solves | ACME-branded chat turn with citation panel open. | ✅ |
| `02.react-ui-full.png` | React SPA — full interface | Full sidebar (brand, conversations, services health dots) + EmptyState chips. | ✅ |
| `03.full-topology-stepper.png` | Seven-route state machine | Pipeline stepper mid-flight — stages running, sub-pills visible. | ✅ |
| `04.langgraph-topology.png` | LangGraph — compiled state machine | Screenshot of the compiled LangGraph topology diagram. | ✋ manual |
| `05.clarifier-turn.png` | Year-aware retrieval & clarifier | Clarifier reply asking which year, stepper showing Clarifier branch. | ✅ |
| `06.data-turn-with-table.png` | Talk-to-Data agent | KPI answer with Markdown table + "How this was computed" expander open. | ✅ |
| `07.data-drilldown-chips.png` | Drill-down — inherited / changed | Follow-up turn showing Inherited/Changed operation chips. | ✅ |
| `08.executive-report-rendered.png` | Executive annual report | Top of 2024 executive report — header + summary + KPI grid. | ✅ |
| `09.executive-risk-badges.png` | Risk indicators — deterministic bands | Risk table with 🟢/🟡/🔴 severity badges. | ✅ |
| `10.executive-downloads.png` | DOCX · PDF · MD downloads | Three download buttons row + run-id caption. | ✅ |
| `11.approval-card.png` | Human-in-the-Loop — approval gates | ApprovalCard in Telegram-watching mode — countdown + /approve instruction. | ✅ |
| `12.approval-manual.png` | Approval — inline bypass vs Telegram | ApprovalCard flipped to manual Approve / Reject buttons. | ✅ |
| `13.admin-conversations.png` | Admin panel — operations visibility | Admin Conversations tab with one row expanded showing inline messages. | ✅ |
| `14.admin-audit-log.png` | Audit log — colour-coded by subsystem | Admin Audit Log tab with monospace event chips coloured by subsystem. | ✅ |
| `15.ux-polish.png` | UX polish — feedback, timestamps, citations | Completed turn: 👍/👎 feedback, HH:mm timestamp, open citation panel. | ✅ |
| `16.aspire-trace-detail.png` | Observability — every decision in Aspire | Aspire trace detail page with span waterfall + attributes panel. | ✅ |
| `17.audit-export-csv.png` | Audit trail — compliance export | `audit_export.csv` open in Excel / VS Code, 5–10 rows visible. | ✋ manual |
| `18.azure-northstar.png` | Northstar — production architecture | Azure architecture diagram (draw.io / Excalidraw). | ✋ manual |
| `11.full-topology-stepper.png` | The seven-route state machine | The full stepper mid-flight on a RAG turn — all 7 nodes visible with sub-pills. The active branch should be green, off-path branches dimmed/strikethrough. |
| `12.clarifier-turn.png` | Year-aware retrieval & clarifier | A clarifier reply ("Which year — 2020, 2021, 2022, or 2024?") with the stepper showing `Supervisor → Clarifier` green. |
| `13.data-turn-with-table.png` | Talk-to-Data agent | A data-route reply with narrative + Markdown table visible, "How this was computed" expander open in the bottom of the screenshot. |
| `14.data-drilldown-chips.png` | Drill-down — inherited / changed chips | The same expander on a follow-up turn, showing `Inherited from previous turn: metric · filters · aggregation` and `Changed this turn: group_by`. |
| `15.executive-report-rendered.png` | Executive annual report | Top of a 2024 executive report — header + executive summary + KPI grid + first trend chart visible. |
| `16.executive-risk-badges.png` | Risk indicators — deterministic bands | The risk-indicators table only, with 🟢/🟡/🔴 badges visible across the five rows. |
| `17.executive-downloads.png` | DOCX · PDF · MD downloads | The three download buttons row + the italic `Report id ... · same id = same numbers` caption directly below. |
| `18.aspire-trace-detail.png` | Observability: every decision in Aspire | An Aspire trace page showing the supervisor → data.plan → data.execute span hierarchy for a single data turn, with attributes visible in the right panel. |
| `19.audit-export-csv.png` | Audit trail · compliance export | `audit_export.csv` opened in Excel / VS Code, showing 5–10 rows from one trace (one `supervisor.route` event, one `data.plan`, one `data.execute`, etc.). |

### Capture procedure (Windows 11 + WSL)

1. **Start the stack:**
   ```bash
   bash src/scripts/run_all.sh
   ```
2. **Open the UI** at http://localhost:5173 and Aspire at http://localhost:18888.
3. **Walk through the scenarios** — the smoke test gives you a script:
   ```bash
   cd src && source .venv/bin/activate
   python scripts/smoke_test.py
   ```
   Use the **same conversations** in the React SPA to reach each
   state listed above.
4. **Capture each shot** with **Win + Shift + S** (Snipping Tool) or
   any screenshot tool. Save into `docs/screens/<name>.png` using the
   exact filename from the table.
5. **Re-run the builder:**
   ```bash
   python scripts/build_pptx.py
   ```
   The TODO placeholders disappear and the real screenshots take their
   place.

### Tips for clean shots

- Use the browser's default light background for the most professional look.
- Crop tightly. The deck embeds at 7.0" × 5.2" — wide screenshots
  get letter-boxed. A 16:9-ish aspect ratio reads cleanest.
- For the Aspire trace shot, click the supervisor span first so the
  attribute panel shows `supervisor.route = data` and `data.csv_sha256`.
- For the Operation expander shot, **open the expander before capturing**
  so the JSON is visible.

## Editing the deck

`deck.md` is the only file you need to touch. The grammar:

```markdown
## <Slide title>                  # starts a new slide

Body prose / bullets here.        # rendered as 14pt body text
- Bullet lines work too.          # auto-bullet on lines starting with '- '
- **Bold prefixes** stay bold.    # leading **Word.** is bolded

image: <filename>.png             # embeds docs/screens/<filename>.png
note: <one-line caption>          # caption rendered under the image
```

Lines starting with `> ` (block-quotes) are skipped — the parser
treats them as documentation comments.

## Phase 10 design intent (excerpt from `docs/agent_topology.md`)

Phase 10 is non-runtime — it never runs in the live app. The deck
is a static build artefact for stakeholders. There's no node in
the LangGraph state machine and no operational impact.
