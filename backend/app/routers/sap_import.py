"""
routers/sap_import.py

Imports antibody master data from a CSV or Excel (.xlsx) file: either a SAP
materials export or the flowjAI antibody import template
(templates/antibody-import-template.csv).

Two-phase workflow:
  POST /api/import/sap/preview  — parse file, return preview rows (no DB writes)
  POST /api/import/sap/commit   — create antibody + fluorochrome records from confirmed rows

Typical SAP materials export columns:
  Short Text      → parse for antibody name + fluorochrome
  Catalogue No    → antibody.catalog_no
  Manufacturer    → antibody.vendor (normalised)
  Kit Size        → volume hint (µl when Alternative UOM = MICRO)
  Alternative UOM → filter: only MICRO rows are antibodies
  Material        → stored as a catalog reference note

Rows where Alternative UOM = LITRE are instrument reagents
(sheath fluid, shutdown solution) and are automatically skipped.

flowjAI template columns (names matched case-insensitively):
  Antibody Name, Fluorochrome Name, Catalogue No, Manufacturer,
  Vial Volume uL (standard fill volume, saved as the antibody's vial volume),
  Description (optional when Antibody Name is given)
"""

import io
import logging
import re
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user, require_admin
from app.database import get_session
from app.models import Antibody, Fluorochrome, User

router = APIRouter(prefix="/api/import", tags=["import"])
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fluorochrome extraction — patterns matched against Short Text (upper-cased)
# Order matters: longer/more-specific patterns first
# ---------------------------------------------------------------------------

FLUOR_PATTERNS = [
    # Tandems and complex names first
    (r'PE[\-\s]?CY7|PECY7',              'PE-Cy7'),
    (r'PE[\-\s]?CY5\.5|PECY5\.5',        'PE-Cy5.5'),
    (r'PE[\-\s]?CY5\b|PECY5\b',          'PE-Cy5'),
    (r'APC[\-\s]?H7|APCH7',              'APC-H7'),
    (r'APC[\-\s]?CY7|APCY7',             'APC-Cy7'),
    (r'APC[\-\s]?R700',                  'APC-R700'),
    (r'PERCP[\-\s]?CY5\.5|PRCP[\-\s]?CY5\.5', 'PerCP-Cy5.5'),
    (r'PRCP\s+CY5',                      'PerCP-Cy5.5'),   # "PRCP CY5.5" variant
    (r'PE[\-\s]?CF594',                  'PE-CF594'),
    # BD Horizon tandem dyes
    (r'\bR718\b',                         'BD Horizon R718'),
    (r'\bR780\b',                         'BD Horizon R780'),
    (r'\bV450\b',                         'BD Horizon V450'),
    (r'\bV500\b',                         'BD Horizon V500'),
    # BrilliantViolet series
    (r'\bBV786\b',                        'BV786'),
    (r'\bBV750\b',                        'BV750'),
    (r'\bBV711\b',                        'BV711'),
    (r'\bBV650\b',                        'BV650'),
    (r'\bBV605\b',                        'BV605'),
    (r'\bBV570\b',                        'BV570'),
    (r'\bBV510\s*M?P?H?I?P?\b',          'BV510'),   # BV510MPHIP variant
    (r'\bBV510\b',                        'BV510'),
    (r'\bBV480\b',                        'BV480'),
    (r'\bBV421\b',                        'BV421'),
    (r'\bBV395\b',                        'BV395'),
    # BrilliantUltraViolet
    (r'\bBUV737\b',                       'BUV737'),
    (r'\bBUV615\b',                       'BUV615'),
    (r'\bBUV496\b',                       'BUV496'),
    (r'\bBUV395\b',                       'BUV395'),
    # Standard fluorochromes
    (r'CY5\.5',                           'PerCP-Cy5.5'),   # bare CY5.5 in flow context
    (r'\bFITC\b',                         'FITC'),
    (r'\bAPC\b',                          'APC'),
    (r'\bPerCP\b',                        'PerCP'),
    (r'\bPE\b',                           'PE'),
]

