"""
routers/shipment_verifications.py — shipment-to-shipment verification (QC).

  GET    /api/shipment-verifications/                 list (status=open|closed|all)
  GET    /api/shipment-verifications/summary          open / overdue counts (nav badge)
  GET    /api/shipment-verifications/{id}             detail incl. attachments
  POST   /api/shipment-verifications/{id}/attachments upload evidence (multipart: file, role)
  GET    /api/shipment-verifications/attachments/{att_id}        download
  DELETE /api/shipment-verifications/attachments/{att_id}        remove (open records only)
  POST   /api/shipment-verifications/{id}/close       sign off with outcome
  GET    /api/shipment-verifications/export/log.csv   audit log
"""

import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_technologist_or_admin
from app.database import get_session
from app.models import (
    Antibody, Fluorochrome, ShipmentVerification, ShipmentVerificationAttachment, Staff, User,
)
from app.services.shipments import (
    attachment_path, check_overdue, close_verification, delete_attachment,
    display_status, is_overdue, save_attachment,
)

router = APIRouter(prefix="/api/shipment-verifications", tags=["shipment-verifications"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AttachmentRead(BaseModel):
    id: int
    role: str
    original_filename: str
    content_type: Optional[str]
    size_bytes: int
    sha256: str
    uploaded_by_username: str
    uploaded_at: datetime


class VerificationRead(BaseModel):
    id: int
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    vendor: Optional[str]
    shipment_id: str
    new_lot_no: Optional[str]
    previous_shipment_id: Optional[str]
    previous_lot_no: Optional[str]
    lot_changed: bool
    status: str
    display_status: str              # pending | overdue | acceptable | not_acceptable
    overdue: bool
    triggered_at: datetime
    due_at: datetime
    hours_remaining: Optional[float]  # negative when overdue; None when closed
    outcome: Optional[str]
    comments: Optional[str]
    closed_by_username: Optional[str]
    closed_at: Optional[datetime]
    closed_late: Optional[bool]
    attachments: List[AttachmentRead]
    has_previous_evidence: bool
    has_new_evidence: bool


class ClosePayload(BaseModel):
    outcome: str
    comments: Optional[str] = None
    closed_by_staff_id: Optional[int] = None   # person signing off (shared login)


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

def _username(user_id: Optional[int], session: Session) -> Optional[str]:
    if not user_id:
        return None
    u = session.get(User, user_id)
    return u.username if u else None


def _signed_by(v: ShipmentVerification, session: Session) -> Optional[str]:
    """Staff name of the signer; login username for records without one."""
    if v.closed_by_staff_id:
        s = session.get(Staff, v.closed_by_staff_id)
        if s:
            return s.name
    return _username(v.closed_by, session)


def _enrich(v: ShipmentVerification, session: Session) -> VerificationRead:
    ab = session.get(Antibody, v.antibody_id)
    fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab and ab.fluorochrome_id else None
    atts = session.exec(
        select(ShipmentVerificationAttachment)
        .where(ShipmentVerificationAttachment.verification_id == v.id)
        .order_by(ShipmentVerificationAttachment.uploaded_at)
    ).all()
    now = datetime.now()
    hours = round((v.due_at - now).total_seconds() / 3600, 1) if v.status == "open" else None
    return VerificationRead(
        id=v.id,
        antibody_id=v.antibody_id,
        antibody_name=ab.name if ab else "unknown",
        fluorochrome=fc.name if fc else None,
        vendor=ab.vendor if ab else None,
        shipment_id=v.shipment_id,
        new_lot_no=v.new_lot_no,
        previous_shipment_id=v.previous_shipment_id,
        previous_lot_no=v.previous_lot_no,
        lot_changed=v.lot_changed,
        status=v.status,
        display_status=display_status(v) or "pending",
        overdue=is_overdue(v, now),
        triggered_at=v.triggered_at,
        due_at=v.due_at,
        hours_remaining=hours,
        outcome=v.outcome,
        comments=v.comments,
        closed_by_username=_signed_by(v, session),
        closed_at=v.closed_at,
        closed_late=(v.closed_at > v.due_at) if v.closed_at else None,
        attachments=[
            AttachmentRead(
                id=a.id,
                role=a.role,
                original_filename=a.original_filename,
                content_type=a.content_type,
                size_bytes=a.size_bytes,
                sha256=a.sha256,
                uploaded_by_username=_username(a.uploaded_by, session) or "unknown",
                uploaded_at=a.uploaded_at,
            )
            for a in atts
        ],
        has_previous_evidence=any(a.role == "previous" for a in atts),
        has_new_evidence=any(a.role == "new" for a in atts),
    )


def _get_or_404(vid: int, session: Session) -> ShipmentVerification:
    v = session.get(ShipmentVerification, vid)
    if not v:
        raise HTTPException(status_code=404, detail="Verification not found")
    return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/summary")
def summary(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    open_vs = session.exec(
        select(ShipmentVerification).where(ShipmentVerification.status == "open")
    ).all()
    now = datetime.now()
    return {
        "open": len(open_vs),
        "overdue": sum(1 for v in open_vs if is_overdue(v, now)),
    }


@router.get("/", response_model=List[VerificationRead])
def list_verifications(
    status: str = "open",
    antibody_id: Optional[int] = None,
    shipment_id: Optional[str] = None,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    if status not in ("open", "closed", "all"):
        raise HTTPException(status_code=400, detail="status must be open, closed or all")

    # Raise overdue alerts lazily — there is no background scheduler, and this
    # page (and the nav badge) is where overdue items get noticed.
    if check_overdue(session):
        session.commit()

    q = select(ShipmentVerification)
    if status != "all":
        q = q.where(ShipmentVerification.status == status)
    if antibody_id:
        q = q.where(ShipmentVerification.antibody_id == antibody_id)
    if shipment_id:
        q = q.where(ShipmentVerification.shipment_id == shipment_id.strip())
    rows = session.exec(q).all()
    # open: most urgent first; closed: most recent first
    rows.sort(key=lambda v: (v.status != "open", v.due_at if v.status == "open" else datetime.max - (v.closed_at or v.triggered_at)))
    return [_enrich(v, session) for v in rows]


@router.get("/export/log.csv", response_class=StreamingResponse)
def export_log(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    rows = session.exec(select(ShipmentVerification).order_by(ShipmentVerification.triggered_at)).all()
    fields = [
        "verification_id", "antibody", "fluorochrome", "vendor",
        "previous_shipment_id", "previous_lot_no", "new_shipment_id", "new_lot_no", "lot_changed",
        "triggered_at", "due_at", "status", "outcome", "closed_by", "closed_at", "closed_late",
        "evidence_previous", "evidence_new", "comments",
    ]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for v in rows:
        r = _enrich(v, session)
        w.writerow({
            "verification_id": r.id,
            "antibody": r.antibody_name,
            "fluorochrome": r.fluorochrome or "",
            "vendor": r.vendor or "",
            "previous_shipment_id": r.previous_shipment_id or "(untagged)",
            "previous_lot_no": r.previous_lot_no or "",
            "new_shipment_id": r.shipment_id,
            "new_lot_no": r.new_lot_no or "",
            "lot_changed": r.lot_changed,
            "triggered_at": r.triggered_at.isoformat(timespec="minutes"),
            "due_at": r.due_at.isoformat(timespec="minutes"),
            "status": r.display_status,
            "outcome": r.outcome or "",
            "closed_by": r.closed_by_username or "",
            "closed_at": r.closed_at.isoformat(timespec="minutes") if r.closed_at else "",
            "closed_late": "" if r.closed_late is None else r.closed_late,
            "evidence_previous": "; ".join(f"{a.original_filename} (sha256 {a.sha256[:12]})" for a in r.attachments if a.role == "previous"),
            "evidence_new": "; ".join(f"{a.original_filename} (sha256 {a.sha256[:12]})" for a in r.attachments if a.role == "new"),
            "comments": r.comments or "",
        })
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="flowjai_shipment_verifications_{ts}.csv"'},
    )


@router.get("/attachments/{att_id}")
def download_attachment(
    att_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    att = session.get(ShipmentVerificationAttachment, att_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        path = attachment_path(att)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid attachment path")
    if not path.exists():
        raise HTTPException(status_code=410, detail="File missing from the uploads folder")
    return FileResponse(
        str(path),
        media_type=att.content_type or "application/octet-stream",
        filename=att.original_filename,
    )


@router.delete("/attachments/{att_id}", status_code=204)
def remove_attachment(
    att_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    att = session.get(ShipmentVerificationAttachment, att_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    if att.uploaded_by != current_user.id and current_user.role not in ("admin", "service"):
        raise HTTPException(status_code=403, detail="Only the uploader or an admin can remove this file")
    try:
        delete_attachment(att, session)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    session.commit()


@router.get("/{vid}", response_model=VerificationRead)
def get_verification(
    vid: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    return _enrich(_get_or_404(vid, session), session)


@router.post("/{vid}/attachments", response_model=VerificationRead)
def upload_attachment(
    vid: int,
    role: str = Form(...),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    v = _get_or_404(vid, session)
    try:
        save_attachment(
            v,
            role=role,
            filename=file.filename or "upload",
            content_type=file.content_type,
            stream=file.file,
            user_id=current_user.id,
            session=session,
        )
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    session.commit()
    session.refresh(v)
    return _enrich(v, session)


@router.post("/{vid}/close", response_model=VerificationRead)
def close(
    vid: int,
    payload: ClosePayload,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    v = _get_or_404(vid, session)
    if payload.closed_by_staff_id is not None:
        s = session.get(Staff, payload.closed_by_staff_id)
        if not s or not s.active:
            raise HTTPException(status_code=400, detail="Signing staff member not found or inactive")
    try:
        close_verification(
            v,
            outcome=payload.outcome,
            comments=payload.comments,
            user_id=current_user.id,
            session=session,
            staff_id=payload.closed_by_staff_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session.commit()
    session.refresh(v)
    return _enrich(v, session)
