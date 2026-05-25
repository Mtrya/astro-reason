#!/usr/bin/env python3
"""Render the Chapter 5 case-study montage (v4) from verbatim trace excerpts.

Visual model: chapter5_case_study_montage_reference_travelplanner.png
(centered column header + colored accent bar, italic Task block, inline role
labels with bold colored prefix, tight yellow highlights on key tokens).

Three panels:
  A — Claude Code + Opus 4.6 on Stereo Imaging case_0005   (private-world failure)
  B — Claude Code + Opus 4.6 on Revisit Constellation case_0001 (calibration vs verifier)
  C — Codex CLI + GPT-5.4  on Relay Constellation case_0003     (case-adaptive search)

Source: experiments/main_agentic/reports/case_studies/chapter5_case_study_figure_snippets.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "experiments" / "images" / "chapter5_case_study_montage_v4.png"

MARK = "▌"

FONT_REGULAR = "/usr/share/fonts/TTF/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
FONT_ITALIC = "/usr/share/fonts/TTF/DejaVuSans-Oblique.ttf"
FONT_BOLD_ITALIC = "/usr/share/fonts/TTF/DejaVuSans-BoldOblique.ttf"
FONT_MONO = "/usr/share/fonts/TTF/DejaVuSansMono.ttf"
FONT_MONO_BOLD = "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf"


ROLE_COLORS = {
    "Reads":      "#1F6B3F",
    "Thought":    "#5E3A8E",
    "Decision":   "#8A5A00",
    "Writes":     "#1F4E8C",
    "Self-check": "#0F6B6B",
    "Verifier":   "#9A2C3C",
}

PANEL_TONE = {
    "A": "#B23A48",
    "B": "#2F5D8E",
    "C": "#2F7A53",
}

HIGHLIGHT_BG = "#FFE89A"
TEXT_FG = "#1B1B1B"
TASK_FG = "#202020"
SUBTLE_FG = "#5A5A5A"
TASK_BG = "#FAF6E9"
DIVIDER = "#E6E6E6"


@dataclass
class Line:
    text: str
    mono: bool = False


@dataclass
class Beat:
    role: str
    role_note: str = ""
    body: list[Line] = field(default_factory=list)


@dataclass
class Panel:
    label: str
    title: str         # mechanism-as-header, e.g. "Private world"
    subtitle: str      # agent + benchmark, e.g. "Claude Code · Opus 4.6  ·  Stereo Imaging, case_0005"
    task: str
    beats: list[Beat]


# -------------------------------------------------------------------------
# Panel content
# -------------------------------------------------------------------------


def L(text, mono=False):
    return Line(text=text, mono=mono)


PANEL_A = Panel(
    label="A",
    title="Private world",
    subtitle="Claude Code · Opus 4.6   on   Stereo Imaging, case_0005",
    task=(
        "Schedule satellite observations the verifier will accept. "
        f"Submit a top-level {MARK}actions[]{MARK} list of individual observations."
    ),
    beats=[
        Beat(
            role="Reads",
            body=[
                L("$ ls case/   →   mission.yaml · satellites.yaml · targets.yaml", mono=True),
                L("(no root listing, no README, no verifier --help)"),
            ],
        ),
        Beat(
            role="Thought",
            body=[
                L(f"“This is a {MARK}stereo imaging scheduling problem{MARK}. … identify {MARK}stereo pair candidates{MARK} …”"),
            ],
        ),
        Beat(
            role="Decision",
            body=[
                L(f"“I need to build a {MARK}stereo imaging scheduler{MARK}. … {MARK}write the solver{MARK}.”"),
            ],
        ),
        Beat(
            role="Writes",
            body=[
                L("solve.py:  \"\"\"Stereo imaging scheduler …\"\"\"", mono=True),
                L(f"output  →  {{ \"target_id\": \"open_071\",  {MARK}\"observations\"{MARK}: [ … ] }}", mono=True),
            ],
        ),
        Beat(
            role="Self-check",
            role_note="agent's own verify.py",
            body=[
                L("=== VERIFICATION RESULTS ===", mono=True),
                L(f"{MARK}Valid stereo pairs: 98{MARK}     {MARK}Issues found: 0{MARK}", mono=True),
            ],
        ),
    ],
)


PANEL_B = Panel(
    label="B",
    title="Calibration vs verifier",
    subtitle="Claude Code · Opus 4.6   on   Revisit Constellation, case_0001",
    task=(
        f"Design a satellite constellation that revisits every ground target within {MARK}6 hours{MARK}. "
        "The verifier is opaque — only its accept/reject output and error strings are visible."
    ),
    beats=[
        Beat(
            role="Writes",
            body=[
                L("solve.py:  hand-coded J2 propagator + simplified Earth rotation.", mono=True),
                L("output  →  20-satellite plan.", mono=True),
            ],
        ),
        Beat(
            role="Self-check",
            role_note="printed before the verifier call",
            body=[
                L("GMST offset:   1.6443 deg", mono=True),
                L(f"ITRF check at t=0 …    {MARK}Diff: 17 601.56 m{MARK}", mono=True),
            ],
        ),
        Beat(
            role="Verifier",
            body=[
                L("Exit code 1", mono=True),
                L(f"“off-nadir angle {MARK}30.041 deg{MARK} exceeds sensor max 30.000 deg”", mono=True),
                L(f"“… {MARK}30.349{MARK}, {MARK}30.291{MARK}, {MARK}30.157{MARK}, {MARK}30.279{MARK}, {MARK}30.567{MARK} …”", mono=True),
            ],
        ),
        Beat(
            role="Thought",
            body=[
                L(f"“The errors are from {MARK}slight propagation / rotation mismatches{MARK}. Let me use {MARK}brahe's propagator directly{MARK} for precision.”"),
            ],
        ),
        Beat(
            role="Verifier",
            role_note="after the rewrite, 20 satellites",
            body=[
                L("Mean capped gap:   6.000 h     worst per-target: 4.66 h", mono=True),
                L(f"“The solution is {MARK}valid with 0 errors{MARK}.”"),
            ],
        ),
        Beat(
            role="Verifier",
            role_note="after pruning the constellation",
            body=[
                L(f"{MARK}Valid: True{MARK}    Score: 6.0    Max gap: 5.933 h    {MARK}Satellites: 10{MARK}", mono=True),
            ],
        ),
    ],
)


PANEL_C = Panel(
    label="C",
    title="Case-adaptive search",
    subtitle="Codex CLI · GPT-5.4   on   Relay Constellation, case_0003",
    task=(
        f"Place up to {MARK}8 relay satellites{MARK} so all 5 customer-demand windows are fully served. "
        f"Hard ceiling on satellite altitude: {MARK}1500 km{MARK}."
    ),
    beats=[
        Beat(
            role="Decision",
            body=[
                L(f"“Create an {MARK}empty but valid{MARK} solution.json first, then iterate with {MARK}the verifier{MARK} to improve service.”"),
            ],
        ),
        Beat(
            role="Reads",
            role_note="verifier diagnostic on the backbone alone",
            body=[
                L("demand_002, demand_004, demand_005   →   fully served", mono=True),
                L(f"{MARK}demand_001    30 / 60    (0.50){MARK}", mono=True),
                L(f"{MARK}demand_003    76 / 90    (0.84){MARK}", mono=True),
            ],
        ),
        Beat(
            role="Decision",
            body=[
                L(f"“Misses come from {MARK}brief disconnected periods{MARK} in the ISL graph. Build {MARK}per-minute feasible paths{MARK}, then a {MARK}focused candidate search{MARK}.”"),
            ],
        ),
        Beat(
            role="Verifier",
            body=[
                L("Exit code 1", mono=True),
                L(f"\"apogee_altitude_m\":  {MARK}1 500 000.0000000047{MARK}    (ceiling = 1 500 000.0)", mono=True),
            ],
        ),
        Beat(
            role="Decision",
            body=[
                L(f"“{MARK}Hard-boundary issue{MARK}, not structural — rounded a few {MARK}nanometers high{MARK}. Move the candidate shell slightly below the cap and rerun.”"),
            ],
        ),
        Beat(
            role="Verifier",
            body=[
                L(f"{MARK}service_fraction = 1.0{MARK}    {MARK}mean_latency_ms = 96.077{MARK}    {MARK}2 added relays{MARK}", mono=True),
            ],
        ),
    ],
)


# -------------------------------------------------------------------------
# Layout
# -------------------------------------------------------------------------

PANEL_W = 780
GUTTER = 20
SIDE_PAD = 28
TOP_PAD = 14
BOTTOM_PAD = 18

HEADER_BAR_H = 4
HEADER_BAR_GAP = 8
SUBTITLE_GAP = 6
HEADER_GAP_BELOW = 16

TASK_PAD_Y = 13
TASK_PAD_X = 16
TASK_GAP_BELOW = 14

BEAT_GAP = 10
INTRA_LINE_GAP = 4
DIVIDER_GAP = 6

ROLE_GAP = 6   # gap between "Role:" prefix and body

FS_TITLE = 22
FS_SUBTITLE = 13
FS_TASK_LABEL = 12
FS_TASK = 16
FS_ROLE = 15
FS_ROLE_NOTE = 12
FS_BODY = 15
FS_BODY_MONO = 13


def load_fonts() -> dict:
    return {
        "title": ImageFont.truetype(FONT_BOLD, FS_TITLE),
        "subtitle": ImageFont.truetype(FONT_REGULAR, FS_SUBTITLE),
        "task_label": ImageFont.truetype(FONT_BOLD, FS_TASK_LABEL),
        "task": ImageFont.truetype(FONT_ITALIC, FS_TASK),
        "task_bold": ImageFont.truetype(FONT_BOLD_ITALIC, FS_TASK),
        "role": ImageFont.truetype(FONT_BOLD, FS_ROLE),
        "role_note": ImageFont.truetype(FONT_ITALIC, FS_ROLE_NOTE),
        "body": ImageFont.truetype(FONT_REGULAR, FS_BODY),
        "body_bold": ImageFont.truetype(FONT_BOLD, FS_BODY),
        "mono": ImageFont.truetype(FONT_MONO, FS_BODY_MONO),
        "mono_bold": ImageFont.truetype(FONT_MONO_BOLD, FS_BODY_MONO),
    }


def measure(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def line_h(draw, font):
    _, h = measure(draw, "Agpqj│", font)
    return h


def render_marked(
    draw,
    x,
    y,
    line,
    *,
    regular,
    bold,
    fg=TEXT_FG,
    highlight_bg=HIGHLIGHT_BG,
):
    """Render `line` with ▌highlight▌ spans. Returns final x (right edge)."""
    if not line:
        return x
    if MARK not in line:
        draw.text((x, y), line, font=regular, fill=fg)
        bbox = draw.textbbox((x, y), line, font=regular)
        return bbox[2]
    cursor = x
    segments = line.split(MARK)
    for idx, seg in enumerate(segments):
        if seg == "":
            continue
        font = bold if (idx % 2 == 1) else regular
        seg_bbox = draw.textbbox((cursor, y), seg, font=font)
        if idx % 2 == 1:
            draw.rectangle(
                (seg_bbox[0] - 3, seg_bbox[1] - 2, seg_bbox[2] + 3, seg_bbox[3] + 2),
                fill=highlight_bg,
            )
        draw.text((cursor, y), seg, font=font, fill=fg)
        cursor = seg_bbox[2]
    return cursor


def wrap(draw, text, font, max_w):
    """Word-wrap `text` (with ▌markers) into lines fitting in max_w."""
    if not text:
        return [""]
    words = text.split(" ")
    lines = []
    cur = ""
    for word in words:
        candidate = (cur + " " + word) if cur else word
        visible = candidate.replace(MARK, "")
        w, _ = measure(draw, visible, font)
        if w <= max_w or not cur:
            cur = candidate
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def wrap_after_prefix(draw, text, prefix_w, regular, max_w):
    """Wrap `text` (with ▌markers) so the first line starts at prefix_w
    and subsequent lines start at 0 (i.e. the body column edge)."""
    if not text:
        return [(0, "")]
    words = text.split(" ")
    out = []
    first = True
    cur = ""
    cur_start = prefix_w
    for word in words:
        candidate = (cur + " " + word) if cur else word
        visible = candidate.replace(MARK, "")
        w, _ = measure(draw, visible, regular)
        avail = max_w - (cur_start if first else 0)
        if w <= avail or not cur:
            cur = candidate
        else:
            out.append((cur_start, cur))
            cur = word
            cur_start = 0
            first = False
    if cur:
        out.append((cur_start, cur))
    return out


def render_panel(draw, panel: Panel, ox: int, oy: int, fonts: dict) -> int:
    tone = PANEL_TONE[panel.label]
    body_left = ox + SIDE_PAD
    body_right = ox + PANEL_W - SIDE_PAD
    body_w = body_right - body_left

    cur_y = oy + TOP_PAD

    # ---- Centered column header: mechanism title ----
    title = panel.title
    tw, t_h = measure(draw, title, fonts["title"])
    title_x = ox + (PANEL_W - tw) // 2
    draw.text((title_x, cur_y), title, font=fonts["title"], fill=TEXT_FG)
    cur_y += t_h + HEADER_BAR_GAP

    # Colored accent bar centered, ~60% of panel width
    bar_w = int(PANEL_W * 0.62)
    bar_x = ox + (PANEL_W - bar_w) // 2
    draw.rectangle(
        (bar_x, cur_y, bar_x + bar_w, cur_y + HEADER_BAR_H),
        fill=tone,
    )
    cur_y += HEADER_BAR_H + SUBTITLE_GAP

    # Subtitle (centered) — system + benchmark + case
    sw, sh = measure(draw, panel.subtitle, fonts["subtitle"])
    draw.text(
        (ox + (PANEL_W - sw) // 2, cur_y),
        panel.subtitle,
        font=fonts["subtitle"],
        fill=SUBTLE_FG,
    )
    cur_y += sh + HEADER_GAP_BELOW

    # ---- Task block (italic on cream bg) ----
    task_label = "TASK"
    task_label_w, task_label_h = measure(draw, task_label, fonts["task_label"])
    task_text_x = body_left + TASK_PAD_X + task_label_w + 10
    task_inner_w = body_right - TASK_PAD_X - task_text_x
    task_lines = wrap(draw, panel.task, fonts["task"], task_inner_w)
    task_line_h = line_h(draw, fonts["task"]) + INTRA_LINE_GAP
    task_box_h = TASK_PAD_Y * 2 + task_line_h * len(task_lines) - INTRA_LINE_GAP + 4
    draw.rounded_rectangle(
        (body_left, cur_y, body_right, cur_y + task_box_h),
        radius=5,
        fill=TASK_BG,
    )
    # left accent stripe
    draw.rectangle(
        (body_left, cur_y, body_left + 3, cur_y + task_box_h),
        fill=tone,
    )
    # label
    draw.text(
        (body_left + TASK_PAD_X, cur_y + TASK_PAD_Y + 2),
        task_label,
        font=fonts["task_label"],
        fill=tone,
    )
    # body
    line_y = cur_y + TASK_PAD_Y
    for tl in task_lines:
        render_marked(
            draw,
            task_text_x,
            line_y,
            tl,
            regular=fonts["task"],
            bold=fonts["task_bold"],
            fg=TASK_FG,
        )
        line_y += task_line_h
    cur_y += task_box_h + TASK_GAP_BELOW

    # ---- Beats (inline role labels) ----
    sans_h = line_h(draw, fonts["body"]) + INTRA_LINE_GAP
    mono_h = line_h(draw, fonts["mono"]) + INTRA_LINE_GAP

    for bi, beat in enumerate(panel.beats):
        # First-line prefix: bold colored "Role:" (+ italic role_note in parens)
        prefix_parts = [(beat.role + ":", fonts["role"], ROLE_COLORS[beat.role])]
        if beat.role_note:
            prefix_parts.append((f"  ({beat.role_note})", fonts["role_note"], SUBTLE_FG))

        prefix_x = body_left
        # measure total prefix width
        prefix_w_total = 0
        for txt, fnt, _ in prefix_parts:
            w, _ = measure(draw, txt, fnt)
            prefix_w_total += w
        prefix_w_total += ROLE_GAP

        # Draw prefix
        cursor = prefix_x
        for txt, fnt, color in prefix_parts:
            draw.text((cursor, cur_y), txt, font=fnt, fill=color)
            w, _ = measure(draw, txt, fnt)
            cursor += w

        # First body line follows the prefix on the same row
        line_index = 0
        body_y = cur_y
        first_line_consumed = False
        first_body_line = None
        first_body_mono = None
        for li, line in enumerate(beat.body):
            line_index = li
            first_body_line = line.text
            first_body_mono = line.mono
            break

        if first_body_line is not None:
            font_reg = fonts["mono" if first_body_mono else "body"]
            font_bold = fonts["mono_bold" if first_body_mono else "body_bold"]
            avail_first = body_right - (prefix_x + prefix_w_total)
            visible = first_body_line.replace(MARK, "")
            full_w, _ = measure(draw, visible, font_reg)
            if full_w <= avail_first:
                # Fits on same row as prefix
                render_marked(
                    draw,
                    prefix_x + prefix_w_total,
                    body_y,
                    first_body_line,
                    regular=font_reg,
                    bold=font_bold,
                )
                body_y += (mono_h if first_body_mono else sans_h)
                first_line_consumed = True
            else:
                # Wrap: prefix on its own row; first body line on next
                body_y += (mono_h if first_body_mono else sans_h)
                # Re-render first body line on its own row
                sub_lines = wrap(draw, first_body_line, font_reg, body_right - body_left)
                for sl in sub_lines:
                    render_marked(
                        draw,
                        body_left,
                        body_y,
                        sl,
                        regular=font_reg,
                        bold=font_bold,
                    )
                    body_y += (mono_h if first_body_mono else sans_h)
                first_line_consumed = True

        # Remaining body lines on their own rows
        if first_line_consumed:
            for line in beat.body[1:]:
                font_reg = fonts["mono" if line.mono else "body"]
                font_bold = fonts["mono_bold" if line.mono else "body_bold"]
                sub_lines = wrap(draw, line.text, font_reg, body_right - body_left)
                for sl in sub_lines:
                    render_marked(
                        draw,
                        body_left,
                        body_y,
                        sl,
                        regular=font_reg,
                        bold=font_bold,
                    )
                    body_y += (mono_h if line.mono else sans_h)

        cur_y = body_y + BEAT_GAP

        # Light divider between beats
        if bi < len(panel.beats) - 1:
            draw.line(
                (body_left, cur_y - BEAT_GAP // 2, body_right, cur_y - BEAT_GAP // 2),
                fill=DIVIDER,
                width=1,
            )

    cur_y += BOTTOM_PAD - BEAT_GAP

    # ---- Panel outline ----
    draw.rounded_rectangle(
        (ox, oy, ox + PANEL_W, cur_y),
        radius=5,
        outline="#D4D4D4",
        width=1,
    )

    return cur_y - oy


def main() -> None:
    fonts = load_fonts()
    panels = [PANEL_A, PANEL_B, PANEL_C]

    # Pass 1: measure each panel's height.
    measured = []
    tmp = Image.new("RGB", (PANEL_W * 3 + GUTTER * 4, 4000), "white")
    tdraw = ImageDraw.Draw(tmp)
    for i, panel in enumerate(panels):
        ox = GUTTER + i * (PANEL_W + GUTTER)
        h = render_panel(tdraw, panel, ox, GUTTER, fonts)
        measured.append(h)
    panel_h = max(measured)

    fig_w = 3 * PANEL_W + 4 * GUTTER
    fig_h = panel_h + 2 * GUTTER

    img = Image.new("RGB", (fig_w, fig_h), "white")
    draw = ImageDraw.Draw(img)
    for i, panel in enumerate(panels):
        ox = GUTTER + i * (PANEL_W + GUTTER)
        render_panel(draw, panel, ox, GUTTER, fonts)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT_PATH, "PNG", optimize=True)
    print(f"wrote {OUT_PATH}  ({fig_w}×{fig_h} px)")


if __name__ == "__main__":
    main()
