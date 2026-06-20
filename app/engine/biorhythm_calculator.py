"""Deterministic biorhythm calendar calculator.

Computes Physical (23-day), Emotional (28-day), and Intellectual (33-day)
sine-wave cycles from patient DOB, then classifies each day of a given
month as Hyper / Neutral / Hypo with corrective advice from the clinical
rules (biorhythm.docx).

DOB derivation: if exact DOB is unavailable, it is approximated from
``patient.age`` + ``patient.date`` (report date).
"""
from __future__ import annotations

import calendar
import logging
import math
import re
from datetime import date, timedelta
from typing import Optional

log = logging.getLogger(__name__)

# ── Cycle periods (days) ─────────────────────────────────────────────
PHYSICAL_PERIOD = 23
EMOTIONAL_PERIOD = 28
INTELLECTUAL_PERIOD = 33

# ── Thresholds for Hyper / Hypo classification ───────────────────────
_HYPER_THRESHOLD = 0.30   # sin > 0.30  → Hyper
_HYPO_THRESHOLD = -0.30   # sin < -0.30 → Hypo

# ── SVG graph dimensions ─────────────────────────────────────────────
GRAPH_WIDTH = 540
GRAPH_HEIGHT = 150
GRAPH_PAD_X = 28
GRAPH_PAD_Y = 16

# ── Clinical rule table (from biorhythm.docx) ────────────────────────
RULES = {
    "physical": {
        "hyper": {
            "description": "High stamina, peak strength, fast recovery. Risk of overexertion.",
            "advice": "Do heavy workouts; schedule stretching to prevent injuries.",
        },
        "hypo": {
            "description": "Sluggishness, low immunity, slow body recovery.",
            "advice": "Sleep more; switch to light walking or gentle yoga.",
        },
        "neutral": {
            "description": "Normal energy levels, balanced physical state.",
            "advice": "Maintain regular routine; moderate exercise recommended.",
        },
    },
    "emotional": {
        "hyper": {
            "description": "Deep empathy, high creativity. Risk of anxiety or over-reacting.",
            "advice": "Channel into socializing or art; use deep breathing to ground.",
        },
        "hypo": {
            "description": "Apathy, low motivation, desire to withdraw.",
            "advice": "Say 'no' to social events; enjoy quiet, solitary hobbies.",
        },
        "neutral": {
            "description": "Stable mood, balanced emotional responses.",
            "advice": "Good time for important conversations and decisions.",
        },
    },
    "intellectual": {
        "hyper": {
            "description": "Sharp memory, fast logic. Risk of racing mind and insomnia.",
            "advice": "Solve complex problems; do a bedtime diary writing.",
        },
        "hypo": {
            "description": "Brain fog, low concentration, easily frustrated.",
            "advice": "Do easy, routine tasks; take frequent 5-minute mental breaks.",
        },
        "neutral": {
            "description": "Normal cognitive function, balanced focus.",
            "advice": "Routine work and moderate learning tasks are ideal.",
        },
    },
}

CYCLE_LABELS = {
    "physical": {"short": "P", "label": "Physical"},
    "emotional": {"short": "E", "label": "Emotional"},
    "intellectual": {"short": "I", "label": "Intellectual"},
}

STATE_LABELS = {
    "hyper": "Hyper",
    "neutral": "Neutral",
    "hypo": "Hypo",
}


def _cycle_payload(cycle: str, state: str, value: float) -> dict:
    """Return display-ready biorhythm data for a single cycle."""
    rule = RULES[cycle][state]
    labels = CYCLE_LABELS[cycle]
    return {
        "state": state,
        "state_label": STATE_LABELS[state],
        "value": round(value, 2),
        "percent": int(round(value * 100)),
        "short": labels["short"],
        "label": labels["label"],
        "description": rule["description"],
        "advice": rule["advice"],
    }


