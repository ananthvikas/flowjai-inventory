"""
services/sample_flags.py — tap-to-toggle sample quality flags.

Designed for the bench tablet, where typing with gloves on is impractical: a
small fixed set of one-tap flags. Free-text detail goes in the sample comment.
Order here is the display order everywhere.
"""

from typing import Dict, List, Optional

SAMPLE_FLAGS: Dict[str, str] = {
    "fibrin": "Fibrin threads",
    "low_volume": "Low volume",
    "lyse_issue": "Lyse issue",
}


def parse_flags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    present = {c.strip() for c in raw.split(",") if c.strip()}
    return [code for code in SAMPLE_FLAGS if code in present]   # canonical order, unknowns dropped


def set_flag(raw: Optional[str], code: str, on: bool) -> Optional[str]:
    if code not in SAMPLE_FLAGS:
        raise ValueError(f"Unknown flag '{code}'. Options: {', '.join(SAMPLE_FLAGS)}")
    flags = set(parse_flags(raw))
    if on:
        flags.add(code)
    else:
        flags.discard(code)
    ordered = [c for c in SAMPLE_FLAGS if c in flags]
    return ",".join(ordered) or None


def flag_labels(raw: Optional[str]) -> List[str]:
    return [SAMPLE_FLAGS[c] for c in parse_flags(raw)]
