"""Build the Phase 10 stakeholder PoC deck.

Reads docs/presentation/deck.md as the single source of truth and
emits docs/presentation/insurance-rag-poc.pptx. Screenshots are
loaded from docs/screens/<name>.png; missing files render as a
'TODO: capture <name>.png' placeholder so the deck still builds
while the user is collecting captures.

Slide grammar (parsed from deck.md):
    ## <title>             -> starts a new slide
    image: <file>.png      -> embeds docs/screens/<file>.png
    note: <line>           -> SPEAKER NOTE (PPTX notes pane, NOT
                              visible on the slide). Author can
                              leave themselves cues without
                              polluting the client-facing surface.
    everything else        -> bullets / prose in the slide body

Run:
    cd poc && source .venv/bin/activate
    python scripts/build_pptx.py
    # -> docs/presentation/insurance-rag-poc.pptx
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DECK_MD = REPO_ROOT / "docs" / "presentation" / "deck.md"
SCREENS_DIR = REPO_ROOT / "docs" / "screens"
OUT_PPTX = REPO_ROOT / "docs" / "presentation" / "insurance-rag-poc.pptx"

# Brand colours (same navy as the Phase 9 PDF table headers).
ACME_NAVY = (0x0d, 0x3b, 0x66)
ACME_NAVY_LIGHT = (0x1d, 0x6f, 0xa5)
GREY = (0x55, 0x55, 0x55)
GREY_LIGHT = (0xbb, 0xbb, 0xbb)


# ---------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------


@dataclass
class Slide:
    title: str
    body_lines: list[str] = field(default_factory=list)
    # filename in docs/screens/, e.g. "10.acme-brand-header.png"
    image: str = ""
    # Speaker note - routed to the PPTX notes pane, never visible
    # on the slide itself.
    note: str = ""

    def has_image(self) -> bool:
        return bool(self.image)


_HR = re.compile(r"^---+\s*$")
_TITLE = re.compile(r"^##\s+(.+?)\s*$")
_IMAGE = re.compile(r"^image:\s*(.+?)\s*$")
_NOTE = re.compile(r"^note:\s*(.+?)\s*$")
_BLOCKQUOTE = re.compile(r"^>\s")


def parse_deck(md_path: Path) -> list[Slide]:
    """Convert deck.md into a list of Slide objects.

    The top-level `# <title>` line is skipped — slides start at
    `##`. Block-quotes (lines beginning with '>') are skipped so the
    parsing-rules block at the top of the file doesn't leak.
    """
    text = md_path.read_text(encoding="utf-8")
    slides: list[Slide] = []
    current: Slide | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if _HR.match(line):
            continue
        if _BLOCKQUOTE.match(line):
            continue
        # Skip the top-level h1 (deck title).
        if line.startswith("# ") and current is None:
            continue
        m_title = _TITLE.match(line)
        if m_title:
            if current is not None:
                slides.append(current)
            current = Slide(title=m_title.group(1))
            continue
        if current is None:
            continue
        m_img = _IMAGE.match(line)
        if m_img:
            current.image = m_img.group(1)
            continue
        m_note = _NOTE.match(line)
        if m_note:
            # `note:` is a SPEAKER note that always attaches to the
            # current slide (routed to the PPTX notes pane, not
            # rendered on the slide). Multiple notes on one slide
            # are concatenated.
            text_line = m_note.group(1)
            current.note = (
                f"{current.note}\n{text_line}" if current.note
                else text_line
            )
            continue
        # Plain body line.
        if line or current.body_lines:
            current.body_lines.append(line)

    if current is not None:
        slides.append(current)

    # Trim trailing empty body lines.
    for s in slides:
        while s.body_lines and not s.body_lines[-1].strip():
            s.body_lines.pop()
    return slides


# ---------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------


def _add_text_frame(slide, left, top, width, height, lines, *,
                    font_size, color, bold=False, italic=False):
    """Append a TextFrame on the slide with the given lines."""
    from pptx.util import Pt
    from pptx.dml.color import RGBColor

    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        # Bullets for body lines that start with '- ' or '* '.
        text = line
        if text.startswith("- ") or text.startswith("* "):
            text = text[2:]
            p.level = 0
        # Bold a leading "**Word.**" prefix the deck uses for
        # bullet-list emphasis (executive summary / yearly narrative
        # carry this convention).
        bold_prefix_match = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", text)
        if bold_prefix_match:
            run = p.add_run()
            run.text = bold_prefix_match.group(1)
            run.font.bold = True
            run.font.size = Pt(font_size)
            run.font.color.rgb = RGBColor(*color)
            tail = bold_prefix_match.group(2)
            if tail:
                run2 = p.add_run()
                run2.text = " " + tail
                run2.font.size = Pt(font_size)
                run2.font.color.rgb = RGBColor(*color)
        else:
            run = p.add_run()
            run.text = text
            run.font.size = Pt(font_size)
            run.font.bold = bold
            run.font.italic = italic
            run.font.color.rgb = RGBColor(*color)
    return tb


def _add_placeholder(slide, left, top, width, height, filename, prs):
    """Draw a TODO box when the referenced screenshot is missing."""
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Pt

    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height,
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor(0xf3, 0xf5, 0xf9)
    shape.line.color.rgb = RGBColor(*GREY_LIGHT)
    shape.line.width = Pt(1)
    tf = shape.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = 2  # CENTER
    run = p.add_run()
    run.text = f"📸  TODO: capture  {filename}"
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.color.rgb = RGBColor(*GREY)
    sub = tf.add_paragraph()
    sub.alignment = 2
    sub_run = sub.add_run()
    sub_run.text = (
        f"Save the screenshot to docs/screens/{filename} and "
        "re-run scripts/build_pptx.py"
    )
    sub_run.font.size = Pt(10)
    sub_run.font.italic = True
    sub_run.font.color.rgb = RGBColor(*GREY)


def render_pptx(slides: list[Slide], out_path: Path) -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor

    prs = Presentation()
    prs.slide_width = Inches(13.333)   # 16:9 widescreen
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]   # blank layout

    for i, slide_def in enumerate(slides):
        slide = prs.slides.add_slide(blank_layout)

        # --- Title bar (navy) --------------------------------------
        from pptx.enum.shapes import MSO_SHAPE
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(0),
            prs.slide_width, Inches(0.9),
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = RGBColor(*ACME_NAVY)
        bar.line.fill.background()
        title_tb = slide.shapes.add_textbox(
            Inches(0.5), Inches(0.15),
            prs.slide_width - Inches(1), Inches(0.7),
        )
        tp = title_tb.text_frame.paragraphs[0]
        tp_run = tp.add_run()
        tp_run.text = slide_def.title
        tp_run.font.size = Pt(28)
        tp_run.font.bold = True
        tp_run.font.color.rgb = RGBColor(0xff, 0xff, 0xff)

        # --- Decide layout based on whether there's an image -------
        body_top = Inches(1.1)
        body_left = Inches(0.5)
        body_width = prs.slide_width - Inches(1)

        if slide_def.has_image():
            # Split: body bullets on the left (40%), image on the
            # right (58%, room for a margin).
            text_w = Inches(5.2)
            img_left = Inches(6.0)
            img_top = body_top
            img_w = Inches(7.0)
            img_h = Inches(5.2)

            if slide_def.body_lines:
                _add_text_frame(
                    slide,
                    body_left, body_top, text_w, Inches(5.0),
                    slide_def.body_lines,
                    font_size=14, color=(0x22, 0x22, 0x22),
                )

            img_path = SCREENS_DIR / slide_def.image
            if img_path.is_file():
                slide.shapes.add_picture(
                    str(img_path), img_left, img_top,
                    width=img_w, height=img_h,
                )
            else:
                _add_placeholder(
                    slide,
                    img_left, img_top, img_w, img_h,
                    slide_def.image, prs,
                )

        else:
            # Full-width prose / bullets.
            _add_text_frame(
                slide,
                body_left, body_top,
                body_width, prs.slide_height - body_top - Inches(0.4),
                slide_def.body_lines or [""],
                font_size=18, color=(0x22, 0x22, 0x22),
            )

        # --- Speaker note (NOT visible on the slide) ----------------
        # Routed to the PPTX notes pane so the presenter sees it in
        # Presenter View but the audience never does. Keeps the
        # client-facing surface clean.
        if slide_def.note:
            notes_tf = slide.notes_slide.notes_text_frame
            notes_tf.text = slide_def.note

        # --- Footer (slide N / run id placeholder) ------------------
        footer = slide.shapes.add_textbox(
            Inches(0.5),
            prs.slide_height - Inches(0.4),
            prs.slide_width - Inches(1),
            Inches(0.3),
        )
        fp = footer.text_frame.paragraphs[0]
        fp.alignment = 2  # CENTER
        fr = fp.add_run()
        fr.text = (
            f"ACME Insurances · Local RAG PoC · "
            f"slide {i + 1}/{len(slides)}"
        )
        fr.font.size = Pt(9)
        fr.font.color.rgb = RGBColor(*GREY)
        fr.font.italic = True

    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deck", type=Path, default=DECK_MD,
        help="Path to deck.md (default: docs/presentation/deck.md).",
    )
    parser.add_argument(
        "--out", type=Path, default=OUT_PPTX,
        help=(
            "Output .pptx path "
            "(default: docs/presentation/insurance-rag-poc.pptx)."
        ),
    )
    args = parser.parse_args()

    if not args.deck.is_file():
        print(f"deck markdown not found: {args.deck}", file=sys.stderr)
        return 1

    slides = parse_deck(args.deck)
    if not slides:
        print(f"no slides parsed from {args.deck}", file=sys.stderr)
        return 1

    missing = []
    for s in slides:
        if s.has_image() and not (SCREENS_DIR / s.image).is_file():
            missing.append(s.image)

    render_pptx(slides, args.out)
    print(f"Wrote {len(slides)} slides -> {args.out}")
    if missing:
        print(
            f"  (note: {len(missing)} screenshot(s) missing - "
            "TODO placeholders rendered):"
        )
        for m in missing:
            print(f"    docs/screens/{m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