def _daily_interpretation(cycles: dict) -> dict:
    """Summarize the three cycles into one concise calendar action."""
    state_counts = {
        state: sum(1 for item in cycles.values() if item["state"] == state)
        for state in ("hyper", "neutral", "hypo")
    }
    strongest_key = max(cycles, key=lambda key: abs(cycles[key]["value"]))
    strongest = cycles[strongest_key]

    if state_counts["hyper"] == 1 and state_counts["hypo"] == 2:
        hyper_cycle = next(item for item in cycles.values() if item["state"] == "hyper")
        low_cycles = [
            item["label"].lower()
            for item in cycles.values()
            if item["state"] == "hypo"
        ]
        return {
            "type": "caution",
            "title": f"{hyper_cycle['label']} support day",
            "focus": f"{hyper_cycle['label']} high, two lows",
            "summary": (
                f"{hyper_cycle['label']} is active, while "
                f"{low_cycles[0]} and {low_cycles[1]} are in low phases."
            ),
            "action": (
                f"Use {hyper_cycle['label'].lower()} strength selectively; "
                f"keep {low_cycles[0]} and {low_cycles[1]} demands gentle."
            ),
        }
    if state_counts["hypo"] >= 2:
        return {
            "type": "caution",
            "title": "Recovery day",
            "focus": "Multiple lows",
            "summary": "Energy may feel low across more than one cycle.",
            "action": "Keep the schedule light; prioritize rest and simple tasks.",
        }
    if state_counts["hyper"] >= 2:
        return {
            "type": "peak",
            "title": "High-drive day",
            "focus": "Multiple highs",
            "summary": "More than one cycle is in an active phase.",
            "action": "Use the momentum for demanding work; add grounding breaks.",
        }
    if state_counts["neutral"] == 3:
        return {
            "type": "steady",
            "title": "Balanced day",
            "focus": "All steady",
            "summary": "Physical, emotional and intellectual cycles are balanced.",
            "action": "Maintain routine; steady work and normal exercise suit best.",
        }

    cycle_label = strongest["label"]
    state_label = strongest["state_label"]
    return {
        "type": "mixed",
        "title": f"{cycle_label} {state_label}",
        "focus": f"{cycle_label} leads",
        "summary": strongest["description"],
        "action": strongest["advice"],
    }


def _approximate_dob(age_str: str, report_date_str: str) -> Optional[date]:
    """Derive an approximate DOB from age string and report date.

    Handles formats like "21 years", "21", "21 yrs".
    Report date formats: "18 June 2026", "2026-06-18", "18/06/2026".
    """
    # Parse age
    age_match = re.search(r"(\d+)", str(age_str))
    if not age_match:
        return None
    age_years = int(age_match.group(1))

    # Parse report date
    report_date = _parse_date_string(report_date_str)
    if not report_date:
        report_date = date.today()

    # Approximate: subtract years (assume same month/day as report)
    try:
        dob = report_date.replace(year=report_date.year - age_years)
    except ValueError:
        # Feb 29 edge case
        dob = report_date.replace(year=report_date.year - age_years, day=28)

    return dob