# Compiled for speed
_FLUOR_RE = [(re.compile(p, re.IGNORECASE), name) for p, name in FLUOR_PATTERNS]


# ---------------------------------------------------------------------------
# Vendor normalisation
# ---------------------------------------------------------------------------

VENDOR_MAP = {
    'BD': 'BD Biosciences',
    'BECTON': 'BD Biosciences',
    'BECTON DICKINSON': 'BD Biosciences',
    'BIOLEGEND': 'BioLegend',
    'BIO-LEGEND': 'BioLegend',
    'BECKMAN': 'Beckman Coulter',
    'BECKMAN COULTER': 'Beckman Coulter',
    'MILTENYI': 'Miltenyi Biotec',
    'THERMOFISHER': 'Thermo Fisher',
    'THERMO FISHER': 'Thermo Fisher',
    'THERMO': 'Thermo Fisher',
    'EBIOSCIENCE': 'Thermo Fisher',
    'INVITROGEN': 'Thermo Fisher',
    'BAG': 'BAG Diagnostics',
    'BAG DIAGNOSTICS': 'BAG Diagnostics',
}


def normalise_vendor(raw: str) -> str:
    if not raw:
        return raw
    upper = raw.strip().upper()
    for key, val in VENDOR_MAP.items():
        if upper == key or upper.startswith(key + ' '):
            return val
    return raw.strip().title()


# ---------------------------------------------------------------------------
# Antibody name extraction from Short Text
# ---------------------------------------------------------------------------

_CD_RE = re.compile(r'\bCD\s*(\d{1,3}[A-Za-z]?)\b', re.IGNORECASE)
_NAMED = {
    r'HLA[\-\s]?DR': 'HLA-DR',
    r'HLA[\-\s]?ABC': 'HLA-ABC',
    r'HLA[\-\s]?A': 'HLA-A',
    r'\bTCR[\-\s]?ALPHA[\-\s]?BETA\b': 'TCR α/β',
    r'\bTCR[\-\s]?GAMMA[\-\s]?DELTA\b': 'TCR γ/δ',
    r'\bTdT\b|\bTERMINAL DEOXYNUCLEOTIDYL\b': 'TdT',
    r'\bFMC7\b': 'FMC7',
    r'\bZAP[\-\s]?70\b': 'ZAP-70',
    r'\bIgG\b': 'IgG',
    r'\bIgM\b': 'IgM',
    r'\bIgA\b': 'IgA',
    r'\bIgD\b': 'IgD',
    r'\bKAPPA\b': 'Kappa',
    r'\bLAMBDA\b': 'Lambda',
    r'\bKI[\-\s]?67\b': 'Ki-67',
    r'\bBCL[\-\s]?2\b': 'BCL-2',
    r'\bBCL[\-\s]?6\b': 'BCL-6',
    r'\bMPO\b|\bMYELOPEROXIDASE\b': 'MPO',
    r'\bMUM[\-\s]?1\b': 'MUM-1',
    r'\bCYCLIN[\-\s]?D1\b': 'Cyclin D1',
}
_NAMED_RE = [(re.compile(p, re.IGNORECASE), name) for p, name in _NAMED.items()]


def extract_antibody_name(text: str) -> Optional[str]:
    # CD markers
    m = _CD_RE.search(text)
    if m:
        return f"CD{m.group(1).upper()}"
    # Named markers
    for pattern, name in _NAMED_RE:
        if pattern.search(text):
            return name
    return None


def extract_fluorochrome(text: str) -> Optional[str]:
    for pattern, name in _FLUOR_RE:
        if pattern.search(text):
            return name
    return None


