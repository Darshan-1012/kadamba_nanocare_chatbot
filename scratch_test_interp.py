"""Quick test: apply build_interpretations to existing report.json and print results."""
import json
from app.engine.interpretation import build_interpretations

# Load existing report
with open("reports/3d05a97255e27404/report.json", "r", encoding="utf-8") as f:
    report = json.load(f)

print("=== BEFORE ===")
for dim in ["physical", "psychological", "emotional", "spiritual"]:
    desc = report.get("dimensions", {}).get(dim, {}).get("description", "")
    print(f"  {dim}: {desc[:80]}...")

# Apply interpretations (no parsed device data in this test, just metrics)
result = build_interpretations(report)

print("\n=== AFTER (deterministic) ===")
for dim in ["physical", "psychological", "emotional", "spiritual"]:
    desc = result.get("dimensions", {}).get(dim, {}).get("description", "")
    print(f"  {dim}: {desc}")

print("\n=== INTERPRETATIONS ===")
interps = result.get("interpretations", {})
for key, val in interps.items():
    print(f"  {key}: {val}")

# Save updated report
with open("reports/3d05a97255e27404/report.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print("\n[OK] Updated report.json saved")
