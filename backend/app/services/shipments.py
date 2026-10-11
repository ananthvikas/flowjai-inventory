"""
services/shipments.py — shipment-to-shipment verification.

Trigger rule
------------
When an antibody is received under shipment S, a verification is raised if the
lab already holds (or has held) stock of that antibody from a DIFFERENT
shipment — tagged with another ID, or legacy stock with no shipment ID at all.
The first-ever receipt of an antibody raises nothing: there is no previous
shipment to compare against (that is new-reagent validation, a separate
process).

One verification per (antibody, shipment): receiving more vials under the same
shipment ID, or opening vials from it, never raises a second one.

The clock starts when the receipt is recorded (not the typed received date, which
may be back-dated) and runs for VERIFICATION_WINDOW_HOURS.

Evidence files live under <data dir>/uploads/shipment_verifications/<id>/ —
next to the database, so the existing "keep the data folder" upgrade and backup
advice covers them.

Deliberately decoupled from FastAPI: takes a Session, raises ValueError.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, List, Optional, Tuple

from sqlmodel import Session, select

from app.models import (
    Alert, Antibody, ShipmentVerification, ShipmentVerificationAttachment,
    StockLot, StoreStock,
)

VERIFICATION_WINDOW_HOURS = 48
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp",
    ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".fcs",
}
ATTACHMENT_ROLES = ("previous", "new")
OUTCOMES = ("acceptable", "not_acceptable")


def normalise_shipment_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = value.strip()
    return v or None


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------

def find_previous_stock(
    antibody_id: int,
    new_shipment_id: str,
    received: date,
    session: Session,
) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """
    Most recent stock of this antibody that did NOT come in `new_shipment_id`,
    received on or before `received`. Returns (shipment_id, lot_no) — shipment_id
    may be None for legacy untagged stock — or None when there is no prior stock.
    """
    candidates: List[Tuple[date, int, Optional[str], Optional[str]]] = []

    for ss in session.exec(select(StoreStock).where(StoreStock.antibody_id == antibody_id)).all():
        if normalise_shipment_id(ss.shipment_id) == new_shipment_id:
            continue
        if ss.received_date and ss.received_date <= received:
            candidates.append((ss.received_date, ss.id or 0, normalise_shipment_id(ss.shipment_id), ss.lot_no))

    for lot in session.exec(select(StockLot).where(StockLot.antibody_id == antibody_id)).all():
        if normalise_shipment_id(lot.shipment_id) == new_shipment_id:
            continue
        if lot.date_received and lot.date_received <= received:
            candidates.append((lot.date_received, lot.id or 0, normalise_shipment_id(lot.shipment_id), lot.lot_no))

    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1]))
    _, _, prev_shipment, prev_lot = candidates[-1]
    return prev_shipment, prev_lot


def get_verification(antibody_id: int, shipment_id: Optional[str], session: Session) -> Optional[ShipmentVerification]:
    sid = normalise_shipment_id(shipment_id)
    if not sid:
        return None
    return session.exec(
        select(ShipmentVerification)
        .where(ShipmentVerification.antibody_id == antibody_id)
        .where(ShipmentVerification.shipment_id == sid)
    ).first()


def ensure_shipment_verification(
    *,
    antibody_id: int,
    shipment_id: Optional[str],
    lot_no: Optional[str],
    received: date,
    session: Session,
    user_id: Optional[int] = None,
) -> Tuple[Optional[ShipmentVerification], bool]:
    """
    Raise a verification for (antibody, shipment) if the rule above applies.
    Returns (verification or None, created_now). Call AFTER the new stock row has
    been added to the session; the row is excluded by its shipment ID.
    """
    sid = normalise_shipment_id(shipment_id)
    if not sid:
        return None, False

    existing = get_verification(antibody_id, sid, session)
    if existing:
        return existing, False

    prev = find_previous_stock(antibody_id, sid, received, session)
    if prev is None:
        return None, False  # first receipt of this antibody — nothing to compare
    prev_shipment, prev_lot = prev

    now = datetime.now()
    lot_changed = bool(lot_no and prev_lot and lot_no.strip() != prev_lot.strip())
    v = ShipmentVerification(
        antibody_id=antibody_id,
        shipment_id=sid,
        new_lot_no=lot_no,
        previous_shipment_id=prev_shipment,
        previous_lot_no=prev_lot,
        lot_changed=lot_changed,
        status="open",
        triggered_at=now,
        due_at=now + timedelta(hours=VERIFICATION_WINDOW_HOURS),
        triggered_by=user_id,
    )
    session.add(v)
    session.flush()

    ab = session.get(Antibody, antibody_id)
    ab_name = ab.name if ab else f"antibody {antibody_id}"
    prev_label = prev_shipment or "untagged stock"
    lot_note = f" New lot {lot_no} (previous {prev_lot})." if lot_changed else ""
    alert = Alert(
        antibody_id=antibody_id,
        alert_type="shipment_verification",
        message=(
            f"Shipment change for {ab_name}: {prev_label} → {sid}.{lot_note} "
            f"Shipment-to-shipment verification due by {v.due_at:%d %b %H:%M}."
        )[:512],
        days_remaining=VERIFICATION_WINDOW_HOURS / 24,
        triggered_at=now,
    )
    session.add(alert)
    session.flush()
    v.alert_id = alert.id
    session.add(v)
    return v, True


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def is_overdue(v: ShipmentVerification, now: Optional[datetime] = None) -> bool:
    return v.status == "open" and (now or datetime.now()) > v.due_at


def display_status(v: Optional[ShipmentVerification]) -> Optional[str]:
    """pending | overdue | acceptable | not_acceptable | None (no verification)."""
    if v is None:
        return None
    if v.status == "open":
        return "overdue" if is_overdue(v) else "pending"
    return v.outcome


def check_overdue(session: Session) -> List[Alert]:
    """Raise one overdue alert per open verification past its due time."""
    now = datetime.now()
    raised: List[Alert] = []
    open_vs = session.exec(
        select(ShipmentVerification).where(ShipmentVerification.status == "open")
    ).all()
    for v in open_vs:
        if v.overdue_alert_id or not is_overdue(v, now):
            continue
        ab = session.get(Antibody, v.antibody_id)
        hours = (now - v.due_at).total_seconds() / 3600
        alert = Alert(
            antibody_id=v.antibody_id,
            alert_type="shipment_verification_overdue",
            message=(
                f"OVERDUE: shipment verification for {ab.name if ab else v.antibody_id} "
                f"(shipment {v.shipment_id}) was due {v.due_at:%d %b %H:%M} — "
                f"{hours:.0f} h late."
            )[:512],
            days_remaining=-(hours / 24),
            triggered_at=now,
        )
        session.add(alert)
        session.flush()
        v.overdue_alert_id = alert.id
        session.add(v)
        raised.append(alert)
    return raised


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------

def close_verification(
    v: ShipmentVerification,
    *,
    outcome: str,
    comments: Optional[str],
    user_id: int,
    session: Session,
    staff_id: Optional[int] = None,
) -> ShipmentVerification:
    if v.status != "open":
        raise ValueError("Verification is already closed")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    comments = (comments or "").strip() or None
    if outcome == "not_acceptable" and not comments:
        raise ValueError("Comments are required when the new shipment is not acceptable")

    atts = session.exec(
        select(ShipmentVerificationAttachment)
        .where(ShipmentVerificationAttachment.verification_id == v.id)
    ).all()
    missing = [r for r in ATTACHMENT_ROLES if not any(a.role == r for a in atts)]
    if missing:
        raise ValueError(
            "Attach evidence for both shipments before closing — missing: "
            + ", ".join(f"{m} shipment" for m in missing)
        )

    now = datetime.now()
    v.status = "closed"
    v.outcome = outcome
    v.comments = comments
    v.closed_by = user_id
    v.closed_by_staff_id = staff_id
    v.closed_at = now
    session.add(v)

    for alert_id in (v.alert_id, v.overdue_alert_id):
        if alert_id:
            alert = session.get(Alert, alert_id)
            if alert and alert.acknowledged_at is None:
                alert.acknowledged_at = now
                alert.acknowledged_by = user_id
                session.add(alert)
    return v


# ---------------------------------------------------------------------------
# File storage
# ---------------------------------------------------------------------------

def uploads_root() -> Path:
    """<data dir>/uploads — data dir derived from the SQLite path when possible."""
    override = os.getenv("FLOWJAI_UPLOAD_DIR")
    if override:
        root = Path(override)
    else:
        url = os.getenv("DATABASE_URL", "sqlite:///./data/flowjai.db")
        if url.startswith("sqlite:///"):
            root = Path(url[len("sqlite:///"):]).resolve().parent / "uploads"
        else:
            root = Path("./data/uploads").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_attachment(
    v: ShipmentVerification,
    *,
    role: str,
    filename: str,
    content_type: Optional[str],
    stream: BinaryIO,
    user_id: int,
    session: Session,
) -> ShipmentVerificationAttachment:
    if v.status != "open":
        raise ValueError("Verification is closed — attachments can no longer be changed")
    if role not in ATTACHMENT_ROLES:
        raise ValueError(f"role must be one of {ATTACHMENT_ROLES}")
    original = Path(filename or "upload").name[:255]
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"File type '{ext or 'none'}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    rel = Path("shipment_verifications") / str(v.id) / f"{uuid.uuid4().hex}{ext}"
    dest = uploads_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ValueError(f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise ValueError("File is empty")
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    att = ShipmentVerificationAttachment(
        verification_id=v.id,
        role=role,
        original_filename=original,
        stored_filename=rel.as_posix(),
        content_type=content_type,
        size_bytes=size,
        sha256=digest.hexdigest(),
        uploaded_by=user_id,
    )
    session.add(att)
    return att


def attachment_path(att: ShipmentVerificationAttachment) -> Path:
    root = uploads_root().resolve()
    p = (root / att.stored_filename).resolve()
    if root not in p.parents:
        raise ValueError("Invalid attachment path")
    return p


def delete_attachment(att: ShipmentVerificationAttachment, session: Session) -> None:
    v = session.get(ShipmentVerification, att.verification_id)
    if v and v.status != "open":
        raise ValueError("Verification is closed — attachments can no longer be changed")
    try:
        attachment_path(att).unlink(missing_ok=True)
    except ValueError:
        pass
    session.delete(att)
