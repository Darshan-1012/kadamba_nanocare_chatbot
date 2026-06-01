"""PDF report generator — renders WellnessReport JSON into a styled PDF.

Matches the layout of wellness_template.pptx:
  Page 1: Header → Metrics → 4 Dimensions → 10 Body Systems
  Page 2: Wellness Offerings (Diet, Yoga, Physical Activity, Sleep, Stress,
          Supplements, Medicine)
"""
import math
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle


# ── Color palette (matching the UI) ──────────────────────────────────
CORAL = HexColor("#c47068")
TEAL = HexColor("#4a9b8e")
BG_LIGHT = HexColor("#faf9f8")
BORDER = HexColor("#e5e3e0")
TEXT_PRIMARY = HexColor("#1a1a1a")
TEXT_SECONDARY = HexColor("#6b6b6b")
TEXT_TERTIARY = HexColor("#9a9a9a")
WHITE = white

SYSTEM_COLORS = {
    "nervous": "#8b7fd4",
    "cardiovascular": "#d47f7f",
    "respiratory": "#7fbfd4",
    "musculoskeletal": "#d4b07f",
    "digestive": "#7fbd8a",
    "integumentary": "#d4c07f",
    "endocrine": "#d47fb0",
    "urogenital": "#7fc4d4",
    "reproductive": "#b0d47f",
    "immune": "#d4907f",
}

SYSTEM_LABELS = {
    "nervous": "Nervous System",
    "cardiovascular": "Cardiovascular",
    "respiratory": "Respiratory",
    "musculoskeletal": "Muscle & Bone",
    "digestive": "Digestive",
    "integumentary": "Integumentary",
    "endocrine": "Endocrine",
    "urogenital": "Urogenital",
    "reproductive": "Reproductive",
    "immune": "Immune System",
}


def generate_pdf(report: dict, output_path: str) -> str:
    """Generate a styled PDF from the wellness report dict.

    Args:
        report:      Validated WellnessReport dict.
        output_path: File path to write the PDF.

    Returns:
        The output_path for convenience.
    """
    width, height = A4
    c = canvas.Canvas(output_path, pagesize=A4)

    # ── Page 1: Overview ─────────────────────────────────────────────
    _draw_page1(c, report, width, height)

    c.showPage()

    # ── Page 2: Wellness Offerings ───────────────────────────────────
    _draw_page2(c, report, width, height)

    c.save()
    return output_path


