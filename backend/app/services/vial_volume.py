"""
services/vial_volume.py — guard against wrong starting volumes.

Most reagents ship in a fixed fill volume per catalogue number. Starting volumes
typed in by hand at receipt / vial opening were a source of forecast error (a
wrong starting volume shifts every later "remaining" figure by the same amount,
until the lot is physically verified).

Rule, applied at every point a starting volume enters the system:
  * Antibody has a standard vial volume (antibody master):
      - nothing entered            -> standard volume used
      - entered == standard (±tol) -> standard volume used
      - entered != standard        -> rejected unless a reason is given; with a
                                      reason it is accepted and an audit note
                                      is returned for the lot record
  * No standard volume set -> the entered volume is required (> 0).

Decoupled from FastAPI: raises ValueError.
"""

from typing import Optional, Tuple

from app.models import Antibody

TOLERANCE_UL = 0.5
OVERRIDE_TAG = "[VOLUME OVERRIDE]"
CORRECTION_TAG = "[VOLUME CORRECTED]"
MAX_VIAL_UL = 20000.0


def _fmt(v: float) -> str:
    return f"{v:g}"


def validate_master_volume(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    if v <= 0 or v > MAX_VIAL_UL:
        raise ValueError(f"Vial volume must be between 0 and {_fmt(MAX_VIAL_UL)} µl")
    return float(v)


def resolve_vial_volume(
    ab: Antibody,
    entered: Optional[float],
    override_reason: Optional[str] = None,
) -> Tuple[float, Optional[str]]:
    """Return (volume to record, audit note or None)."""
    standard = ab.vial_volume_ul
    reason = (override_reason or "").strip()

    if entered is not None and entered <= 0:
        raise ValueError("Vial volume must be greater than 0 µl")

    if standard is None:
        if entered is None:
            raise ValueError(
                f"Enter the vial volume for {ab.name} — no standard vial volume is set "
                "in the antibody master."
            )
        return float(entered), None

    if entered is None or abs(entered - standard) <= TOLERANCE_UL:
        return float(standard), None

    if not reason:
        cat = f" (cat. {ab.catalog_no})" if ab.catalog_no else ""
        raise ValueError(
            f"{ab.name}{cat}: the standard vial volume is {_fmt(standard)} µl but "
            f"{_fmt(entered)} µl was entered. Use the standard volume, or give a reason "
            "for the different volume."
        )
    note = f"{OVERRIDE_TAG} standard {_fmt(standard)} µl, recorded {_fmt(entered)} µl — {reason}"
    return float(entered), note[:1024]


def append_note(existing: Optional[str], note: Optional[str], limit: int = 1024) -> Optional[str]:
    if not note:
        return existing
    merged = f"{existing} | {note}" if existing else note
    return merged[-limit:] if len(merged) > limit else merged


def is_overridden(notes: Optional[str]) -> bool:
    return bool(notes) and OVERRIDE_TAG in notes
