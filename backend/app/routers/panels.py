"""routers/panels.py — Panel and PanelComponent CRUD."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin
from app.database import get_session
from app.models import Antibody, Fluorochrome, Panel, PanelComponent, User

router = APIRouter(prefix="/api/panels", tags=["panels"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PanelComponentRead(BaseModel):
    id: int
    antibody_id: int
    antibody_name: str
    fluorochrome: Optional[str]
    volume_per_tube_ul: float
    tubes_per_test: int
    ul_per_test: float


class PanelRead(BaseModel):
    id: int
    name: str
    test_code: str
    test_group: Optional[str] = None
    department: Optional[str]
    active: bool
    components: List[PanelComponentRead] = []


class PanelCreate(BaseModel):
    name: str
    test_code: str
    test_group: Optional[str] = None
    department: Optional[str] = None


class PanelUpdate(BaseModel):
    name: Optional[str] = None
    test_code: Optional[str] = None
    test_group: Optional[str] = None
    department: Optional[str] = None
    active: Optional[bool] = None


class ComponentCreate(BaseModel):
    antibody_id: int
    volume_per_tube_ul: float
    tubes_per_test: int = 1


class ComponentUpdate(BaseModel):
    volume_per_tube_ul: Optional[float] = None
    tubes_per_test: Optional[int] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enrich_components(panel: Panel, session: Session) -> List[PanelComponentRead]:
    components = session.exec(
        select(PanelComponent).where(PanelComponent.panel_id == panel.id)
    ).all()
    result = []
    for c in components:
        ab = session.get(Antibody, c.antibody_id)
        fc = session.get(Fluorochrome, ab.fluorochrome_id) if (ab and ab.fluorochrome_id) else None
        result.append(PanelComponentRead(
            id=c.id,
            antibody_id=c.antibody_id,
            antibody_name=ab.name if ab else "unknown",
            fluorochrome=fc.name if fc else None,
            volume_per_tube_ul=c.volume_per_tube_ul,
            tubes_per_test=c.tubes_per_test,
            ul_per_test=c.ul_per_test(),
        ))
    return result


# ---------------------------------------------------------------------------
# Panel CRUD
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[PanelRead])
def list_panels(
    active_only: bool = True,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    q = select(Panel)
    if active_only:
        q = q.where(Panel.active == True)    # noqa: E712
    panels = session.exec(q.order_by(Panel.name)).all()
    return [
        PanelRead(
            id=p.id, name=p.name, test_code=p.test_code,
            test_group=p.test_group, department=p.department, active=p.active,
            components=_enrich_components(p, session),
        )
        for p in panels
    ]


@router.get("/{panel_id}", response_model=PanelRead)
def get_panel(
    panel_id: int,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    panel = session.get(Panel, panel_id)
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")
    return PanelRead(
        id=panel.id, name=panel.name, test_code=panel.test_code,
        test_group=panel.test_group, department=panel.department, active=panel.active,
        components=_enrich_components(panel, session),
    )


@router.post("/", response_model=PanelRead, dependencies=[Depends(require_admin)])
def create_panel(payload: PanelCreate, session: Session = Depends(get_session)):
    panel = Panel(**payload.model_dump())
    session.add(panel)
    session.commit()
    session.refresh(panel)
    return PanelRead(
        id=panel.id, name=panel.name, test_code=panel.test_code,
        test_group=panel.test_group, department=panel.department, active=panel.active, components=[],
    )


@router.patch("/{panel_id}", response_model=PanelRead, dependencies=[Depends(require_admin)])
def update_panel(
    panel_id: int, payload: PanelUpdate, session: Session = Depends(get_session)
):
    panel = session.get(Panel, panel_id)
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")

    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(panel, k, v)

    session.add(panel)
    session.commit()
    session.refresh(panel)
    return PanelRead(
        id=panel.id, name=panel.name, test_code=panel.test_code,
        test_group=panel.test_group, department=panel.department, active=panel.active,
        components=_enrich_components(panel, session),
    )


# ---------------------------------------------------------------------------
# Components sub-resource
# ---------------------------------------------------------------------------

@router.post(
    "/{panel_id}/components",
    response_model=PanelComponentRead,
    dependencies=[Depends(require_admin)],
)
def add_component(
    panel_id: int, payload: ComponentCreate, session: Session = Depends(get_session)
):
    panel = session.get(Panel, panel_id)
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")

    ab = session.get(Antibody, payload.antibody_id)
    if not ab:
        raise HTTPException(status_code=404, detail="Antibody not found")

    existing = session.exec(
        select(PanelComponent)
        .where(PanelComponent.panel_id == panel_id)
        .where(PanelComponent.antibody_id == payload.antibody_id)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="This antibody is already in the panel — use PATCH to update volumes",
        )

    comp = PanelComponent(
        panel_id=panel_id,
        antibody_id=payload.antibody_id,
        volume_per_tube_ul=payload.volume_per_tube_ul,
        tubes_per_test=payload.tubes_per_test,
    )
    session.add(comp)
    session.commit()
    session.refresh(comp)

    fc = session.get(Fluorochrome, ab.fluorochrome_id) if ab.fluorochrome_id else None
    return PanelComponentRead(
        id=comp.id, antibody_id=ab.id, antibody_name=ab.name,
        fluorochrome=fc.name if fc else None,
        volume_per_tube_ul=comp.volume_per_tube_ul,
        tubes_per_test=comp.tubes_per_test,
        ul_per_test=comp.ul_per_test(),
    )


@router.patch(
    "/{panel_id}/components/{component_id}",
    response_model=PanelComponentRead,
    dependencies=[Depends(require_admin)],
)
def update_component(
    panel_id: int,
    component_id: int,
    payload: ComponentUpdate,
    session: Session = Depends(get_session),
):
    comp = session.get(PanelComponent, component_id)
    if not comp or comp.panel_id != panel_id:
        raise HTTPException(status_code=404, detail="Component not found")

    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(comp, k, v)

    session.add(comp)
    session.commit()
    session.refresh(comp)

    ab = session.get(Antibody, comp.antibody_id)
    fc = session.get(Fluorochrome, ab.fluorochrome_id) if (ab and ab.fluorochrome_id) else None
    return PanelComponentRead(
        id=comp.id, antibody_id=comp.antibody_id,
        antibody_name=ab.name if ab else "unknown",
        fluorochrome=fc.name if fc else None,
        volume_per_tube_ul=comp.volume_per_tube_ul,
        tubes_per_test=comp.tubes_per_test,
        ul_per_test=comp.ul_per_test(),
    )


@router.delete(
    "/{panel_id}/components/{component_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
def remove_component(
    panel_id: int, component_id: int, session: Session = Depends(get_session)
):
    comp = session.get(PanelComponent, component_id)
    if not comp or comp.panel_id != panel_id:
        raise HTTPException(status_code=404, detail="Component not found")
    session.delete(comp)
    session.commit()


@router.get("/{panel_id}/delete-preview", dependencies=[Depends(require_admin)])
def panel_delete_preview(panel_id: int, session: Session = Depends(get_session)):
    from app.models import PanelComponent, TestLog
    from sqlmodel import select

    panel = session.get(Panel, panel_id)
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")

    comps     = session.exec(select(PanelComponent).where(PanelComponent.panel_id == panel_id)).all()
    test_logs = session.exec(select(TestLog).where(TestLog.panel_id == panel_id)).all()

    return {
        "panel_name": panel.name,
        "components": len(comps),
        "test_logs": len(test_logs),
        "safe": len(test_logs) == 0,
    }


@router.delete("/{panel_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_panel(panel_id: int, force: bool = False, session: Session = Depends(get_session)):
    """
    Delete a panel.
    - Normal delete: blocked if the panel has test log history.
    - Force delete (?force=true): removes components and test logs too.
    """
    from app.models import PanelComponent, TestLog, ConsumptionLog
    from sqlmodel import select

    panel = session.get(Panel, panel_id)
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")

    comps     = session.exec(select(PanelComponent).where(PanelComponent.panel_id == panel_id)).all()
    test_logs = session.exec(select(TestLog).where(TestLog.panel_id == panel_id)).all()

    if test_logs and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: panel has {len(test_logs)} test log record(s). Use force delete to remove everything.",
        )

    # Cascade: consumption logs reference test logs, delete those first
    for tl in test_logs:
        cons = session.exec(select(ConsumptionLog).where(ConsumptionLog.test_log_id == tl.id)).all()
        for c in cons:
            session.delete(c)
        session.delete(tl)

    for comp in comps:
        session.delete(comp)

    session.delete(panel)
    session.commit()