# ─────────────────────────────────────────────────────────────────────
# PAGE 1
# ─────────────────────────────────────────────────────────────────────
def _draw_page1(c: canvas.Canvas, report: dict, w: float, h: float):
    margin = 25 * mm
    usable = w - 2 * margin
    y = h - margin

    patient = report.get("patient", {})
    metrics = report.get("metrics", {})
    dims = report.get("dimensions", {})
    systems = report.get("systems", {})

    # ── Header ───────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(TEXT_PRIMARY)
    c.drawString(margin, y, "Wellness Report")

    c.setFont("Helvetica", 10)
    c.setFillColor(TEXT_SECONDARY)
    name = patient.get("name", "Patient")
    age = patient.get("age", "")
    date = patient.get("date", "")
    c.drawRightString(w - margin, y, name)
    c.drawRightString(w - margin, y - 14, f"{age}   {date}")

    y -= 30
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(margin, y, w - margin, y)
    y -= 15

    # ── Metrics row ──────────────────────────────────────────────────
    metric_items = [
        (metrics.get("weight", 0), "kg", "Weight", "InBody"),
        (metrics.get("bodyFat", 0), "%", "Body Fat", "InBody"),
        (metrics.get("bmi", 0), "", "BMI", "InBody"),
        (metrics.get("heartRate", 0), "bpm", "Heart Rate", "ECG"),
        (metrics.get("bioEnergy", 0), "J", "Bio-Energy", "BioWell"),
        (metrics.get("energyReserve", 0), "%", "Energy Res.", "BioWell"),
        (metrics.get("lfhfRatio", 0), "", "LF/HF", "HRV"),
        (metrics.get("nadiPulse", 0), "bpm", "Nadi Pulse", "Nadi"),
    ]

    box_w = usable / 8
    box_h = 38
    for i, (val, unit, label, src) in enumerate(metric_items):
        bx = margin + i * box_w
        by = y - box_h

        # Box background
        c.setFillColor(BG_LIGHT)
        c.setStrokeColor(BORDER)
        c.roundRect(bx + 1, by, box_w - 2, box_h, 4, fill=1, stroke=1)

        # Value
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 11)
        val_str = "--"
        if val is not None:
            val_str = f"{val}" if isinstance(val, int) else f"{val:.1f}"
        c.drawCentredString(bx + box_w / 2, by + 24, f"{val_str}{unit}")

        # Label
        c.setFont("Helvetica", 6.5)
        c.setFillColor(TEXT_SECONDARY)
        c.drawCentredString(bx + box_w / 2, by + 14, label.upper())

        # Source
        c.setFont("Helvetica", 5.5)
        c.setFillColor(TEXT_TERTIARY)
        c.drawCentredString(bx + box_w / 2, by + 6, src)

    y -= box_h + 18

    # ── Dimensions section ───────────────────────────────────────────
    dim_items = [
        ("physical", "Physical"),
        ("emotional", "Emotional"),
        ("psychological", "Psychological"),
        ("spiritual", "Spiritual"),
    ]

    col_w = usable / 2
    dim_h = 48
    for i, (key, label) in enumerate(dim_items):
        dim = dims.get(key, {})
        score = dim.get("score", 0)
        desc = dim.get("description", "")

        col = i % 2
        row = i // 2
        dx = margin + col * col_w + 4
        dy = y - row * (dim_h + 8)

        # Donut chart (small)
        donut_r = 16
        donut_cx = dx + donut_r + 2
        donut_cy = dy - dim_h / 2 + 2
        _draw_donut(c, donut_cx, donut_cy, donut_r, score)

        # Label + description
        tx = dx + donut_r * 2 + 12
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(tx, dy - 10, label)

        c.setFont("Helvetica", 7)
        c.setFillColor(TEXT_SECONDARY)
        # Wrap description text
        max_chars = 55
        desc_lines = _wrap_text(desc, max_chars)
        for li, line in enumerate(desc_lines[:3]):
            c.drawString(tx, dy - 22 - li * 9, line)

    y -= 2 * (dim_h + 8) + 12

    # ── Systems section ──────────────────────────────────────────────
    c.setStrokeColor(BORDER)
    c.line(margin, y, w - margin, y)
    y -= 5

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(TEXT_PRIMARY)
    c.drawString(margin, y - 5, "Body Systems")
    y -= 20

    sys_keys = list(SYSTEM_LABELS.keys())
    cols = 5
    rows_count = 2
    cell_w = usable / cols
    cell_h = 44

    for idx, key in enumerate(sys_keys):
        col = idx % cols
        row = idx // cols

        sx = margin + col * cell_w + 2
        sy = y - row * (cell_h + 6)

        sys_data = systems.get(key, {})
        score = sys_data.get("score", 0)
        status = sys_data.get("status", "Need Attention")
        color = HexColor(SYSTEM_COLORS.get(key, "#999999"))
        label = SYSTEM_LABELS.get(key, key)
        is_normal = status == "Normal"

        # Card background
        c.setFillColor(BG_LIGHT)
        c.setStrokeColor(BORDER)
        c.roundRect(sx, sy - cell_h, cell_w - 4, cell_h, 4, fill=1, stroke=1)

        # Color circle with abbreviation
        circ_r = 10
        circ_cx = sx + circ_r + 6
        circ_cy = sy - cell_h / 2

        # Light color fill — create a light version by mixing with white
        base_hex = SYSTEM_COLORS.get(key, "#999999")
        light_color = _lighten_color(base_hex, 0.85)
        c.setFillColor(light_color)
        c.circle(circ_cx, circ_cy, circ_r, fill=1, stroke=0)
        c.setStrokeColor(color)
        c.setLineWidth(1)
        c.circle(circ_cx, circ_cy, circ_r, fill=0, stroke=1)

        # Score
        tx = sx + circ_r * 2 + 16
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(tx, sy - 14, f"{score}%")

        # Status
        c.setFont("Helvetica", 7)
        c.setFillColor(HexColor("#3d9970") if is_normal else CORAL)
        c.drawString(tx, sy - 24, status)

        # Label
        c.setFont("Helvetica", 6.5)
        c.setFillColor(TEXT_SECONDARY)
        c.drawString(tx, sy - 34, label)


