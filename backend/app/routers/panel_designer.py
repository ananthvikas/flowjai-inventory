"""
routers/panel_designer.py — Panel Designer: auto-design panels from antibody picks.

Two-step flow:
  1. POST /design  — user picks antibodies; algorithm returns valid fluorochrome
                     assignments, ranked combinations, and clash flags.
  2. POST /create  — user resolves clashes, names the panel; creates Panel +
                     components.

WHAT CHANGED
    The previous _build_options() read only ab.fluorochrome_id, so every
    antibody had at most ONE fluorochrome option. The backtracking search, the
    "all combinations" response and the top-50 stock-weighted ranking therefore
    operated over a search space of size one and could never produce an
    alternative design.

    A marker is now resolved across every active Antibody row carrying that
    name — CD4-PE, CD4-APC and CD4-BV421 are three fluorochrome options for the
    marker CD4 — which is what makes the combinatorial search meaningful. Each
    option reports the specific antibody variant id, so /create still writes the
    correct PanelComponent.

    A clash is now only raised for genuine contention: two markers whose sole
    remaining option is the same fluorochrome. Having several fluorochrome
    variants of one marker is the point of the feature, not an error.

SEARCH BOUNDS
    Enumeration is branch-and-bound over markers ordered most-constrained-first,
    capped at MAX_NODES explored states and MAX_SOLUTIONS retained assignments.
    With ~12 markers and a few variants each the search completes well inside
    those bounds; the caps exist so a pathological pick cannot hang a request.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_technologist_or_admin
from app.database import get_session
from app.models import (
    Antibody,
    AntibodyAlternative,
    Fluorochrome,
    Panel,
    PanelComponent,
    StockLot,
    User,
)
from app.routers.panels import PanelRead, _enrich_components

router = APIRouter(prefix="/api/panel-designer", tags=["panel-designer"])

MAX_NODES = 200_000        # explored search states before the search stops early
MAX_SOLUTIONS = 5_000      # retained assignments before ranking
MAX_RETURNED = 50          # combinations returned to the client


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DesignRequest(BaseModel):
    antibody_ids: List[int]


class FluorochromeOption(BaseModel):
    fluorochrome_id: int
    fluorochrome_name: str
    laser: Optional[str] = None
    emission_nm: Optional[int] = None
    stock_ul: float
    # Which Antibody row carries this marker in this fluorochrome. Needed
    # because one marker may exist as several variants.
    antibody_id: Optional[int] = None
    clone: Optional[str] = None
    vendor: Optional[str] = None


class AntibodyOption(BaseModel):
    antibody_id: int                 # representative variant for this marker
    antibody_name: str
    clone: Optional[str] = None
    vendor: Optional[str] = None
    fluorochrome_options: List[FluorochromeOption]


class Assignment(BaseModel):
    antibody_id: int                 # the specific variant chosen
    antibody_name: str
    fluorochrome_id: int
    fluorochrome_name: str
    laser: Optional[str] = None
    emission_nm: Optional[int] = None
    stock_ul: float


class Combination(BaseModel):
    index: int
    assignments: List[Assignment]
    total_stock_ul: float


class ConflictAntibodyEntry(BaseModel):
    antibody_id: int
    name: str
    fluorochrome_name: Optional[str] = None
    stock_ul: float


class Clash(BaseModel):
    fluorochrome_name: str
    conflicting_antibodies: List[ConflictAntibodyEntry]


class AlternativeEntry(BaseModel):
    antibody_id: int
    antibody_name: str
    fluorochrome_id: Optional[int] = None
    fluorochrome_name: Optional[str] = None
    stock_ul: float


class DesignResponse(BaseModel):
    antibody_options: List[AntibodyOption]
    combinations: List[Combination]
    clashes: List[Clash]
    unplaced_antibodies: List[int]   # representative ids with no in-stock option
    alternatives: Dict[int, List[AlternativeEntry]] = {}
    search_truncated: bool = False   # true if the node cap stopped enumeration


class PanelDesignerCreateRequest(BaseModel):
    name: str
    test_code: str
    test_group: Optional[str] = None
    department: Optional[str] = None
    volume_per_tube_ul: float = 0.5
    tubes_per_test: int = 1
    assignments: List[Assignment]


# ---------------------------------------------------------------------------
# Internal marker representation
# ---------------------------------------------------------------------------

class _Option:
    """One (antibody variant, fluorochrome) pairing available for a marker."""

    __slots__ = ("antibody_id", "antibody_name", "clone", "vendor",
                 "fc_id", "fc_name", "laser", "emission_nm", "stock_ul")

    def __init__(self, ab: Antibody, fc: Fluorochrome, stock_ul: float):
        self.antibody_id = ab.id
        self.antibody_name = ab.name
        self.clone = ab.clone
        self.vendor = ab.vendor
        self.fc_id = fc.id
        self.fc_name = fc.name
        self.laser = fc.laser
        self.emission_nm = fc.emission_nm
        self.stock_ul = stock_ul


class _Marker:
    """A requested marker (e.g. CD4) and every in-stock fluorochrome it exists in."""

    __slots__ = ("name", "representative_id", "clone", "vendor", "options")

    def __init__(self, name: str, representative: Antibody, options: List[_Option]):
        self.name = name
        self.representative_id = representative.id
        self.clone = representative.clone
        self.vendor = representative.vendor
        self.options = options


# ---------------------------------------------------------------------------
# Stock lookup
# ---------------------------------------------------------------------------

def _stock_by_antibody(antibody_ids: List[int], session: Session) -> Dict[int, float]:
    """Total active stock per antibody id, in one query rather than N."""
    if not antibody_ids:
        return {}
    lots = session.exec(
        select(StockLot)
        .where(StockLot.antibody_id.in_(antibody_ids))
        .where(StockLot.active == True)          # noqa: E712
    ).all()
    totals: Dict[int, float] = defaultdict(float)
    for lot in lots:
        totals[lot.antibody_id] += lot.current_volume_ul
    return {k: round(v, 3) for k, v in totals.items()}


def _build_markers(antibody_ids: List[int], session: Session) -> List[_Marker]:
    """
    Resolve each requested antibody to its marker, then collect every active
    variant of that marker that has a fluorochrome and stock on hand.
    """
    requested = session.exec(
        select(Antibody)
        .where(Antibody.id.in_(antibody_ids))
        .where(Antibody.active == True)          # noqa: E712
    ).all()
    if not requested:
        return []

    # Preserve the order the user picked in, one entry per marker name.
    marker_names: List[str] = []
    representatives: Dict[str, Antibody] = {}
    for ab in sorted(requested, key=lambda a: antibody_ids.index(a.id) if a.id in antibody_ids else 0):
        key = ab.name.strip().lower()
        if key not in representatives:
            representatives[key] = ab
            marker_names.append(key)

    # Every active variant of the requested markers, in one query.
    variants = session.exec(
        select(Antibody).where(Antibody.active == True)          # noqa: E712
    ).all()
    by_marker: Dict[str, List[Antibody]] = defaultdict(list)
    for ab in variants:
        key = ab.name.strip().lower()
        if key in representatives:
            by_marker[key].append(ab)

    all_variant_ids = [ab.id for abs_ in by_marker.values() for ab in abs_]
    stock = _stock_by_antibody(all_variant_ids, session)

    fc_ids = {ab.fluorochrome_id for abs_ in by_marker.values()
              for ab in abs_ if ab.fluorochrome_id}
    fluors: Dict[int, Fluorochrome] = {}
    if fc_ids:
        for fc in session.exec(select(Fluorochrome).where(Fluorochrome.id.in_(fc_ids))).all():
            fluors[fc.id] = fc

    markers: List[_Marker] = []
    for key in marker_names:
        options: List[_Option] = []
        seen_fc: set = set()
        for ab in by_marker.get(key, []):
            if not ab.fluorochrome_id:
                continue
            fc = fluors.get(ab.fluorochrome_id)
            if not fc:
                continue
            have = stock.get(ab.id, 0.0)
            if have <= 0:
                continue
            # If two variants share a fluorochrome, keep the better-stocked one.
            if fc.name in seen_fc:
                existing = next(o for o in options if o.fc_name == fc.name)
                if have > existing.stock_ul:
                    options.remove(existing)
                    options.append(_Option(ab, fc, have))
                continue
            seen_fc.add(fc.name)
            options.append(_Option(ab, fc, have))

        options.sort(key=lambda o: -o.stock_ul)
        markers.append(_Marker(key, representatives[key], options))

    return markers


# ---------------------------------------------------------------------------
# Clash detection
# ---------------------------------------------------------------------------

def _detect_clashes(markers: List[_Marker]) -> List[Clash]:
    """
    Genuine contention only: two or more markers whose ONLY in-stock option is
    the same fluorochrome, so no assignment can place both.
    """
    sole: Dict[str, List[_Marker]] = defaultdict(list)
    for m in markers:
        if len(m.options) == 1:
            sole[m.options[0].fc_name].append(m)

    clashes: List[Clash] = []
    for fc_name, contenders in sole.items():
        if len(contenders) < 2:
            continue
        clashes.append(Clash(
            fluorochrome_name=fc_name,
            conflicting_antibodies=[
                ConflictAntibodyEntry(
                    antibody_id=m.options[0].antibody_id,
                    name=m.options[0].antibody_name,
                    fluorochrome_name=fc_name,
                    stock_ul=m.options[0].stock_ul,
                )
                for m in contenders
            ],
        ))
    return clashes


# ---------------------------------------------------------------------------
# Combination search
# ---------------------------------------------------------------------------

def _generate_combinations(markers: List[_Marker]) -> Tuple[List[Combination], bool]:
    """
    Branch-and-bound over markers, most-constrained first. Each fluorochrome may
    carry at most one marker. Returns maximum-cardinality assignments ranked by
    total available stock, plus a flag indicating whether the node cap was hit.
    """
    placeable = [m for m in markers if m.options]
    if not placeable:
        return [], False

    order = sorted(placeable, key=lambda m: len(m.options))
    n = len(order)

    solutions: List[List[_Option]] = []
    best_size = 0
    used_fc: set = set()
    current: List[_Option] = []
    nodes = 0
    truncated = False

    def backtrack(idx: int) -> None:
        nonlocal best_size, nodes, truncated

        if nodes >= MAX_NODES or len(solutions) >= MAX_SOLUTIONS:
            truncated = True
            return
        nodes += 1

        if idx == n:
            if not current:
                return
            size = len(current)
            if size > best_size:
                best_size = size
                solutions.clear()
            if size == best_size:
                solutions.append(list(current))
            return

        # Prune: even placing every remaining marker can't match the best found.
        if len(current) + (n - idx) < best_size:
            return

        marker = order[idx]
        for opt in marker.options:
            if opt.fc_name in used_fc:
                continue
            used_fc.add(opt.fc_name)
            current.append(opt)
            backtrack(idx + 1)
            current.pop()
            used_fc.discard(opt.fc_name)
            if truncated:
                return

        # Skip this marker (needed when every fluorochrome it has is taken).
        backtrack(idx + 1)

    backtrack(0)

    ranked = sorted(solutions, key=lambda s: -sum(o.stock_ul for o in s))[:MAX_RETURNED]

    combos: List[Combination] = []
    for i, sol in enumerate(ranked):
        # Present in the order the user picked, not the search order.
        by_name = {o.antibody_name.lower(): o for o in sol}
        ordered = [by_name[m.name] for m in markers if m.name in by_name]
        assignments = [
            Assignment(
                antibody_id=o.antibody_id,
                antibody_name=o.antibody_name,
                fluorochrome_id=o.fc_id,
                fluorochrome_name=o.fc_name,
                laser=o.laser,
                emission_nm=o.emission_nm,
                stock_ul=o.stock_ul,
            )
            for o in ordered
        ]
        combos.append(Combination(
            index=i,
            assignments=assignments,
            total_stock_ul=round(sum(a.stock_ul for a in assignments), 3),
        ))

    return combos, truncated


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/design", response_model=DesignResponse)
def design_panel(
    payload: DesignRequest,
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """Given a list of antibody ids, return valid fluorochrome assignments."""
    if not payload.antibody_ids:
        return DesignResponse(
            antibody_options=[], combinations=[], clashes=[], unplaced_antibodies=[]
        )

    markers = _build_markers(payload.antibody_ids, session)

    antibody_options = [
        AntibodyOption(
            antibody_id=m.representative_id,
            antibody_name=m.options[0].antibody_name if m.options else m.name.upper(),
            clone=m.clone,
            vendor=m.vendor,
            fluorochrome_options=[
                FluorochromeOption(
                    fluorochrome_id=o.fc_id,
                    fluorochrome_name=o.fc_name,
                    laser=o.laser,
                    emission_nm=o.emission_nm,
                    stock_ul=o.stock_ul,
                    antibody_id=o.antibody_id,
                    clone=o.clone,
                    vendor=o.vendor,
                )
                for o in m.options
            ],
        )
        for m in markers
    ]

    unplaced = [m.representative_id for m in markers if not m.options]
    clashes = _detect_clashes(markers)
    combinations, truncated = _generate_combinations(markers)

    # Registered alternatives for markers with nothing in stock
    alternatives: Dict[int, List[AlternativeEntry]] = {}
    for ab_id in unplaced:
        alt_rows = session.exec(
            select(AntibodyAlternative).where(AntibodyAlternative.antibody_id == ab_id)
        ).all()
        alt_ids = [a.alt_antibody_id for a in alt_rows]
        alt_stock = _stock_by_antibody(alt_ids, session)
        for alt in alt_rows:
            alt_ab = session.get(Antibody, alt.alt_antibody_id)
            if not alt_ab or not alt_ab.active:
                continue
            have = alt_stock.get(alt_ab.id, 0.0)
            if have <= 0:
                continue
            fc_name = None
            if alt_ab.fluorochrome_id:
                fc = session.get(Fluorochrome, alt_ab.fluorochrome_id)
                fc_name = fc.name if fc else None
            alternatives.setdefault(ab_id, []).append(AlternativeEntry(
                antibody_id=alt_ab.id,
                antibody_name=alt_ab.name,
                fluorochrome_id=alt_ab.fluorochrome_id,
                fluorochrome_name=fc_name,
                stock_ul=have,
            ))

    return DesignResponse(
        antibody_options=antibody_options,
        combinations=combinations,
        clashes=clashes,
        unplaced_antibodies=unplaced,
        alternatives=alternatives,
        search_truncated=truncated,
    )


@router.post("/create")
def create_designed_panel(
    payload: PanelDesignerCreateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_technologist_or_admin),
):
    """Create a panel from the designer's resolved assignments."""
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Panel name is required")
    if not payload.test_code.strip():
        raise HTTPException(status_code=400, detail="Test code is required")
    if not payload.assignments:
        raise HTTPException(status_code=400, detail="At least one antibody assignment is required")

    # Reject a design that reuses a fluorochrome or a marker.
    seen_fc, seen_marker, seen_ab = set(), set(), set()
    for a in payload.assignments:
        if a.fluorochrome_id in seen_fc:
            raise HTTPException(
                status_code=400,
                detail=f"Fluorochrome {a.fluorochrome_name} is assigned to more than one antibody",
            )
        marker = a.antibody_name.strip().lower()
        if marker in seen_marker:
            raise HTTPException(
                status_code=400,
                detail=f"{a.antibody_name} appears more than once in this panel",
            )
        if a.antibody_id in seen_ab:
            raise HTTPException(
                status_code=400,
                detail=f"Antibody id {a.antibody_id} appears more than once",
            )
        seen_fc.add(a.fluorochrome_id)
        seen_marker.add(marker)
        seen_ab.add(a.antibody_id)

    panel = Panel(
        name=payload.name.strip(),
        test_code=payload.test_code.strip(),
        test_group=payload.test_group or None,
        department=payload.department or None,
    )
    session.add(panel)
    session.flush()

    for a in payload.assignments:
        session.add(PanelComponent(
            panel_id=panel.id,
            antibody_id=a.antibody_id,
            volume_per_tube_ul=payload.volume_per_tube_ul,
            tubes_per_test=payload.tubes_per_test,
        ))

    session.commit()
    session.refresh(panel)

    return PanelRead(
        id=panel.id,
        name=panel.name,
        test_code=panel.test_code,
        test_group=panel.test_group,
        department=panel.department,
        active=panel.active,
        components=_enrich_components(panel, session),
    )
