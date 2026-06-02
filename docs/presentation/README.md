# PoC Presentation deck

Phase 10 deliverable — a 14-slide stakeholder deck built from a single
Markdown source of truth.

## Files in this directory

| Path | What |
|---|---|
| `deck.md` | **Source of truth.** All slide titles, prose, image references and captions. Edit this and re-run the builder. |
| `insurance-rag-poc.pptx` | Build artefact (gitignored). Emitted by `poc/scripts/build_pptx.py`. |
| _(future)_ `insurance-rag-poc.pdf` | Optional PDF export: `soffice --headless --convert-to pdf insurance-rag-poc.pptx` |

## Build

```bash
cd poc && source .venv/bin/activate
python scripts/build_pptx.py
# -> ../docs/presentation/insurance-rag-poc.pptx
```

The builder prints how many slides it wrote and a list of any
screenshots it couldn't find. Missing screenshots render as a
**"📸 TODO: capture &lt;name&gt;.png"** placeholder box on the slide,
so the deck is always buildable — fill the screenshots in as you
collect them.

## Screenshot capture flow

Capture targets live in [`docs/screens/`](../screens/) at the repo
root. The deck references **ten** new shots (`10.*` through `19.*`)
on top of the seven shots from Phase 5/6 that are already tracked.

### Where each shot goes in the deck

| File | Slide title | What the shot should show |
|---|---|---|
| `10.acme-brand-header.png` | What this PoC solves | The ACME-branded page top + a chat turn with a citation popover open. Demonstrates the "real product" feel. |
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
   bash poc/scripts/run_all.sh
   ```
2. **Open the UI** at http://localhost:8501 and Aspire at http://localhost:18888.
3. **Walk through the scenarios** — the smoke test gives you a script:
   ```bash
   cd poc && source .venv/bin/activate
   python scripts/smoke_test.py
   ```
   Use the **same conversations** in the Streamlit UI to reach each
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

- Use **light theme** for the most professional look (Streamlit:
  ☰ menu → Settings → Theme: Light).
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
