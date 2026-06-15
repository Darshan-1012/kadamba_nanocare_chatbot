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
        "%Y-%m-%d",    # 2026-06-18
        "%d/%m/%Y",    # 18/06/2026
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

        day_data = {
            "day": day_num,
            "physical": {"state": p_state, "value": round(p_val, 2)},
            "emotional": {"state": e_state, "value": round(e_val, 2)},
            "intellectual": {"state": i_state, "value": round(i_val, 2)},
        }
        days.append(day_data)

        # Identify watch-out days (all same extreme state)
        states = [p_state, e_state, i_state]
        if states.count("hypo") >= 2:
            watch_days.append({
                "day": day_num,
                "type": "caution",
                "label": f"Day {day_num}: Multiple cycles low",
                "advice": "Rest day — avoid major decisions and heavy exertion.",
                "physical": RULES["physical"][p_state],
                "emotional": RULES["emotional"][e_state],
                "intellectual": RULES["intellectual"][i_state],
            })
        elif states.count("hyper") == 3:
            watch_days.append({
                "day": day_num,
                "type": "peak",
                "label": f"Day {day_num}: All cycles peak",
                "advice": "Peak performance day — tackle challenging tasks.",
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
        "rules": RULES,
    }


def build_biorhythm_calendar(
    patient_data: dict,
    biowell_raw: str = "",
) -> Optional[dict]:
    """Entry point: build the monthly biorhythm calendar from patient data.

    Tries, in order:
      1. Parse biorhythm month from BioWell raw text
      2. Fall back to report date month
      3. Fall back to current month

    DOB is approximated from patient.age + patient.date.

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

    # 1. Try BioWell raw text
    if biowell_raw:
        target_month = _parse_biorhythm_month(biowell_raw)
        if target_month:
            log.info(f"Biorhythm month from BioWell: {target_month}")

    # 2. Fall back to report date
    if not target_month:
        report_date = _parse_date_string(report_date_str)
        if report_date:
            target_month = report_date.replace(day=1)
            log.info(f"Biorhythm month from report date: {target_month}")

    # 3. Fall back to today
    if not target_month:
        target_month = date.today().replace(day=1)
        log.info(f"Biorhythm month fallback to current: {target_month}")

    return compute_month_calendar(dob, target_month)
