"""Deterministic BioWell table parser.

Parses the "Functional/energetic condition of organs and systems" table so
Page 2 system scores use Balance% only. Energy Joules are preserved for text
interpretation, but never used as the percentage score.
"""
from __future__ import annotations

import re

from app.engine.interpretation import get_chakra_description, interpret_chakra


_TABLE_START = "Functional/energetic condition of organs and systems"
_TABLE_END_MARKERS = (
    "Very low Low Normal Increased High",
    "Bio-Well is not a medical instrument",
    "This Report is Powered by Bio-Well",
)

_SYSTEM_GROUPS = {
    "Head",
    "Cardiovascular system",
    "Respiratory system",
    "Endocrine system",
    "Musculoskeletal system",
    "Digestive system",
    "Urogenital system",
    "Nervous system",
    "Immune system",
}

_ROW_RE = re.compile(
    r"^(?P<name>.+?)\s+(?P<energy>\d+(?:\.\d+)?)\s+(?P<balance>\d+(?:\.\d+)?)$"
)
_PIPE_ROW_RE = re.compile(
    r"^\s*(?P<group>[^|]*)\|\s*(?P<organ>[^|]*)\|\s*"
    r"(?P<energy>\d+(?:\.\d+)?)\s*\|\s*(?:\d+\s*\|\s*)?"
    r"(?P<balance>\d+(?:\.\d+)?)\s*\|"
)
_CHAKRA_NAME_MAP = {
    "muladhara": {"key": "muladara", "display": "Muladara"},
    "muladara": {"key": "muladara", "display": "Muladara"},
    "svadhisthana": {"key": "swadistana", "display": "Swadistana"},
    "swadistana": {"key": "swadistana", "display": "Swadistana"},
    "manipura": {"key": "manipura", "display": "Manipura"},
    "anahata": {"key": "anahatha", "display": "Anahatha"},
    "anahatha": {"key": "anahatha", "display": "Anahatha"},
    "vishuddha": {"key": "vishudda", "display": "Vishudda"},
    "vishudda": {"key": "vishudda", "display": "Vishudda"},
    "ajna": {"key": "agna", "display": "Agna"},
    "agna": {"key": "agna", "display": "Agna"},
    "sahasrara": {"key": "sahasrara", "display": "Sahasrara"},
}

_CHAKRA_COLOR_HEX = {
    "red": "#cf3c34",
    "orange": "#f18a1b",
    "yellow": "#d6a400",
    "green": "#239b56",
    "azure": "#2d9cdb",
    "blue": "#266dd3",
    "violet": "#8e44ad",
    "magenta": "#c4459a",
    "light blue": "#2d9cdb",
}


def parse_biowell_functional_table(raw_text: str) -> dict:
    """Parse BioWell functional table rows from extracted report text.

    Returns:
        {
          "organ_energy_levels": [
            {
              "system_group": "Digestive system",
              "organ": "Liver",
              "energy_joules": 7.60,
              "balance_percent": 67.96
            }
          ]
        }
    """
    section = _extract_functional_section(raw_text)
    if not section:
        return {"organ_energy_levels": []}

    rows = _parse_plain_rows(section)
    if not rows:
        rows = _parse_pipe_rows(section)

    return {"organ_energy_levels": rows}


def parse_biowell_chakra_details(raw_text: str) -> dict:
    """Parse chakra number, color, and alignment from BioWell text."""
    details: dict[str, dict] = {}
    if not raw_text:
        return {"chakra_details": details}

    current: dict | None = None
    for raw_line in raw_text.splitlines():
        line = raw_line.strip().lstrip("|").strip()
        if not line or line == "[TABLE]" or re.fullmatch(r"\d+", line):
            continue

        if line.startswith("Number of chakra:"):
            if current and current.get("key") and current.get("alignment_percent") is not None and current.get("color"):
                details[current["key"]] = current
            number_match = re.search(r"(\d+)", line)
            current = {
                "number": int(number_match.group(1)) if number_match else 0,
                "key": "",
                "name": "",
                "energy_joules": None,
                "alignment_percent": None,
                "status": "",
                "color": "",
                "color_hex": "#5b6b79",
                "description": "",
            }
            continue

        if current is None:
            continue

        if line.startswith("Name of chakra:"):
            raw_name = line.split(":", 1)[1].strip().lower()
            mapped = _CHAKRA_NAME_MAP.get(raw_name)
            if not mapped:
                current = None
                continue
            current["key"] = mapped["key"]
            current["name"] = mapped["display"]
            current["description"] = get_chakra_description(mapped["key"])
            continue

        if not current.get("key"):
            continue

        if line.startswith("Energy:"):
            energy_match = re.search(r"(\d+(?:\.\d+)?)", line)
            if energy_match:
                current["energy_joules"] = float(energy_match.group(1))
            continue

        if line.startswith("Alignment:"):
            alignment_match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if alignment_match:
                alignment = float(alignment_match.group(1))
                current["alignment_percent"] = alignment
                current["status"] = interpret_chakra(alignment)["status"]
            continue

        if line.startswith("Color:"):
            color = line.split(":", 1)[1].strip().lower()
            current["color"] = color.title()
            current["color_hex"] = _CHAKRA_COLOR_HEX.get(color, "#5b6b79")

    if current and current.get("key") and current.get("alignment_percent") is not None and current.get("color"):
        details[current["key"]] = current

    return {"chakra_details": details}


def _extract_functional_section(raw_text: str) -> str:
    start = raw_text.find(_TABLE_START)
    if start < 0:
        return ""
    section = raw_text[start + len(_TABLE_START):]

    end_positions = [
        idx for marker in _TABLE_END_MARKERS
        if (idx := section.find(marker)) >= 0
    ]
    if end_positions:
        section = section[:min(end_positions)]
    return section


def _parse_plain_rows(section: str) -> list[dict]:
    rows = []
    current_group = ""

    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("---") or line.startswith("["):
            continue
        if "Energy, Joules" in line or "Balance" in line:
            continue
        if line.startswith("NB!"):
            continue

        match = _ROW_RE.match(line)
        if not match:
            continue

        name = match.group("name").strip()
        energy = float(match.group("energy"))
        balance = float(match.group("balance"))

        if name in _SYSTEM_GROUPS:
            current_group = name

        if not current_group:
            continue

        rows.append({
            "system_group": current_group,
            "organ": name,
            "energy_joules": energy,
            "balance_percent": balance,
        })

    return rows


def _parse_pipe_rows(section: str) -> list[dict]:
    rows = []
    current_group = ""

    for raw_line in section.splitlines():
        match = _PIPE_ROW_RE.match(raw_line)
        if not match:
            continue

        group = match.group("group").strip()
        organ = match.group("organ").strip()
        energy = float(match.group("energy"))
        balance = float(match.group("balance"))

        if group:
            current_group = group
            name = group if not organ else organ
        else:
            name = organ

        if not current_group or not name:
            continue

        rows.append({
            "system_group": current_group,
            "organ": name,
            "energy_joules": energy,
            "balance_percent": balance,
        })

    return rows
