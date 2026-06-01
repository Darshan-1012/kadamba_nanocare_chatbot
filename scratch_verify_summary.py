"""Quick verification: render HTML and check summaries appear."""
import json
from app.output.html_renderer import render_html

d = json.load(open(r'reports\3d05a97255e27404\report.json', 'r', encoding='utf-8'))
html = render_html(d)

# Write the rendered HTML for visual inspection
with open('test_summary_check.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("=== Dimensions in report.json ===")
for dim in ['physical', 'psychological', 'emotional', 'spiritual']:
    desc = d['dimensions'][dim]['description']
    print(f"  {dim}: {desc[:100]}...")

# Check if descriptions appear in rendered HTML
print("\n=== Checking rendered HTML ===")
for dim in ['physical', 'psychological', 'emotional', 'spiritual']:
    desc_snippet = d['dimensions'][dim]['description'][:40]
    found = desc_snippet in html
    print(f"  {dim} description in HTML: {'YES' if found else 'NO'}")

print("\nDone! Check test_summary_check.html in browser.")
