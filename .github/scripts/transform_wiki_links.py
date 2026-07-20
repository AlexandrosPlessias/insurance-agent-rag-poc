#!/usr/bin/env python3
"""Transform docs/wiki/*.md relative links → absolute URLs for the public wiki.

The in-repo `docs/wiki/Home.md` uses relative links like `../../SETUP.md`
that resolve correctly when viewed inside the main repo. When that same file
is synced to the GitHub wiki (which renders at `/<repo>/wiki/<Page>`), those
relative paths break. This script rewrites them to absolute `blob/dev` (text)
or `raw/dev` (binary) URLs against the main repo, writing the transformed
files to a destination directory ready to be pushed to `<repo>.wiki.git`.

Invoked from `.github/workflows/sync-wiki.yml` on every push to `dev` that
touches `docs/wiki/**`.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

BASE = "https://github.com/AlexandrosPlessias/insurance-agent-rag-poc"
BLOB = f"{BASE}/blob/dev"
RAW = f"{BASE}/raw/dev"

# Order matters only insofar as longer prefixes (`../../`) must be tried
# before shorter ones (`../`), which the regex anchoring already enforces.
SUBSTITUTIONS: list[tuple[str, str]] = [
    # ../../<file>  → blob/dev/<file>
    (r"\.\./\.\./SETUP\.md", f"{BLOB}/SETUP.md"),
    (r"\.\./\.\./USAGE\.md", f"{BLOB}/USAGE.md"),
    (r"\.\./\.\./GRAPH\.md", f"{BLOB}/GRAPH.md"),
    (r"\.\./\.\./README\.md", f"{BLOB}/README.md"),
    # ../<file>  (relative to docs/wiki/) → blob/dev/docs/<file>
    # architecture/ sub-folder (Commit 3 restructure)
    (r"\.\./architecture/GRAPH\.md", f"{BLOB}/docs/architecture/GRAPH.md"),
    (r"\.\./architecture/agentic-pipeline\.md", f"{BLOB}/docs/architecture/agentic-pipeline.md"),
    (r"\.\./architecture/design-rationale\.md", f"{BLOB}/docs/architecture/design-rationale.md"),
    (r"\.\./architecture/ingestion\.md", f"{BLOB}/docs/architecture/ingestion.md"),
    (r"\.\./architecture/voice-integration\.md", f"{BLOB}/docs/architecture/voice-integration.md"),
    (
        r"\.\./architecture/container-orchestration\.md",
        f"{BLOB}/docs/architecture/container-orchestration.md",
    ),
    (r"\.\./BACKLOG\.md", f"{BLOB}/docs/BACKLOG.md"),
    (
        r"\.\./insurance_rag_strategic_roadmap\.md",
        f"{BLOB}/docs/insurance_rag_strategic_roadmap.md",
    ),
    (r"\.\./presentation/deck\.md", f"{BLOB}/docs/presentation/deck.md"),
    (r"\.\./presentation/README\.md", f"{BLOB}/docs/presentation/README.md"),
    # Binary assets need /raw/, not /blob/.
    (
        r"\.\./presentation/insurance-rag-poc\.pptx",
        f"{RAW}/docs/presentation/insurance-rag-poc.pptx",
    ),
    (
        r"\.\./architecture/high_level_architecture\.png",
        f"{RAW}/docs/architecture/high_level_architecture.png",
    ),
]


def transform(text: str) -> str:
    """Apply every substitution to the input markdown."""
    for pattern, replacement in SUBSTITUTIONS:
        text = re.sub(pattern, replacement, text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--src",
        required=True,
        type=pathlib.Path,
        help="Source directory (docs/wiki).",
    )
    parser.add_argument(
        "--dst",
        required=True,
        type=pathlib.Path,
        help="Destination directory (will be created if missing).",
    )
    args = parser.parse_args()

    if not args.src.is_dir():
        raise SystemExit(f"Source directory not found: {args.src}")
    args.dst.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for source_path in sorted(args.src.glob("*.md")):
        transformed = transform(source_path.read_text(encoding="utf-8"))
        leftover = re.findall(r"\]\(\.\.", transformed)
        if leftover:
            failures.append(
                f"{source_path.name}: {len(leftover)} relative link(s) "
                "remain after transform — extend SUBSTITUTIONS in "
                f"{pathlib.Path(__file__).name}."
            )
            continue
        target_path = args.dst / source_path.name
        target_path.write_text(transformed, encoding="utf-8", newline="\n")
        print(f"  {source_path.name}: ok ({len(transformed)} bytes)")

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
