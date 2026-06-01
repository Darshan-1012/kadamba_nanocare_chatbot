"""Convert the static Figma HTML template into a Jinja2 template.

Reads new_figma_template.html, replaces hardcoded values with Jinja2
placeholders, fixes image paths to file:/// URIs, and writes to
report_template.html.
"""
import re
from pathlib import Path

SRC = Path(r"app/frontend/template/new_figma_template.html")
DST = Path(r"app/frontend/template/report_template.html")
STATIC = Path(r"app/frontend/static").resolve().as_posix()

html = SRC.read_text(encoding="utf-8")

# ── Fix image paths: absolute Windows → file:/// URIs ────────────────
# Match src="E:\...\something.svg" or src="E:/..."
def fix_img_path(m):
    raw = m.group(1)
    # Normalize to forward slashes
    p = raw.replace("\\", "/")
    # Convert to file:/// URI
    if not p.startswith("file:///"):
        p = "file:///" + p
    return f'src="{p}"'

html = re.sub(r'src="(E:[^"]+)"', fix_img_path, html)

# ── PAGE 1: Patient info in ALL headers ──────────────────────────────
# Replace all occurrences of hardcoded patient name/age/ID
html = html.replace(
    'Patient Name:&nbsp;<strong>Albertoo</strong><br>Age:&nbsp;<strong>67</strong><br>Patient\n        ID:&nbsp;<strong>123456789</strong>',
    'Patient Name:&nbsp;<strong>{{ patient.name }}</strong><br>Age:&nbsp;<strong>{{ patient.age }}</strong><br>Patient\n        ID:&nbsp;<strong>{{ patient.id|default("—") }}</strong>'
)
# Also catch any single-line variants
html = html.replace(
    'Patient Name:&nbsp;<strong>Albertoo</strong>',
    'Patient Name:&nbsp;<strong>{{ patient.name }}</strong>'
)

# ── PAGE 1: Stats bar values ─────────────────────────────────────────
# Weight
html = html.replace(
    '<span class="stat__val">73.1 kg</span>\r\n          <span class="stat__lbl">Weight',
    '<span class="stat__val">{{ metrics.weight }} kg</span>\r\n          <span class="stat__lbl">Weight'
)
# Visceral Fat
html = html.replace(
    '<span class="stat__val">9</span>\r\n          <span class="stat__lbl">Viceral Fat Level',
    '<span class="stat__val">{{ metrics.bodyFat|default("—") }}</span>\r\n          <span class="stat__lbl">Viceral Fat Level'
)
# BMI
html = html.replace(
    '<span class="stat__val">25.8</span>\r\n          <span class="stat__lbl">BMI',
    '<span class="stat__val">{{ metrics.bmi }}</span>\r\n          <span class="stat__lbl">BMI'
)
# Heart Rate
html = html.replace(
    '<span class="stat__val">65</span>\r\n          <span class="stat__lbl">Heart Rate',
    '<span class="stat__val">{{ metrics.heartRate }}</span>\r\n          <span class="stat__lbl">Heart Rate'
)
# Bio-Energy
html = html.replace(
    '<span class="stat__val">57 J</span>\r\n          <span class="stat__lbl">Bio-Energy',
    '<span class="stat__val">{{ metrics.bioEnergy }} J</span>\r\n          <span class="stat__lbl">Bio-Energy'
)
# Energy Reserve
html = html.replace(
    '<span class="stat__val">87 %</span>\r\n          <span class="stat__lbl">Energy Reserve',
    '<span class="stat__val">{{ metrics.energyReserve }} %</span>\r\n          <span class="stat__lbl">Energy Reserve'
)
# LF/HF
html = html.replace(
    '<span class="stat__val">2.97</span>\r\n          <span class="stat__lbl">LF/HF',
    '<span class="stat__val">{{ metrics.lfhfRatio }}</span>\r\n          <span class="stat__lbl">LF/HF'
)
# Nadi Pulse
html = html.replace(
    '<span class="stat__val">64 bpm</span>\r\n          <span class="stat__lbl">Nadi Pulse',
    '<span class="stat__val">{{ metrics.nadiPulse }} bpm</span>\r\n          <span class="stat__lbl">Nadi Pulse'
)

# ── PAGE 1: Gauge donuts (4 dimensions) ──────────────────────────────
# Physical gauge (top-left) - score and dashoffset
# circumference = 2*pi*17 = 106.8
# dashoffset = 106.8 * (1 - score/100)
CIRC = 106.8

