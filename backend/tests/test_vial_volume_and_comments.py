"""
v0.8.1: standard vial volume enforcement, starting-volume correction,
worklist sample comments, and the inventory export fix.

    cd backend && python -m pytest tests/test_vial_volume_and_comments.py -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.database import create_db_and_tables, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import StockLot, StoreStock  # noqa: E402

create_db_and_tables()
client = TestClient(app)


@pytest.fixture(scope="module")
def h():
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "Adm1n-pass-123"})
    if r.status_code != 201:
        r = client.post("/api/auth/token", data={"username": "admin", "password": "Adm1n-pass-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def new_ab(h, name, vial=None, cat=None):
    body = {"name": name, "catalog_no": cat}
    if vial is not None:
        body["vial_volume_ul"] = vial
    r = client.post("/api/antibodies/", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ── Antibody master ──────────────────────────────────────────────────────────

def test_master_vial_volume_create_update_clear(h):
    ab = new_ab(h, "VV-CD10", vial=100, cat="555375")
    assert ab["vial_volume_ul"] == 100 and ab["catalog_no"] == "555375"

    r = client.patch(f"/api/antibodies/{ab['id']}", json={"vial_volume_ul": 125}, headers=h)
    assert r.json()["vial_volume_ul"] == 125
    # unrelated edit leaves it alone
    r = client.patch(f"/api/antibodies/{ab['id']}", json={"clone": "HI10a"}, headers=h)
    assert r.json()["vial_volume_ul"] == 125
    # explicit null clears it
    r = client.patch(f"/api/antibodies/{ab['id']}", json={"vial_volume_ul": None}, headers=h)
    assert r.json()["vial_volume_ul"] is None

    assert client.post("/api/antibodies/", json={"name": "bad", "vial_volume_ul": -5}, headers=h).status_code == 400


# ── Receipts ─────────────────────────────────────────────────────────────────

def test_receive_lot_uses_standard_and_requires_reason(h):
    ab = new_ab(h, "VV-CD20", vial=100)
    base = {"antibody_id": ab["id"], "date_received": "2026-10-01", "shipment_id": "S1"}

    r = client.post("/api/stock/", json={**base, "lot_no": "A1"}, headers=h)          # omitted -> standard
    assert r.status_code == 200, r.text
    assert r.json()["initial_volume_ul"] == 100 and r.json()["current_volume_ul"] == 100

    r = client.post("/api/stock/", json={**base, "lot_no": "A2", "initial_volume_ul": 500}, headers=h)
    assert r.status_code == 400 and "standard vial volume is 100" in r.json()["detail"]

    r = client.post("/api/stock/", json={**base, "lot_no": "A3", "initial_volume_ul": 100.3}, headers=h)
    assert r.status_code == 200 and r.json()["initial_volume_ul"] == 100       # within tolerance -> standard

    r = client.post("/api/stock/", json={**base, "lot_no": "A4", "initial_volume_ul": 125,
                                         "volume_override_reason": "vendor changed fill"}, headers=h)
    assert r.status_code == 200
    assert r.json()["initial_volume_ul"] == 125 and "[VOLUME OVERRIDE]" in r.json()["notes"]


def test_receive_without_standard_requires_volume(h):
    ab = new_ab(h, "VV-CD22")
    base = {"antibody_id": ab["id"], "lot_no": "B1", "date_received": "2026-10-01", "shipment_id": "S1"}
    assert client.post("/api/stock/", json=base, headers=h).status_code == 400
    r = client.post("/api/stock/", json={**base, "initial_volume_ul": 250}, headers=h)
    assert r.status_code == 200 and r.json()["initial_volume_ul"] == 250


def test_bulk_receive_is_all_or_nothing(h):
    ok = new_ab(h, "VV-CD34", vial=50)
    bad = new_ab(h, "VV-CD38", vial=50)
    rows = [
        {"antibody_id": ok["id"], "lot_no": "C1", "date_received": "2026-10-01", "shipment_id": "S9"},
        {"antibody_id": bad["id"], "lot_no": "C2", "initial_volume_ul": 500,
         "date_received": "2026-10-01", "shipment_id": "S9"},
    ]
    r = client.post("/api/stock/bulk", json=rows, headers=h)
    assert r.status_code == 400 and "Row 2" in r.json()["detail"]
    assert client.get(f"/api/stock/?antibody_id={ok['id']}", headers=h).json() == []   # nothing saved

    rows[1]["initial_volume_ul"] = None
    r = client.post("/api/stock/bulk", json=rows, headers=h)
    assert r.status_code == 200 and [x["initial_volume_ul"] for x in r.json()] == [50, 50]


def test_store_stock_no_500_default_and_open_vial(h):
    ab = new_ab(h, "VV-CD45", vial=100, cat="557833")
    r = client.post("/api/store-stock/", json={
        "antibody_id": ab["id"], "lot_no": "D1", "quantity": 2,
        "received_date": "2026-10-01", "shipment_id": "S2",
    }, headers=h)
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["volume_per_vial_ul"] == 100
    assert row["catalog_no"] == "557833"             # defaulted from the master

    r = client.post(f"/api/store-stock/{row['id']}/open-vial", headers=h)
    assert r.status_code == 200
    lots = client.get(f"/api/stock/?antibody_id={ab['id']}", headers=h).json()
    assert [l["initial_volume_ul"] for l in lots] == [100]


def test_open_vial_leaves_legacy_store_volume_alone(h):
    """Prospective only: a store row from before the update (old 500 µl default)
    opens at its recorded volume; the store record is not rewritten."""
    ab = new_ab(h, "VV-CD56", vial=100)
    with Session(engine) as s:
        legacy = StoreStock(antibody_id=ab["id"], lot_no="E1", quantity=1, volume_per_vial_ul=500,
                            received_date=__import__("datetime").date(2026, 9, 1))
        s.add(legacy); s.commit(); s.refresh(legacy); sid = legacy.id

    assert client.post(f"/api/store-stock/{sid}/open-vial", headers=h).status_code == 200
    lot = client.get(f"/api/stock/?antibody_id={ab['id']}", headers=h).json()[0]
    assert lot["initial_volume_ul"] == 500 and not lot["notes"]
    with Session(engine) as s:
        row = s.get(StoreStock, sid)
        assert row.volume_per_vial_ul == 500 and not row.notes
    # ...and the new lot shows up in Volume check for manual review
    rep = client.get("/api/stock/volume-discrepancies", headers=h).json()
    assert lot["id"] in {l["lot_id"] for l in rep["lots"]}


def test_purchase_order_and_delivery(h):
    ab = new_ab(h, "VV-CD5", vial=100)
    r = client.post("/api/orders/", json={"antibody_id": ab["id"], "quantity_vials": 1,
                                          "order_date": "2026-10-01"}, headers=h)
    assert r.status_code == 200 and r.json()["volume_per_vial_ul"] == 100
    oid = r.json()["id"]

    d = {"lot_no": "F1", "shipment_id": "S3", "actual_volume_per_vial_ul": 500}
    assert client.post(f"/api/orders/{oid}/deliver", json=d, headers=h).status_code == 400
    d["actual_volume_per_vial_ul"] = None
    assert client.post(f"/api/orders/{oid}/deliver", json=d, headers=h).status_code == 200
    assert client.get(f"/api/stock/?antibody_id={ab['id']}", headers=h).json()[0]["initial_volume_ul"] == 100


# ── Discrepancy report and correction ────────────────────────────────────────

def _legacy_lot(ab_id, start, current, verified=False):
    import datetime as dt
    with Session(engine) as s:
        lot = StockLot(antibody_id=ab_id, lot_no="LEG", initial_volume_ul=start, current_volume_ul=current,
                       date_received=dt.date(2026, 8, 1),
                       last_verified_date=dt.date(2026, 9, 1) if verified else None)
        s.add(lot); s.commit(); s.refresh(lot)
        return lot.id


def test_discrepancy_report_and_correction(h):
    ab = new_ab(h, "VV-CD7", vial=100)
    unverified = _legacy_lot(ab["id"], start=500, current=460)     # 40 µl used
    verified = _legacy_lot(ab["id"], start=500, current=30, verified=True)

    rep = client.get("/api/stock/volume-discrepancies", headers=h).json()
    flagged = {l["lot_id"] for l in rep["lots"]}
    assert {unverified, verified} <= flagged

    # unverified: start AND remaining shift by -400
    r = client.post(f"/api/stock/{unverified}/correct-start-volume",
                    json={"correct_initial_volume_ul": 100, "reason": "typo"}, headers=h)
    assert r.status_code == 200
    assert r.json()["initial_volume_ul"] == 100 and r.json()["current_volume_ul"] == 60
    assert "[VOLUME CORRECTED]" in r.json()["notes"]

    # verified: remaining is a measurement and is left alone
    r = client.post(f"/api/stock/{verified}/correct-start-volume",
                    json={"correct_initial_volume_ul": 100, "reason": "typo"}, headers=h)
    assert r.json()["initial_volume_ul"] == 100 and r.json()["current_volume_ul"] == 30

    rep = client.get("/api/stock/volume-discrepancies", headers=h).json()
    assert not ({unverified, verified} & {l["lot_id"] for l in rep["lots"]})

    # "Keep": confirming a genuinely different vial stops it being flagged
    genuine = _legacy_lot(ab["id"], start=125, current=125)
    r = client.post(f"/api/stock/{genuine}/correct-start-volume",
                    json={"correct_initial_volume_ul": 125, "reason": "larger fill this lot"}, headers=h)
    assert r.json()["initial_volume_ul"] == 125 and "[VOLUME OVERRIDE]" in r.json()["notes"]
    rep = client.get("/api/stock/volume-discrepancies", headers=h).json()
    assert genuine not in {l["lot_id"] for l in rep["lots"]}

    # correction needs a reason
    assert client.post(f"/api/stock/{genuine}/correct-start-volume",
                       json={"correct_initial_volume_ul": 100, "reason": " "}, headers=h).status_code == 400


def test_report_lists_antibodies_without_volume(h):
    ab = new_ab(h, "VV-NOVOL")
    rep = client.get("/api/stock/volume-discrepancies", headers=h).json()
    assert ab["id"] in {a["antibody_id"] for a in rep["antibodies_without_volume"]}


# ── Worklist sample comment and flags ────────────────────────────────────────

@pytest.fixture(scope="module")
def staff(h):
    a = client.post("/api/staff/", json={"name": "Asha T", "role": "technologist"}, headers=h)
    b = client.post("/api/staff/", json={"name": "Ravi K", "role": "technologist"}, headers=h)
    assert a.status_code in (200, 201) and b.status_code in (200, 201), a.text
    return {"asha": a.json()["id"], "ravi": b.json()["id"]}


def _order(h, lab):
    ab = new_ab(h, f"VV-{lab}", vial=100)
    client.post("/api/stock/", json={"antibody_id": ab["id"], "lot_no": "G1",
                                     "date_received": "2026-10-01", "shipment_id": "S4"}, headers=h)
    panel = client.post("/api/panels/", json={"name": f"P-{lab}", "test_code": lab[:8]}, headers=h).json()["id"]
    client.post(f"/api/panels/{panel}/components", json={"antibody_id": ab["id"], "volume_per_tube_ul": 5}, headers=h)
    r = client.post("/api/sample-orders/", json={"lab_id": lab, "tubes": [{"panel_id": panel}]}, headers=h)
    assert r.status_code in (200, 207), r.text
    return r.json()["id"]

def test_sample_comment_needs_staff_any_status_and_csv(h, staff):
    oid = _order(h, "VV-0001")
    url = f"/api/sample-orders/{oid}/sample-comment"

    r = client.put(url, json={"comment": "Clotted"}, headers=h)                     # no staff name
    assert r.status_code == 400 and "staff" in r.json()["detail"].lower()

    r = client.put(url, json={"comment": "  Clotted; Low cell count ", "staff_id": staff["asha"]}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["sample_comment"] == "Clotted; Low cell count"
    assert body["sample_comment_staff_name"] == "Asha T"
    assert body["sample_comment_updated_by"] == "admin"          # the shared login, kept as well

    # still editable once the order is closed; the editor's name follows the latest edit
    assert client.post(f"/api/sample-orders/{oid}/cancel", headers=h).status_code == 200
    r = client.put(url, json={"comment": "Fibrin threads", "staff_id": staff["ravi"]}, headers=h)
    assert r.status_code == 200 and r.json()["sample_comment_staff_name"] == "Ravi K"

    csv = client.get("/api/sample-orders/export/worklist.csv", headers=h).text
    assert "comment_by" in csv.splitlines()[0] and "Ravi K" in csv

    r = client.put(url, json={"comment": "", "staff_id": staff["asha"]}, headers=h)
    assert r.json()["sample_comment"] is None
    assert client.put(url, json={"comment": "x" * 513, "staff_id": staff["asha"]}, headers=h).status_code == 400
    assert client.put(url, json={"comment": "x", "staff_id": 99999}, headers=h).status_code == 400


def test_sample_flags_tap_on_off(h, staff):
    opts = client.get("/api/sample-orders/sample-flags", headers=h).json()
    assert [o["code"] for o in opts] == ["fibrin", "low_volume", "lyse_issue"]

    oid = _order(h, "VV-0002")
    url = lambda code: f"/api/sample-orders/{oid}/flags/{code}"            # noqa: E731

    assert client.put(url("fibrin"), json={"on": True}, headers=h).status_code == 400   # staff required
    r = client.put(url("lyse_issue"), json={"on": True, "staff_id": staff["asha"]}, headers=h)
    r = client.put(url("fibrin"), json={"on": True, "staff_id": staff["asha"]}, headers=h)
    assert r.status_code == 200 and r.json()["sample_flags"] == ["fibrin", "lyse_issue"]   # display order
    assert r.json()["sample_flags_staff_name"] == "Asha T"

    # a repeated "on" (double tap / network retry) changes nothing and keeps the original author
    r = client.put(url("fibrin"), json={"on": True, "staff_id": staff["ravi"]}, headers=h)
    assert r.json()["sample_flags"] == ["fibrin", "lyse_issue"] and r.json()["sample_flags_staff_name"] == "Asha T"

    r = client.put(url("fibrin"), json={"on": False, "staff_id": staff["ravi"]}, headers=h)   # second tap clears
    assert r.json()["sample_flags"] == ["lyse_issue"] and r.json()["sample_flags_staff_name"] == "Ravi K"

    assert client.put(url("clotted"), json={"on": True, "staff_id": staff["ravi"]}, headers=h).status_code == 400

    # visible to the bench station and in the CSV
    q = client.get("/api/station/queue", headers=h).json()
    card = next(o for o in q["orders"] if o["id"] == oid)
    assert card["sample_flags"] == ["lyse_issue"]
    csv = client.get("/api/sample-orders/export/worklist.csv", headers=h).text
    assert "sample_flags" in csv.splitlines()[0] and "Lyse issue" in csv


# ── Export fix ───────────────────────────────────────────────────────────────

def test_inventory_export_works_with_lots(h):
    r = client.get("/api/export/inventory", headers=h)
    assert r.status_code == 200, r.text[:300]
    header = r.text.splitlines()[0]
    assert "initial_volume_ul" in header and "standard_vial_volume_ul" in header
    assert len(r.text.splitlines()) > 1
