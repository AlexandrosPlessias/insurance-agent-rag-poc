---
name: wiki-check
description: Validate docs/wiki relative links against transform_wiki_links.py SUBSTITUTIONS and auto-fix any gaps
---

You are a CI pre-flight assistant. Your job is to ensure the wiki link transformer will pass before any push to `dev`.

## What you must do

### Step 1 — Run the transform script

```bash
python3 .github/scripts/transform_wiki_links.py \
  --src docs/wiki \
  --dst /tmp/wiki_check_out
```

If exit code is 0: report "✓ All wiki links resolve — transform_wiki_links.py is up to date." and stop.

### Step 2 — Find the untransformed links

If exit code is non-zero, for every failing file run:

```bash
grep -n "\.\.\/" docs/wiki/<filename>
```

Collect every `](../...` link that still contains `../` after the transform. These are the gaps.

### Step 3 — Determine the correct substitution for each gap

Apply this mapping rule:
- `../../<file>.md`               → `{BLOB}/<file>.md`          (repo root files: README, SETUP, USAGE)
- `../architecture/<file>.md`     → `{BLOB}/docs/architecture/<file>.md`
- `../architecture/<file>.png`    → `{RAW}/docs/architecture/<file>.png`
- `../presentation/<file>.md`     → `{BLOB}/docs/presentation/<file>.md`
- `../presentation/<file>.pptx`   → `{RAW}/docs/presentation/<file>.pptx`
- `../<file>.md`                  → `{BLOB}/docs/<file>.md`

Where:
- `BLOB = https://github.com/AlexandrosPlessias/insurance-agent-rag-poc/blob/dev`
- `RAW  = https://github.com/AlexandrosPlessias/insurance-agent-rag-poc/raw/dev`

### Step 4 — Auto-fix `.github/scripts/transform_wiki_links.py`

Read the file first, then insert the missing entries into the `SUBSTITUTIONS` list.

Place each new entry immediately after the last existing entry in its logical group (architecture entries with architecture entries, etc.). Use this exact format:

```python
    (r"\.\./architecture/voice-integration\.md", f"{BLOB}/docs/architecture/voice-integration.md"),
```

Escape `.` as `\.` in the regex pattern. Do not escape `-` or `/`.

### Step 5 — Re-run to verify

```bash
python3 .github/scripts/transform_wiki_links.py \
  --src docs/wiki \
  --dst /tmp/wiki_check_out
```

Confirm exit code 0 and all files listed as `ok`.

### Step 6 — Report

Print a summary:
- Which links were missing
- Which substitution entries were added
- Final transform result

Do NOT commit — leave that to the user.
