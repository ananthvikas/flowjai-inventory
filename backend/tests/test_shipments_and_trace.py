"""
End-to-end API tests for shipment-to-shipment verification and cocktail
traceability. Runs against a throwaway SQLite DB.

    cd backend && python -m pytest tests/test_shipments_and_trace.py -q
"""

import io
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.database import create_db_and_tables, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Alert, ShipmentVerification  # noqa: E402

create_db_and_tables()
client = TestClient(app)


@pytest.fixture(scope="module")
def h():
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "Adm1n-pass-123"})
    if r.status_code != 201:      # another test module already ran first-run setup
        r = client.post("/api/auth/token", data={"username": "admin", "password": "Adm1n-pass-123"})
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def world(h):
    ab1 = client.post("/api/antibodies/", json={"name": "CD3"}, headers=h).json()["id"]
    ab2 = client.post("/api/antibodies/", json={"name": "CD19"}, headers=h).json()["id"]
    panel = client.post("/api/panels/", json={"name": "Screen", "test_code": "SC1"}, headers=h).json()["id"]
    for ab in (ab1, ab2):
        r = client.post(f"/api/panels/{panel}/components",
                        json={"antibody_id": ab, "volume_per_tube_ul": 5}, headers=h)
        assert r.status_code in (200, 201), r.text
    return {"ab1": ab1, "ab2": ab2, "panel": panel}