def extract_clone(text: str) -> Optional[str]:
    """
    Clone names often appear as short alphanumeric codes between the
    antibody name and the fluorochrome, e.g. '9F5' in 'CD123 R718 9F5'.
    This is heuristic — flag for manual review if uncertain.
    """
    # Common clone pattern: 2-8 chars, mix of letters and numbers
    m = re.search(r'\b([A-Z0-9]{2,4}[-/]?[A-Z0-9]{1,4})\b', text, re.IGNORECASE)
    if m:
        candidate = m.group(1)
        # Exclude things that look like catalog numbers (all digits or too long)
        if not candidate.isdigit() and len(candidate) <= 8:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SAPRow(BaseModel):
    row_index: int
    material_no: str
    short_text: str
    catalog_no: Optional[str]
    manufacturer: Optional[str]
    uom: Optional[str]
    alternative_uom: Optional[str]
    kit_size: Optional[float]
    # Parsed
    antibody_name: Optional[str]
    fluorochrome_name: Optional[str]
    vendor: Optional[str]
    volume_ul: Optional[float]
    # Status
    status: str          # new | exists | skip | unrecognised
    skip_reason: Optional[str]
    existing_antibody_id: Optional[int]
    # User can override these before commit
    override_name: Optional[str] = None
    override_fluorochrome: Optional[str] = None


class CommitRow(BaseModel):
    row_index: int
    antibody_name: str
    fluorochrome_name: Optional[str]
    catalog_no: Optional[str]
    vendor: Optional[str]
    volume_ul: Optional[float]
    material_no: Optional[str]
    # Set for rows the preview matched to an existing antibody: only a missing
    # standard vial volume is filled in; nothing is created.
    existing_antibody_id: Optional[int] = None


class CommitResult(BaseModel):
    fluorochromes_created: int
    antibodies_created: int
    antibodies_skipped_existing: int
    vial_volumes_set: int = 0     # existing antibodies that had no standard vial volume
    errors: List[str]


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

def _to_float(value) -> Optional[float]:
    """A positive number from a cell, or None (blank, 'nan', text)."""
    try:
        v = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return v if v > 0 and v == v else None


def _volume_ul(kit_size, alt_uom: str) -> Optional[float]:
    """Convert kit_size + alternative_uom to µl."""
    if kit_size is None or pd.isna(kit_size):
        return None
    try:
        val = float(kit_size)
    except (ValueError, TypeError):
        return None

    uom = (alt_uom or '').strip().upper()
    if uom == 'MICRO':
        return val          # already µl
    if uom == 'ML':
        return val * 1000
    if uom == 'LITRE':
        return val * 1_000_000   # sanity-clamp below
    return None