# Replace all four gauge sections with Jinja2
# Physical (top-left, g-fill--lr)
html = html.replace(
    'aria-label="Physical 60%">\r\n              <svg viewBox="0 0 42 42" aria-hidden="true">\r\n                <circle class="g-track" cx="21" cy="21" r="17" />\r\n                <circle class="g-fill g-fill--lr" cx="21" cy="21" r="17" stroke-dasharray="106.8"\r\n                  stroke-dashoffset="42.7" />\r\n              </svg>\r\n              <div class="gauge-pct">60%</div>',
    'aria-label="Physical {{ dimensions.physical.score }}%">\r\n              <svg viewBox="0 0 42 42" aria-hidden="true">\r\n                <circle class="g-track" cx="21" cy="21" r="17" />\r\n                <circle class="g-fill g-fill--lr" cx="21" cy="21" r="17" stroke-dasharray="106.8"\r\n                  stroke-dashoffset="{{ 106.8 * (1 - dimensions.physical.score / 100) }}" />\r\n              </svg>\r\n              <div class="gauge-pct">{{ dimensions.physical.score }}%</div>'
)

# Psychological (top-right, g-fill--rl)
html = html.replace(
    'aria-label="Psychological 60%">\r\n              <svg viewBox="0 0 42 42" aria-hidden="true">\r\n                <circle class="g-track" cx="21" cy="21" r="17" />\r\n                <circle class="g-fill g-fill--rl" cx="21" cy="21" r="17" stroke-dasharray="106.8"\r\n                  stroke-dashoffset="42.7" />\r\n              </svg>\r\n              <div class="gauge-pct">60%</div>',
    'aria-label="Psychological {{ dimensions.psychological.score }}%">\r\n              <svg viewBox="0 0 42 42" aria-hidden="true">\r\n                <circle class="g-track" cx="21" cy="21" r="17" />\r\n                <circle class="g-fill g-fill--rl" cx="21" cy="21" r="17" stroke-dasharray="106.8"\r\n                  stroke-dashoffset="{{ 106.8 * (1 - dimensions.psychological.score / 100) }}" />\r\n              </svg>\r\n              <div class="gauge-pct">{{ dimensions.psychological.score }}%</div>'
)

# Emotional (bottom-left, g-fill--lr)
html = html.replace(
    'aria-label="Emotional 60%">\r\n              <svg viewBox="0 0 42 42" aria-hidden="true">\r\n                <circle class="g-track" cx="21" cy="21" r="17" />\r\n                <circle class="g-fill g-fill--lr" cx="21" cy="21" r="17" stroke-dasharray="106.8"\r\n                  stroke-dashoffset="42.7" />\r\n              </svg>\r\n              <div class="gauge-pct">60%</div>',
    'aria-label="Emotional {{ dimensions.emotional.score }}%">\r\n              <svg viewBox="0 0 42 42" aria-hidden="true">\r\n                <circle class="g-track" cx="21" cy="21" r="17" />\r\n                <circle class="g-fill g-fill--lr" cx="21" cy="21" r="17" stroke-dasharray="106.8"\r\n                  stroke-dashoffset="{{ 106.8 * (1 - dimensions.emotional.score / 100) }}" />\r\n              </svg>\r\n              <div class="gauge-pct">{{ dimensions.emotional.score }}%</div>'
)

# Spiritual (bottom-right, g-fill--rl)
html = html.replace(
    'aria-label="Spiritual 60%">\r\n              <svg viewBox="0 0 42 42" aria-hidden="true">\r\n                <circle class="g-track" cx="21" cy="21" r="17" />\r\n                <circle class="g-fill g-fill--rl" cx="21" cy="21" r="17" stroke-dasharray="106.8"\r\n                  stroke-dashoffset="42.7" />\r\n              </svg>\r\n              <div class="gauge-pct">60%</div>',
    'aria-label="Spiritual {{ dimensions.spiritual.score }}%">\r\n              <svg viewBox="0 0 42 42" aria-hidden="true">\r\n                <circle class="g-track" cx="21" cy="21" r="17" />\r\n                <circle class="g-fill g-fill--rl" cx="21" cy="21" r="17" stroke-dasharray="106.8"\r\n                  stroke-dashoffset="{{ 106.8 * (1 - dimensions.spiritual.score / 100) }}" />\r\n              </svg>\r\n              <div class="gauge-pct">{{ dimensions.spiritual.score }}%</div>'
)

# ── PAGE 1: Summary card bodies ──────────────────────────────────────
# Top-left card (Physical summary) - card__hd--lr
html = html.replace(
    '<div class="card__hd card__hd--lr"><span class="card__hd-title">Summary</span></div>\r\n            <div class="card__body"></div>\r\n          </div>\r\n          <div></div><!-- empty center',
    '<div class="card__hd card__hd--lr"><span class="card__hd-title">Physical Summary</span></div>\r\n            <div class="card__body"><p style="font-size:7.5pt;color:#333;line-height:1.5;">{{ dimensions.physical.description }}</p></div>\r\n          </div>\r\n          <div></div><!-- empty center'
)

