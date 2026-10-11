"""
v0.8.3: antibody import (SAP export or flowjAI template).

    cd backend && python -m pytest tests/test_antibody_import.py -q
"""

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.database import create_db_and_tables, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Antibody  # noqa: E402

create_db_and_tables()
client = TestClient(app)

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "antibody-import-template.csv"


@pytest.fixture(scope="module")
def h():
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "Adm1n-pass-123"})
    if r.status_code != 201:
        r = client.post("/api/auth/token", data={"username": "admin", "password": "Adm1n-pass-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def preview(h, name, content, mime="text/csv"):
    return client.post("/api/import/sap/preview", headers=h,
                       files={"file": (name, content, mime)})


def commit(h, rows):
    body = [{
        "row_index": r["row_index"], "antibody_name": r["antibody_name"],
        "fluorochrome_name": r["fluorochrome_name"], "catalog_no": r["catalog_no"],
        "vendor": r["vendor"], "volume_ul": r["volume_ul"], "material_no": r["material_no"],
    } for r in rows]
    r = client.post("/api/import/sap/commit", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def antibody(cat):
    with Session(engine) as s:
        return s.exec(select(Antibody).where(Antibody.catalog_no == cat)).first()


def test_template_parses_with_vial_volume(h):
    r = preview(h, "antibody-import-template.csv", TEMPLATE.read_bytes())
    assert r.status_code == 200, r.text
    rows = {x["catalog_no"]: x for x in r.json()}
    assert rows["EXAMPLE-001"]["antibody_name"] == "CD3"
    assert rows["EXAMPLE-001"]["fluorochrome_name"] == "FITC"
    assert rows["EXAMPLE-001"]["volume_ul"] == 500
    assert rows["EXAMPLE-003"]["volume_ul"] == 250


def test_commit_saves_standard_vial_volume(h):
    rows = preview(h, "t.csv", TEMPLATE.read_bytes()).json()
    res = commit(h, rows)
    assert res["antibodies_created"] == 3
    assert antibody("EXAMPLE-001").vial_volume_ul == 500
    assert antibody("EXAMPLE-003").vial_volume_ul == 250


def test_existing_antibody_gets_missing_volume_but_set_volume_is_kept(h):
    with Session(engine) as s:
        s.add(Antibody(name="CD5", catalog_no="EXAMPLE-010"))
        s.add(Antibody(name="CD7", catalog_no="EXAMPLE-011", vial_volume_ul=100))
        s.commit()
    csv = ("Antibody Name,Fluorochrome Name,Catalogue No,Manufacturer,Vial Volume uL\n"
           "CD5,APC,EXAMPLE-010,BD,500\nCD7,PE-Cy7,EXAMPLE-011,BD,500\n").encode()
    res = commit(h, preview(h, "e.csv", csv).json())
    assert res["antibodies_created"] == 0
    assert res["vial_volumes_set"] == 1
    assert antibody("EXAMPLE-010").vial_volume_ul == 500
    assert antibody("EXAMPLE-011").vial_volume_ul == 100      # never overwritten


def test_xlsx_upload(h):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Short Text", "Catalogue No", "Manufacturer", "Alternative UOM", "Kit Size"])
    ws.append(["CD10 PE-CY7 HI10A 100T", "EXAMPLE-020", "BD", "MICRO", "500"])
    ws.append(["SHEATH FLUID", "EXAMPLE-021", "BD", "LITRE", "20"])
    buf = io.BytesIO()
    wb.save(buf)
    r = preview(h, "sap.xlsx", buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.status_code == 200, r.text
    rows = {x["catalog_no"]: x for x in r.json()}
    assert rows["EXAMPLE-020"]["antibody_name"] == "CD10"
    assert rows["EXAMPLE-020"]["volume_ul"] == 500
    assert rows["EXAMPLE-021"]["status"] == "skip"


def test_old_xls_is_rejected_with_a_clear_message(h):
    r = preview(h, "old.xls", b"not really excel", "application/vnd.ms-excel")
    assert r.status_code == 400
    assert ".xlsx" in r.json()["detail"]


def test_file_without_name_columns_is_rejected(h):
    r = preview(h, "bad.csv", b"Foo,Bar\n1,2\n")
    assert r.status_code == 400


def test_existing_row_from_preview_fills_volume_without_duplicating(h):
    """The page sends rows the preview marked 'exists' with their antibody id."""
    with Session(engine) as s:
        s.add(Antibody(name="CD20", catalog_no="EXAMPLE-030"))
        s.commit()
    csv = ("Antibody Name,Fluorochrome Name,Catalogue No,Manufacturer,Vial Volume uL\n"
           "CD20,BV421,EXAMPLE-030,BD,250\n").encode()
    rows = preview(h, "x.csv", csv).json()
    assert rows[0]["status"] == "exists"
    body = [{**{k: rows[0][k] for k in ("row_index", "antibody_name", "fluorochrome_name",
                                         "catalog_no", "vendor", "volume_ul", "material_no")},
             "existing_antibody_id": rows[0]["existing_antibody_id"]}]
    res = client.post("/api/import/sap/commit", headers=h, json=body).json()
    assert res["antibodies_created"] == 0 and res["vial_volumes_set"] == 1
    assert res["fluorochromes_created"] == 0
    assert antibody("EXAMPLE-030").vial_volume_ul == 250
    with Session(engine) as s:
        assert len(s.exec(select(Antibody).where(Antibody.catalog_no == "EXAMPLE-030")).all()) == 1