def _parse_dataframe(df: pd.DataFrame) -> List[SAPRow]:
    """
    Normalise column names (case-insensitive, strip spaces/special chars)
    then extract rows.
    """
    # Normalise headers
    df.columns = [
        re.sub(r'[^a-z0-9]', '_', str(c).strip().lower())
        for c in df.columns
    ]

    # Build column aliases
    def col(*candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    mat_col  = col('material', 'material_no', 'mat_no')
    text_col = col('short_text', 'shorttext', 'description', 'short_text_')
    cat_col  = col('catalouge_no', 'catalogue_no', 'catalog_no', 'catalog_number', 'material_no_')
    mfr_col  = col('manufacturer', 'vendor', 'mfr')
    uom_col  = col('uom', 'base_unit', 'unit_of_measure')
    alt_col  = col('alternative_uom', 'alt_uom', 'alt__uom')
    kit_col  = col('kit_size', 'kit_size_', 'kitsize')
    ab_col   = col('antibody_name', 'antibody', 'ab_name', 'marker')
    fluor_col= col('fluorochrome_name', 'fluorochrome', 'fluor', 'dye')
    # Standard vial volume in µl, stated directly (flowjAI template). Takes
    # precedence over Kit Size + Alternative UOM. "Vial Volume (µl)" normalises
    # to vial_volume___l_ and "Vial volume (ul)" to vial_volume__ul_.
    vol_col  = col('vial_volume_ul', 'vial_volume__ul_', 'vial_volume___l_', 'vial_volume', 'volume_ul')

    if not text_col and not ab_col:
        raise ValueError("Cannot find a 'Short Text' / 'Description' or an 'Antibody Name' column "
                         "in the uploaded file. Download the template from the import page.")

    rows = []
    for i, row in df.iterrows():
        text     = str(row.get(text_col, '') or '').strip() if text_col else ''
        mat_no   = str(row.get(mat_col, '') or '').strip() if mat_col else ''
        cat_no   = str(row.get(cat_col, '') or '').strip() if cat_col else None
        mfr      = str(row.get(mfr_col, '') or '').strip() if mfr_col else None
        uom      = str(row.get(uom_col,  '') or '').strip() if uom_col else None
        alt_uom  = str(row.get(alt_col,  '') or '').strip() if alt_col else None
        kit_size = row.get(kit_col) if kit_col else None

        # Clean up "nan" strings from pandas
        cat_no  = None if cat_no in ('nan', '', 'None') else cat_no
        mfr     = None if mfr    in ('nan', '', 'None') else mfr
        alt_uom = None if alt_uom in ('nan', '', 'None') else alt_uom

        # Skip instrument reagents (LITRE = sheath fluid, shutdown solution etc.)
        if alt_uom and alt_uom.upper() == 'LITRE':
            rows.append(SAPRow(
                row_index=int(i), material_no=mat_no, short_text=text,
                catalog_no=cat_no, manufacturer=mfr, uom=uom,
                alternative_uom=alt_uom, kit_size=None,
                antibody_name=None, fluorochrome_name=None,
                vendor=None, volume_ul=None,
                status='skip', skip_reason='Instrument reagent (LITRE unit)',
                existing_antibody_id=None,
            ))
            continue

        # Parse — use pre-parsed columns if present, else regex on Short Text
        pre_ab    = str(row.get(ab_col, '') or '').strip() if ab_col else ''
        pre_fluor = str(row.get(fluor_col, '') or '').strip() if fluor_col else ''
        pre_ab    = None if pre_ab    in ('nan', '', 'None') else pre_ab
        pre_fluor = None if pre_fluor in ('nan', '', 'None') else pre_fluor

        if text.lower() in ('nan', 'none'):
            text = ''
        # Template rows may leave Description blank: describe them from the parsed names
        if not text and pre_ab:
            text = ' '.join(x for x in (pre_ab, pre_fluor) if x)

        # Skip empty rows
        if not text:
            continue

        ab_name  = pre_ab    or extract_antibody_name(text)
        fluor    = pre_fluor or extract_fluorochrome(text)
        vendor   = normalise_vendor(mfr) if mfr else None
        vol      = _volume_ul(kit_size, alt_uom or '')
        if vol_col:
            direct = _to_float(row.get(vol_col))
            if direct is not None:
                vol = direct

        # Clamp unreasonable volumes (>10ml = 10,000µl is unusual for flow antibodies)
        if vol and vol > 10_000:
            vol = None

        # Determine status (will be enriched in the route with DB lookup)
        status = 'new' if ab_name else 'unrecognised'
        reason = None if ab_name else 'Could not extract antibody name from Short Text'

        rows.append(SAPRow(
            row_index=int(i), material_no=mat_no, short_text=text,
            catalog_no=cat_no, manufacturer=mfr, uom=uom,
            alternative_uom=alt_uom, kit_size=_to_float(kit_size),
            antibody_name=ab_name, fluorochrome_name=fluor,
            vendor=vendor, volume_ul=vol,
            status=status, skip_reason=reason,
            existing_antibody_id=None,
        ))

    return rows


def _enrich_with_db(rows: List[SAPRow], session: Session) -> List[SAPRow]:
    """Check each parsed row against existing antibodies to flag duplicates."""
    antibodies = session.exec(select(Antibody)).all()
    existing = {(ab.name.upper(), (ab.catalog_no or '').upper()): ab for ab in antibodies}

    for row in rows:
        if row.status == 'skip':
            continue
        if not row.antibody_name:
            continue
        key_name = row.antibody_name.upper()
        key_cat  = (row.catalog_no or '').upper()

        # Exact catalog number match
        if key_cat:
            match = next((ab for ab in antibodies if (ab.catalog_no or '').upper() == key_cat), None)
            if match:
                row.status = 'exists'
                row.existing_antibody_id = match.id
                continue

        # Name match (same name, any fluorochrome)
        name_matches = [ab for ab in antibodies if ab.name.upper() == key_name]
        if name_matches:
            # If same fluorochrome too, definite duplicate
            if row.fluorochrome_name:
                for ab in name_matches:
                    if ab.fluorochrome and ab.fluorochrome.name.upper() == row.fluorochrome_name.upper():
                        row.status = 'exists'
                        row.existing_antibody_id = ab.id
                        break
            # Same name, different or unknown fluorochrome → treat as new (new conjugate)

    return rows


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/sap/preview", response_model=List[SAPRow])
async def preview_sap_import(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """
    Parse a SAP Excel/CSV export and return a preview of what would be imported.
    No database changes are made.
    """
    content = await file.read()
    filename = (file.filename or '').lower()

    if filename.endswith('.xls'):
        raise HTTPException(status_code=400, detail="Old Excel (.xls) files are not supported. "
                            "Open the file in Excel and save it as .xlsx or .csv, then upload again.")
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content), dtype=str, encoding='utf-8-sig')
        else:
            df = pd.read_excel(io.BytesIO(content), dtype=str, engine='openpyxl')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    try:
        rows = _parse_dataframe(df)
        rows = _enrich_with_db(rows, session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # never a bare 500: the page shows this message
        log.exception("Antibody import preview failed for %s", filename)
        raise HTTPException(status_code=400,
                            detail=f"Could not process the file ({type(e).__name__}: {e}). "
                                   "Details are in the app log (data/flowjai.log).")
    return rows


@router.post("/sap/commit", response_model=CommitResult)
def commit_sap_import(
    payload: List[CommitRow],
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    """
    Create antibody and fluorochrome records from confirmed preview rows.
    Skips rows where an antibody with the same catalog number already exists.
    """
    fluors_created = 0
    abs_created = 0
    abs_skipped = 0
    vols_set = 0
    errors = []

    # Build fluorochrome cache
    fluor_cache: dict = {
        f.name.upper(): f
        for f in session.exec(select(Fluorochrome)).all()
    }

    for row in payload:
        try:
            # Preview matched this row to an existing antibody: fill a missing
            # standard vial volume only, never overwrite or duplicate
            if row.existing_antibody_id:
                ab = session.get(Antibody, row.existing_antibody_id)
                if ab is not None:
                    abs_skipped += 1
                    if ab.vial_volume_ul is None and row.volume_ul and row.volume_ul > 0:
                        ab.vial_volume_ul = row.volume_ul
                        session.add(ab)
                        vols_set += 1
                    continue

            # Resolve or create fluorochrome
            fluor_obj = None
            if row.fluorochrome_name:
                key = row.fluorochrome_name.upper()
                if key in fluor_cache:
                    fluor_obj = fluor_cache[key]
                else:
                    fluor_obj = Fluorochrome(name=row.fluorochrome_name)
                    session.add(fluor_obj)
                    session.flush()
                    fluor_cache[key] = fluor_obj
                    fluors_created += 1

            # Check for existing by catalog number
            if row.catalog_no:
                existing = session.exec(
                    select(Antibody).where(Antibody.catalog_no == row.catalog_no)
                ).first()
                if existing:
                    abs_skipped += 1
                    # Fill in a missing standard vial volume; never overwrite one already set
                    if existing.vial_volume_ul is None and row.volume_ul and row.volume_ul > 0:
                        existing.vial_volume_ul = row.volume_ul
                        session.add(existing)
                        vols_set += 1
                    continue

            # Create antibody
            ab = Antibody(
                name=row.antibody_name,
                vendor=row.vendor,
                catalog_no=row.catalog_no,
                fluorochrome_id=fluor_obj.id if fluor_obj else None,
                vial_volume_ul=row.volume_ul if row.volume_ul and row.volume_ul > 0 else None,
                # Store SAP material number in clone field if no clone known
                # (preserves traceability back to SAP)
            )
            session.add(ab)
            abs_created += 1

        except Exception as e:
            errors.append(f"Row {row.row_index} ({row.antibody_name}): {e}")

    session.commit()
    return CommitResult(
        fluorochromes_created=fluors_created,
        antibodies_created=abs_created,
        antibodies_skipped_existing=abs_skipped,
        vial_volumes_set=vols_set,
        errors=errors,
    )