# ─────────────────────────────────────────────────────────────────────
# PAGE 2
# ─────────────────────────────────────────────────────────────────────
def _draw_page2(c: canvas.Canvas, report: dict, w: float, h: float):
    margin = 25 * mm
    usable = w - 2 * margin
    y = h - margin

    patient = report.get("patient", {})
    wellness = report.get("wellness", {})

    # ── Header ───────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(TEXT_PRIMARY)
    c.drawString(margin, y, "Wellness Report")

    c.setFont("Helvetica", 10)
    c.setFillColor(TEXT_SECONDARY)
    c.drawRightString(w - margin, y, patient.get("name", "Patient"))
    c.drawRightString(w - margin, y - 14, patient.get("age", ""))

    y -= 30
    c.setStrokeColor(BORDER)
    c.line(margin, y, w - margin, y)
    y -= 20

    # ── Title ────────────────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(TEXT_PRIMARY)
    c.drawCentredString(w / 2, y, "Wellness Offerings")
    y -= 25

    # ── Wellness cards (2-column grid) ───────────────────────────────
    cards = [
        ("Diet", wellness.get("diet", "—")),
        ("Yoga Therapy", wellness.get("yoga", "—")),
        ("Physical Activity", wellness.get("physicalActivity", "—")),
        ("Sleep", wellness.get("sleep", "—")),
        ("Stress Management", wellness.get("stress", "—")),
        ("Supplements", wellness.get("supplements", "—")),
    ]

    col_w = usable / 2 - 4
    card_h = 80
    gap = 8

    for i, (title, body) in enumerate(cards):
        col = i % 2
        row = i // 2

        cx = margin + col * (col_w + gap)
        cy = y - row * (card_h + gap)

        # Card border
        c.setFillColor(WHITE)
        c.setStrokeColor(BORDER)
        c.roundRect(cx, cy - card_h, col_w, card_h, 6, fill=1, stroke=1)

        # Title bar
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(TEXT_PRIMARY)
        c.drawString(cx + 10, cy - 14, title)
        c.setStrokeColor(BORDER)
        c.line(cx + 8, cy - 20, cx + col_w - 8, cy - 20)

        # Body text (wrapped)
        c.setFont("Helvetica", 7)
        c.setFillColor(TEXT_SECONDARY)
        lines = _wrap_text(body, 48)
        for li, line in enumerate(lines[:7]):  # max 7 lines per card
            c.drawString(cx + 10, cy - 32 - li * 8.5, line)

    y -= 3 * (card_h + gap) + 10

    # ── Medicine (full-width card) ───────────────────────────────────
    med_text = wellness.get("medicine", "—")
    med_h = 80

    c.setFillColor(WHITE)
    c.setStrokeColor(BORDER)
    c.roundRect(margin, y - med_h, usable, med_h, 6, fill=1, stroke=1)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(TEXT_PRIMARY)
    c.drawString(margin + 10, y - 14, "Medicine & Ayurvedic Herbs")
    c.setStrokeColor(BORDER)
    c.line(margin + 8, y - 20, margin + usable - 8, y - 20)

    c.setFont("Helvetica", 7)
    c.setFillColor(TEXT_SECONDARY)
    lines = _wrap_text(med_text, 100)
    for li, line in enumerate(lines[:7]):
        c.drawString(margin + 10, y - 32 - li * 8.5, line)


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────
def _draw_donut(c: canvas.Canvas, cx, cy, r, score, line_w=5):
    """Draw a donut/arc chart at (cx, cy) with given radius."""
    # Background circle
    c.setStrokeColor(BORDER)
    c.setLineWidth(line_w)
    c.circle(cx, cy, r, fill=0, stroke=1)

    # Progress arc
    color = CORAL if score >= 70 else HexColor("#e89060")
    c.setStrokeColor(color)
    c.setLineWidth(line_w)

    score = max(0, min(100, score or 0))  # clamp and handle None
    extent = (score / 100) * 360
    # drawArc: x1, y1, x2, y2, startAngle, extent
    c.arc(
        cx - r, cy - r, cx + r, cy + r,
        startAng=90, extent=-extent,
    )

    # Center text
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(TEXT_PRIMARY)
    c.drawCentredString(cx, cy - 3, f"{score}%")


def _wrap_text(text, max_chars: int) -> list[str]:
    """Simple word-based text wrapping."""
    if not text or text is None:
        return ["--"]
    text = str(text)
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}" if current else word
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or ["--"]


def _lighten_color(hex_color: str, factor: float = 0.85):
    """Create a lighter version of a hex color by mixing with white."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return HexColor(f"#{r:02x}{g:02x}{b:02x}")