def receive(h, ab, lot, shipment, received="2026-09-01", qty=2):
    r = client.post("/api/store-stock/", json={
        "antibody_id": ab, "lot_no": lot, "quantity": qty, "volume_per_vial_ul": 500,
        "received_date": received, "shipment_id": shipment,
    }, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


# ── Shipment verification ────────────────────────────────────────────────────

def test_first_shipment_raises_nothing(h, world):
    row = receive(h, world["ab1"], "L100", "SH-001", received="2026-08-01")
    assert row["verification_triggered"] is False
    assert row["verification_status"] is None


def test_shipment_change_raises_verification_and_alert(h, world):
    row = receive(h, world["ab1"], "L100", " SH-002 ")          # same lot, new shipment
    assert row["shipment_id"] == "SH-002"                      # normalised
    assert row["verification_triggered"] is True
    assert row["verification_status"] == "pending"

    vs = client.get("/api/shipment-verifications/", headers=h).json()
    assert len(vs) == 1
    v = vs[0]
    assert v["previous_shipment_id"] == "SH-001"
    assert v["lot_changed"] is False
    assert 47 < v["hours_remaining"] <= 48

    alerts = client.get("/api/alerts/", headers=h).json()
    assert any(a["alert_type"] == "shipment_verification" for a in alerts)


def test_same_shipment_again_does_not_duplicate(h, world):
    row = receive(h, world["ab1"], "L100", "SH-002", qty=1)
    assert row["verification_triggered"] is False
    assert row["verification_status"] == "pending"
    assert len(client.get("/api/shipment-verifications/?status=all", headers=h).json()) == 1


def test_open_vial_carries_shipment(h, world):
    rows = client.get("/api/store-stock/", headers=h).json()
    sh2 = next(r for r in rows if r["shipment_id"] == "SH-002")
    assert client.post(f"/api/store-stock/{sh2['id']}/open-vial", headers=h).status_code == 200
    lots = client.get(f"/api/stock/?antibody_id={world['ab1']}", headers=h).json()
    assert any(l["shipment_id"] == "SH-002" for l in lots)


def test_legacy_untagged_stock_counts_as_previous(h, world):
    r = client.post("/api/stock/", json={
        "antibody_id": world["ab2"], "lot_no": "OLD9", "initial_volume_ul": 500,
        "date_received": "2026-07-01",
    }, headers=h)
    assert r.status_code == 200
    r = client.post("/api/stock/", json={
        "antibody_id": world["ab2"], "lot_no": "NEW1", "initial_volume_ul": 500,
        "date_received": "2026-09-01", "shipment_id": "SH-010",
    }, headers=h)
    assert r.status_code == 200 and r.json()["shipment_id"] == "SH-010"
    v = client.get(f"/api/shipment-verifications/?antibody_id={world['ab2']}", headers=h).json()[0]
    assert v["previous_shipment_id"] is None
    assert v["previous_lot_no"] == "OLD9"
    assert v["lot_changed"] is True


def test_close_requires_both_evidence_files(h, world):
    v = client.get(f"/api/shipment-verifications/?antibody_id={world['ab1']}", headers=h).json()[0]
    vid = v["id"]

    bad = client.post(f"/api/shipment-verifications/{vid}/attachments",
                      data={"role": "new"}, files={"file": ("x.exe", b"MZ", "application/octet-stream")}, headers=h)
    assert bad.status_code == 400

    ok = client.post(f"/api/shipment-verifications/{vid}/attachments",
                     data={"role": "new"}, files={"file": ("new.png", b"\x89PNG fake", "image/png")}, headers=h)
    assert ok.status_code == 200 and ok.json()["has_new_evidence"]

    r = client.post(f"/api/shipment-verifications/{vid}/close", json={"outcome": "acceptable"}, headers=h)
    assert r.status_code == 400 and "previous" in r.json()["detail"]

    client.post(f"/api/shipment-verifications/{vid}/attachments",
                data={"role": "previous"}, files={"file": ("prev.pdf", b"%PDF-1.4 fake", "application/pdf")}, headers=h)

    r = client.post(f"/api/shipment-verifications/{vid}/close", json={"outcome": "not_acceptable"}, headers=h)
    assert r.status_code == 400 and "Comments" in r.json()["detail"]

    r = client.post(f"/api/shipment-verifications/{vid}/close",
                    json={"outcome": "acceptable", "comments": "CD3 MFI within 10%"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "closed" and body["display_status"] == "acceptable"
    assert body["closed_late"] is False

    # evidence download works and is immutable after close
    att = body["attachments"][0]
    d = client.get(f"/api/shipment-verifications/attachments/{att['id']}", headers=h)
    assert d.status_code == 200 and len(d.content) == att["size_bytes"]
    assert client.delete(f"/api/shipment-verifications/attachments/{att['id']}", headers=h).status_code == 409

    # the raising alert is acknowledged on close
    with Session(engine) as s:
        v = s.get(ShipmentVerification, vid)
        assert s.get(Alert, v.alert_id).acknowledged_at is not None


def test_overdue_raises_one_alert(h, world):
    with Session(engine) as s:
        v = s.exec(__import__("sqlmodel").select(ShipmentVerification)
                   .where(ShipmentVerification.status == "open")).first()
        v.due_at = datetime.now() - timedelta(hours=3)
        s.add(v); s.commit()
    summ = client.get("/api/shipment-verifications/summary", headers=h).json()
    assert summ == {"open": 1, "overdue": 1}
    client.get("/api/shipment-verifications/", headers=h)
    client.get("/api/shipment-verifications/", headers=h)
    alerts = client.get("/api/alerts/", headers=h).json()
    assert sum(a["alert_type"] == "shipment_verification_overdue" for a in alerts) == 1


def test_po_delivery_records_shipment(h, world):
    o = client.post("/api/orders/", json={
        "antibody_id": world["ab2"], "quantity_vials": 2, "volume_per_vial_ul": 500,
        "order_date": "2026-09-10", "po_number": "PO-77",
    }, headers=h).json()
    r = client.post(f"/api/orders/{o['id']}/deliver",
                    json={"lot_no": "NEW2", "shipment_id": "SH-011", "delivery_date": "2026-09-20"}, headers=h)
    assert r.status_code == 200, r.text
    v = client.get("/api/shipment-verifications/?shipment_id=SH-011", headers=h).json()[0]
    assert v["previous_shipment_id"] == "SH-010"
    assert v["new_lot_no"] == "NEW2"          # manufacturer lot, not the "-1" vial suffix


def test_csv_log(h, world):
    r = client.get("/api/shipment-verifications/export/log.csv", headers=h)
    assert r.status_code == 200 and "new_shipment_id" in r.text and "SH-011" in r.text


# ── Cocktail traceability ────────────────────────────────────────────────────

def test_cocktail_trace(h, world):
    r = client.post("/api/cocktails/", json={"panel_id": world["panel"], "total_tests": 10}, headers=h)
    assert r.status_code in (201, 207), r.text
    cid = r.json()["id"]
    assert r.json()["cocktail_code"].startswith("SC1_")

    for lab in ("LAB-001", "LAB-002", "LAB-003"):
        o = client.post("/api/sample-orders/", json={"lab_id": lab, "tubes": [{"panel_id": world["panel"]}]}, headers=h)
        assert o.status_code == 200, o.text
        if lab != "LAB-003":
            assert client.post(f"/api/sample-orders/{o.json()['id']}/start", headers=h).status_code == 200

    # 2 tests logged manually, without lab IDs
    assert client.post(f"/api/cocktails/{cid}/use",
                       json={"test_date": date.today().isoformat(), "count": 2}, headers=h).status_code == 200

    t = client.get(f"/api/cocktails/{cid}/trace", headers=h).json()
    assert [s["lab_id"] for s in t["samples"]] == ["LAB-001", "LAB-002", "LAB-003"]
    assert t["samples_run"] == 2 and t["samples_reserved"] == 1
    assert t["untracked_tests"] == 2
    shipments = {c["shipment_id"] for c in t["components"]}
    assert "SH-002" in shipments                           # CD3 drawn from the opened SH-002 vial
    cd3 = next(c for c in t["components"] if c["shipment_id"] == "SH-002")
    assert cd3["shipment_verification_status"] == "acceptable"

    # a second cocktail drawing the same lots shows up as related
    r2 = client.post("/api/cocktails/", json={"panel_id": world["panel"], "total_tests": 5}, headers=h)
    t = client.get(f"/api/cocktails/{cid}/trace", headers=h).json()
    assert any(rc["id"] == r2.json()["id"] for rc in t["related_cocktails"])

    csv_r = client.get(f"/api/cocktails/{cid}/trace.csv", headers=h)
    assert csv_r.status_code == 200 and "LAB-002" in csv_r.text and "without lab IDs" in csv_r.text

    ws = client.get(f"/api/cocktails/{cid}/worksheet", headers=h)
    assert ws.status_code == 200 and "Lot / Shipment" in ws.text and "SH-002" in ws.text


def test_worklist_lab_id_search(h, world):
    rows = client.get("/api/sample-orders/?lab_id=lab-002", headers=h).json()
    assert [r["lab_id"] for r in rows] == ["LAB-002"]
    assert rows[0]["tubes"][0]["cocktail_code"].startswith("SC1_")


# ── Staff names on shared-login actions ──────────────────────────────────────

def test_cocktail_prepared_by_staff_and_log(h, world):
    sid = client.post("/api/staff/", json={"name": "Priya R", "role": "technologist"}, headers=h).json()["id"]
    r = client.post("/api/cocktails/", json={"panel_id": world["panel"], "total_tests": 2,
                                              "prepared_by_staff_id": sid}, headers=h)
    assert r.status_code in (201, 207), r.text
    assert r.json()["prepared_by_name"] == "Priya R"
    assert r.json()["prepared_at"]

    bad = client.post("/api/cocktails/", json={"panel_id": world["panel"], "total_tests": 1,
                                                "prepared_by_staff_id": 9999}, headers=h)
    assert bad.status_code == 400

    log = client.get(f"/api/cocktails/?active_only=false&prepared_by_staff_id={sid}", headers=h).json()
    assert len(log) == 1 and log[0]["prepared_by_name"] == "Priya R"
    everything = client.get("/api/cocktails/?active_only=false", headers=h).json()
    assert any(c["prepared_by_name"] == "admin" for c in everything)   # legacy fallback

    t = client.get(f"/api/cocktails/{r.json()['id']}/trace", headers=h).json()
    assert t["cocktail"]["prepared_by"] == "Priya R"
    csv_r = client.get("/api/cocktails/export/summary.csv", headers=h)
    assert "Priya R" in csv_r.text and "prepared_at" in csv_r.text


def test_verification_signed_by_staff(h, world):
    sid = client.post("/api/staff/", json={"name": "Dr Vikas", "role": "pathologist"}, headers=h).json()["id"]
    v = client.get("/api/shipment-verifications/?status=open", headers=h).json()[0]
    for role, name in (("previous", "p.pdf"), ("new", "n.pdf")):
        client.post(f"/api/shipment-verifications/{v['id']}/attachments",
                    data={"role": role}, files={"file": (name, b"%PDF x", "application/pdf")}, headers=h)
    r = client.post(f"/api/shipment-verifications/{v['id']}/close",
                    json={"outcome": "acceptable", "closed_by_staff_id": sid}, headers=h)
    assert r.status_code == 200 and r.json()["closed_by_username"] == "Dr Vikas"
