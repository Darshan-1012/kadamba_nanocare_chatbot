"""Second pass: fix stats bar values and gauge donuts in report_template.html."""
from pathlib import Path
import re

TPL = Path(r"app/frontend/template/report_template.html")
html = TPL.read_text(encoding="utf-8")

# ── Stats bar: replace hardcoded values ──────────────────────────────
replacements = [
    ('>73.1 kg<', '>{{ metrics.weight }} kg<'),
    ('>25.8<',    '>{{ metrics.bmi }}<'),
    ('>65<',      '>{{ metrics.heartRate }}<'),
    ('>57 J<',    '>{{ metrics.bioEnergy }} J<'),
    ('>87 %<',    '>{{ metrics.energyReserve }} %<'),
    ('>2.97<',    '>{{ metrics.lfhfRatio }}<'),
    ('>64 bpm<',  '>{{ metrics.nadiPulse }} bpm<'),
]

# Only replace within stat__val spans (first occurrence only for safety)
for old, new in replacements:
    html = html.replace(old, new, 1)

# Fix visceral fat (the value "9" is too generic, target the exact context)
html = html.replace(
    'stat__val">9</span>',
    'stat__val">{{ metrics.visceralFat|default("--") }}</span>',
    1
)

# ── Gauge donuts: replace 60% and dashoffset 42.7 ────────────────────
# There are exactly 4 gauge-svg-wrap blocks, in order: Physical, Psychological, Emotional, Spiritual
dims = ['physical', 'psychological', 'emotional', 'spiritual']
gauge_pattern = re.compile(
    r'(aria-label=")[^"]+("\s*>\s*<svg[^>]*>\s*'
    r'<circle class="g-track"[^/]*/>\s*'
    r'<circle class="g-fill[^"]*"[^>]*stroke-dasharray="106\.8"\s*'
    r'stroke-dashoffset=")[\d.]+("[^/]*/>\s*'
    r'</svg>\s*<div class="gauge-pct">)[^<]+(</div>)',
    re.DOTALL
)

dim_idx = [0]  # mutable counter for closure
def gauge_replacer(m):
    i = dim_idx[0]
    dim = dims[i] if i < len(dims) else 'unknown'
    dim_idx[0] = i + 1
    score_expr = f'dimensions.{dim}.score'
    offset_expr = f'{{{{ (106.8 * (1 - {score_expr} / 100))|round(1) }}}}'
    pct_expr = f'{{{{ {score_expr} }}}}%'
    label = f'{dim.capitalize()} {{{{ {score_expr} }}}}%'
    return (
        m.group(1) + label + m.group(2) + offset_expr + m.group(3) + pct_expr + m.group(4)
    )

html = gauge_pattern.sub(gauge_replacer, html)

# ── Summary card bodies ──────────────────────────────────────────────
# Physical summary (top-left, card__hd--lr)
html = html.replace(
    'card__hd--lr"><span class="card__hd-title">Summary</span></div>\r\n            <div class="card__body"></div>\r\n          </div>\r\n          <div></div><!-- empty center',
    'card__hd--lr"><span class="card__hd-title">Physical Summary</span></div>\r\n            <div class="card__body"><p style="font-size:7.5pt;color:#333;line-height:1.5;">{{ dimensions.physical.description|default("") }}</p></div>\r\n          </div>\r\n          <div></div><!-- empty center',
    1
)

# Psychological summary (top-right, card__hd--db, first occurrence)
html = html.replace(
    'card__hd--db"><span class="card__hd-title">Summary</span></div>\r\n            <div class="card__body"></div>\r\n          </div>\r\n        </div>',
    'card__hd--db"><span class="card__hd-title">Psychological Summary</span></div>\r\n            <div class="card__body"><p style="font-size:7.5pt;color:#333;line-height:1.5;">{{ dimensions.psychological.description|default("") }}</p></div>\r\n          </div>\r\n        </div>',
    1
)

# Emotional summary (bottom-left, second card__hd--db)
html = html.replace(
    'card__hd--db"><span class="card__hd-title">Summary</span></div>\r\n            <div class="card__body"></div>\r\n          </div>\r\n          <div></div><!-- empty center',
    'card__hd--db"><span class="card__hd-title">Emotional Summary</span></div>\r\n            <div class="card__body"><p style="font-size:7.5pt;color:#333;line-height:1.5;">{{ dimensions.emotional.description|default("") }}</p></div>\r\n          </div>\r\n          <div></div><!-- empty center',
    1
)

# Spiritual summary (card__hd--gr)
html = html.replace(
    'card__hd--gr"><span class="card__hd-title">Chakras biowell</span></div>\r\n            <div class="card__body"></div>',
    'card__hd--gr"><span class="card__hd-title">Spiritual Summary</span></div>\r\n            <div class="card__body"><p style="font-size:7.5pt;color:#333;line-height:1.5;">{{ dimensions.spiritual.description|default("") }}</p></div>',
    1
)

# ── Page 5: Wellness card bodies ─────────────────────────────────────
wellness_cards = [
    ("Diet",              "diet"),
    ("Yoga therapy",      "yoga"),
    ("Physical activity", "physicalActivity"),
    ("Sleep",             "sleep"),
    ("Stress",            "stress"),
    ("Supplements",       "supplements"),
    ("Medicine",          "medicine"),
]
for title, key in wellness_cards:
    html = html.replace(
        f'card__hd-title">{title}</span></div>\r\n          <div class="off-card__body"></div>',
        f'card__hd-title">{title}</span></div>\r\n          <div class="off-card__body"><p style="font-size:8pt;color:#333;line-height:1.6;">{{{{ wellness.{key}|default("") }}}}</p></div>',
        1
    )

TPL.write_text(html, encoding="utf-8")
print(f"[OK] Second pass complete. Size: {len(html)} bytes")

# Verify replacements
checks = ['metrics.weight', 'metrics.bmi', 'metrics.heartRate', 
          'dimensions.physical.score', 'dimensions.psychological.score',
          'systems.nervous.score', 'wellness.diet']
for c in checks:
    if c in html:
        print(f"  [v] {c}")
    else:
        print(f"  [x] MISSING: {c}")