# Top-right card (Psychological summary) - card__hd--db
html = html.replace(
    '<div class="card__hd card__hd--db"><span class="card__hd-title">Summary</span></div>\r\n            <div class="card__body"></div>\r\n          </div>\r\n        </div>',
    '<div class="card__hd card__hd--db"><span class="card__hd-title">Psychological Summary</span></div>\r\n            <div class="card__body"><p style="font-size:7.5pt;color:#333;line-height:1.5;">{{ dimensions.psychological.description }}</p></div>\r\n          </div>\r\n        </div>',
    1  # only first occurrence
)

# Bottom-left card (Emotional summary) - first card__hd--db in bot row
html = html.replace(
    '<!-- Bottom cards -->\r\n        <div class="quad-cards-row quad-cards-row--bot">\r\n          <div class="summary-card">\r\n            <div class="card__hd card__hd--db"><span class="card__hd-title">Summary</span></div>\r\n            <div class="card__body"></div>',
    '<!-- Bottom cards -->\r\n        <div class="quad-cards-row quad-cards-row--bot">\r\n          <div class="summary-card">\r\n            <div class="card__hd card__hd--db"><span class="card__hd-title">Emotional Summary</span></div>\r\n            <div class="card__body"><p style="font-size:7.5pt;color:#333;line-height:1.5;">{{ dimensions.emotional.description }}</p></div>'
)

# Bottom-right card (Spiritual/Chakras) - card__hd--gr
html = html.replace(
    '<div class="card__hd card__hd--gr"><span class="card__hd-title">Chakras biowell</span></div>\r\n            <div class="card__body"></div>',
    '<div class="card__hd card__hd--gr"><span class="card__hd-title">Spiritual Summary</span></div>\r\n            <div class="card__body"><p style="font-size:7.5pt;color:#333;line-height:1.5;">{{ dimensions.spiritual.description }}</p></div>'
)

# ── PAGE 2: Body systems — replace all 10 hardcoded 45% with dynamic values ──
SYSTEMS_MAP = [
    ("Nervous system",        "nervous"),
    ("Cardiovascular system", "cardiovascular"),
    ("Respiratory system",    "respiratory"),
    ("Muscle and bone",       "musculoskeletal"),
    ("Digestive system",      "digestive"),
    ("Integumentary system",  "integumentary"),
    ("Endocrine system",      "endocrine"),
    ("Urogenital system",     "urogenital"),
    ("Reproductive system",   "reproductive"),
    ("Immune system",         "immune"),
]

for title, key in SYSTEMS_MAP:
    # Replace the score percentage
    old_block = f'<p class="sys-card__title">{title}</p>'
    # Find the block and replace the 45% and status text
    pattern = (
        rf'(<p class="sys-card__title">{re.escape(title)}</p>\s*'
        rf'<div class="sys-card__info">.*?'
        rf'<span class="sys-card__pct">)45(%</span>\s*'
        rf'<span class="sys-card__stat">)Normal / need attention(</span>)'
    )
    replacement = (
        rf'\g<1>{{{{ systems.{key}.score }}}}\g<2>'
        rf'{{{{ systems.{key}.displayStatus|default(systems.{key}.status) }}}}\g<3>'
    )
    html = re.sub(pattern, replacement, html, flags=re.DOTALL)

# ── PAGE 5: Wellness offerings card bodies ───────────────────────────
WELLNESS_CARDS = [
    ("Diet",              "diet"),
    ("Yoga therapy",      "yoga"),
    ("Physical activity", "physicalActivity"),
    ("Sleep",             "sleep"),
    ("Stress",            "stress"),
    ("Supplements",       "supplements"),
    ("Medicine",          "medicine"),
]

for title, key in WELLNESS_CARDS:
    html = html.replace(
        f'<span class="card__hd-title">{title}</span></div>\r\n          <div class="off-card__body"></div>',
        f'<span class="card__hd-title">{title}</span></div>\r\n          <div class="off-card__body"><p style="font-size:8pt;color:#333;line-height:1.6;">{{{{ wellness.{key}|default("—") }}}}</p></div>'
    )

# ── Write output ─────────────────────────────────────────────────────
DST.write_text(html, encoding="utf-8")
print(f"[OK] Jinja2 template written to {DST}")
print(f"   Size: {len(html)} bytes")