def _parse_date_string(date_str: str) -> Optional[date]:
    """Parse common date formats to a date object."""
    if not date_str:
        return None

    from datetime import datetime

    formats = [
        "%d %B %Y",    # 18 June 2026
        "%d %b %Y",    # 18 Jun 2026
        "%d-%B-%Y",    # 18-June-2026
        "%d-%b-%Y",    # 18-Jun-2026
        "%Y-%m-%d",    # 2026-06-18
        "%d/%m/%Y",    # 18/06/2026
        "%d-%m-%Y",    # 18-06-2026
        "%B %Y",       # June 2026
        "%b %Y",       # Jun 2026
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_biorhythm_month(biowell_raw: str) -> Optional[date]:
    """Extract the biorhythm month from BioWell raw text.

    Looks for patterns like "Feb 2026" near the "Biorhythms" heading.
    Returns the first day of that month.
    """
    # Find the biorhythm section
    match = re.search(
        r"Biorhythm[s]?\s*\n\s*([A-Za-z]+\s+\d{4})",
        biowell_raw,
        re.IGNORECASE,
    )
    if match:
        month_str = match.group(1).strip()
        parsed = _parse_date_string(month_str)
        if parsed:
            return parsed.replace(day=1)

    return None


def _classify(value: float) -> str:
    """Classify a sine-wave value into hyper/hypo/neutral."""
    if value > _HYPER_THRESHOLD:
        return "hyper"
    elif value < _HYPO_THRESHOLD:
        return "hypo"
    return "neutral"


def compute_biorhythm_value(days_since_birth: int, period: int) -> float:
    """Compute the biorhythm sine value for a given cycle."""
    return math.sin(2 * math.pi * days_since_birth / period)


def _graph_y(value: float) -> float:
    """Map a biorhythm value (-1..1) to SVG Y coordinate."""
    plot_height = GRAPH_HEIGHT - (2 * GRAPH_PAD_Y)
    mid_y = GRAPH_PAD_Y + (plot_height / 2)
    return mid_y - (value * (plot_height / 2))


def _build_graph_payload(days: list[dict]) -> dict:
    """Build SVG polyline points from the same day values used by calendar."""
    num_days = len(days)
    plot_left = GRAPH_PAD_X
    plot_right = GRAPH_WIDTH - GRAPH_PAD_X
    plot_width = plot_right - plot_left

    points = {"physical": [], "emotional": [], "intellectual": []}
    x_ticks = []

    for idx, day_data in enumerate(days):
        if num_days <= 1:
            x = plot_left
        else:
            x = plot_left + (idx / (num_days - 1)) * plot_width

        day_num = day_data["day"]
        if day_num == 1 or day_num == num_days or day_num % 5 == 0:
            x_ticks.append({"day": day_num, "x": round(x, 1)})

        for cycle in ("physical", "emotional", "intellectual"):
            value = float(day_data[cycle]["value"])
            y = _graph_y(value)
            points[cycle].append(f"{x:.1f},{y:.1f}")

    return {
        "width": GRAPH_WIDTH,
        "height": GRAPH_HEIGHT,
        "plot_left": plot_left,
        "plot_right": plot_right,
        "plot_top": GRAPH_PAD_Y,
        "plot_bottom": GRAPH_HEIGHT - GRAPH_PAD_Y,
        "mid_y": round(_graph_y(0), 1),
        "points": {key: " ".join(value) for key, value in points.items()},
        "x_ticks": x_ticks,
        "y_ticks": [
            {"value": 100, "label": "+100", "y": round(_graph_y(1), 1)},
            {"value": 50, "label": "+50", "y": round(_graph_y(0.5), 1)},
            {"value": 0, "label": "0", "y": round(_graph_y(0), 1)},
            {"value": -50, "label": "-50", "y": round(_graph_y(-0.5), 1)},
            {"value": -100, "label": "-100", "y": round(_graph_y(-1), 1)},
        ],
    }


def compute_month_calendar(
    dob: date,
    target_month: date,
) -> dict:
    """Compute the biorhythm calendar for one month.

    Args:
        dob:          Patient's date of birth.
        target_month: Any date in the target month (uses year/month only).

    Returns:
        Dict with keys:
          - ``month_name``: e.g. "February 2026"
          - ``year``: int
          - ``month``: int
          - ``first_weekday``: 0=Mon … 6=Sun
          - ``num_days``: total days in month
          - ``days``: list of day dicts, each with:
              - ``day``: int (1-based)
              - ``physical``: {"state": "hyper"|"hypo"|"neutral", "value": float}
              - ``emotional``: same structure
              - ``intellectual``: same structure
          - ``watch_days``: list of notable days (all-hypo or all-hyper)
    """
    year = target_month.year
    month = target_month.month
    num_days = calendar.monthrange(year, month)[1]
    first_weekday = calendar.monthrange(year, month)[0]  # 0=Monday

    month_name = f"{calendar.month_name[month]} {year}"

    days = []
    watch_days = []

    for day_num in range(1, num_days + 1):
        current_date = date(year, month, day_num)
        days_alive = (current_date - dob).days

        p_val = compute_biorhythm_value(days_alive, PHYSICAL_PERIOD)
        e_val = compute_biorhythm_value(days_alive, EMOTIONAL_PERIOD)
        i_val = compute_biorhythm_value(days_alive, INTELLECTUAL_PERIOD)

        p_state = _classify(p_val)
        e_state = _classify(e_val)
        i_state = _classify(i_val)

        cycle_data = {
            "physical": _cycle_payload("physical", p_state, p_val),
            "emotional": _cycle_payload("emotional", e_state, e_val),
            "intellectual": _cycle_payload("intellectual", i_state, i_val),
        }
        interpretation = _daily_interpretation(cycle_data)

        day_data = {
            "day": day_num,
            "type": interpretation["type"],
            "interpretation": interpretation,
            "physical": cycle_data["physical"],
            "emotional": cycle_data["emotional"],
            "intellectual": cycle_data["intellectual"],
        }
        days.append(day_data)

        # Identify watch-out days (all same extreme state)
        states = [p_state, e_state, i_state]
        if states.count("hypo") >= 2:
            watch_days.append({
                "day": day_num,
                "type": "caution",
                "label": f"Day {day_num}: Multiple cycles low",
                "advice": interpretation["action"],
                "summary": interpretation["summary"],
                "physical": RULES["physical"][p_state],
                "emotional": RULES["emotional"][e_state],
                "intellectual": RULES["intellectual"][i_state],
            })
        elif states.count("hyper") == 3:
            watch_days.append({
                "day": day_num,
                "type": "peak",
                "label": f"Day {day_num}: All cycles peak",
                "advice": interpretation["action"],
                "summary": interpretation["summary"],
                "physical": RULES["physical"][p_state],
                "emotional": RULES["emotional"][e_state],
                "intellectual": RULES["intellectual"][i_state],
            })

    return {
        "month_name": month_name,
        "year": year,
        "month": month,
        "first_weekday": first_weekday,
        "num_days": num_days,
        "days": days,
        "watch_days": watch_days,
        "graph": _build_graph_payload(days),
        "rules": RULES,
    }


def normalize_biorhythm_calendar(calendar_data: dict) -> dict:
    """Ensure older cached calendar data has display-ready interpretations."""
    if not isinstance(calendar_data, dict):
        return calendar_data

    normalized = dict(calendar_data)
    normalized_days = []

    for original in calendar_data.get("days", []):
        if not isinstance(original, dict):
            continue

        has_display_data = (
            original.get("interpretation")
            and original.get("type")
            and all(
                isinstance(original.get(cycle), dict)
                and "percent" in original[cycle]
                for cycle in ("physical", "emotional", "intellectual")
            )
        )
        if has_display_data:
            normalized_days.append(original)
            continue

        cycle_data = {}
        for cycle in ("physical", "emotional", "intellectual"):
            raw_cycle = original.get(cycle, {}) if isinstance(original.get(cycle), dict) else {}
            try:
                value = float(raw_cycle.get("value", 0))
            except (TypeError, ValueError):
                value = 0
            state = raw_cycle.get("state") or _classify(value)
            if state not in STATE_LABELS:
                state = _classify(value)
            cycle_data[cycle] = _cycle_payload(cycle, state, value)

        interpretation = _daily_interpretation(cycle_data)
        day_data = dict(original)
        day_data.update({
            "type": interpretation["type"],
            "interpretation": interpretation,
            "physical": cycle_data["physical"],
            "emotional": cycle_data["emotional"],
            "intellectual": cycle_data["intellectual"],
        })
        normalized_days.append(day_data)

    normalized["days"] = normalized_days
    normalized["graph"] = _build_graph_payload(normalized_days)
    normalized.setdefault("rules", RULES)
    return normalized


def build_biorhythm_calendar(
    patient_data: dict,
    biowell_raw: str = "",
) -> Optional[dict]:
    """Entry point: build the monthly biorhythm calendar from patient data.

    Tries, in order:
      1. Use patient/report date month
      2. Fall back to the biorhythm month parsed from BioWell raw text
      3. Fall back to current month

    DOB is read from patient.dob first, then approximated from
    patient.age + patient.date.

    Returns:
        Calendar dict for template rendering, or None if DOB can't be derived.
    """
    age_str = patient_data.get("age", "")
    report_date_str = patient_data.get("date", "")
    dob_str = patient_data.get("dob", "")

    # Try explicit DOB first
    dob = None
    if dob_str:
        dob = _parse_date_string(dob_str)

    # Fall back to approximation from age + report date
    if not dob:
        dob = _approximate_dob(age_str, report_date_str)

    if not dob:
        log.warning("Cannot compute biorhythm calendar — no DOB or age available")
        return None

    log.info(f"Biorhythm DOB (estimated): {dob}")

    # Determine target month
    target_month = None

    # 1. Use patient/report date when supplied by the API.
    report_date = _parse_date_string(report_date_str)
    if report_date:
        target_month = report_date.replace(day=1)
        log.info(f"Biorhythm month from report date: {target_month}")

    # 2. Fall back to BioWell raw text.
    if not target_month and biowell_raw:
        target_month = _parse_biorhythm_month(biowell_raw)
        if target_month:
            log.info(f"Biorhythm month from BioWell: {target_month}")

    # 3. Fall back to today
    if not target_month:
        target_month = date.today().replace(day=1)
        log.info(f"Biorhythm month fallback to current: {target_month}")

    return compute_month_calendar(dob, target_month)
