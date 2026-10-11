"""Bench processing station: per-tube steps, cocktail consumption, undo, auto-complete."""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Share one throwaway DB per pytest run (see conftest.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.database import create_db_and_tables, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Cocktail, SampleOrderTubeStep  # noqa: E402

create_db_and_tables()
client = TestClient(app)


@pytest.fixture(scope="module")
def h():
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "Adm1n-pass-123"})
    if r.status_code != 201:
        r = client.post("/api/auth/token", data={"username": "admin", "password": "Adm1n-pass-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def w(h):
    ab = client.post("/api/antibodies/", json={"name": "CD4"}, headers=h).json()["id"]
    client.post("/api/stock/", json={"antibody_id": ab, "lot_no": "L1", "initial_volume_ul": 5000,
                                    "date_received": "2026-09-01"}, headers=h)
    surf = client.post("/api/panels/", json={"name": "Surface", "test_code": "S1"}, headers=h).json()["id"]
    intra = client.post("/api/panels/", json={"name": "Intracellular", "test_code": "IC1"}, headers=h).json()["id"]
    for p in (surf, intra):
        client.post(f"/api/panels/{p}/components", json={"antibody_id": ab, "volume_per_tube_ul": 5}, headers=h)
    r = client.put(f"/api/station/templates/{intra}",
                   json={"names": ["Surface stain added", "Fixed", "Permeabilised", "Intracellular stain", "Acquired"]},
                   headers=h)
    assert r.status_code == 200 and r.json()["source"] == "panel"
    c1 = client.post("/api/cocktails/", json={"panel_id": surf, "total_tests": 5}, headers=h).json()["id"]
    c2 = client.post("/api/cocktails/", json={"panel_id": intra, "total_tests": 5}, headers=h).json()["id"]
    staff = client.post("/api/staff/", json={"name": "Anitha K", "role": "technologist"}, headers=h).json()["id"]
    return {"surf": surf, "intra": intra, "c1": c1, "c2": c2, "staff": staff}


def _cocktail(cid):
    with Session(engine) as s:
        c = s.get(Cocktail, cid)
        return c.remaining_tests, c.reserved_tests


def test_templates_listing(h, w):
    t = client.get("/api/station/templates", headers=h).json()
    by = {p["test_code"]: p for p in t["panels"]}
    assert by["S1"]["source"] == "built_in" and by["S1"]["names"][0] == "Cocktail added"
    assert by["IC1"]["names"][1] == "Fixed"
    assert client.put("/api/station/templates/default", json={"names": ["only one"]}, headers=h).status_code == 400


def test_full_flow(h, w):
    o = client.post("/api/sample-orders/", json={"lab_id": "S-100", "priority": "urgent",
                                                 "tubes": [{"panel_id": w["surf"]}, {"panel_id": w["intra"]}]},
                    headers=h).json()
    q = client.get("/api/station/queue", headers=h).json()
    card = next(c for c in q["orders"] if c["id"] == o["id"])
    surf_t = next(t for t in card["tubes"] if t["test_code"] == "S1")
    intra_t = next(t for t in card["tubes"] if t["test_code"] == "IC1")
    assert len(surf_t["steps"]) == 4 and len(intra_t["steps"]) == 5
    assert _cocktail(w["c1"]) == (5, 1)

    # out-of-order tap refused
    r = client.post(f"/api/station/tubes/{surf_t['id']}/steps/2/complete", json={}, headers=h)
    assert r.status_code == 409

    # step 1 consumes only that tube's cocktail test and starts the order
    r = client.post(f"/api/station/tubes/{surf_t['id']}/steps/1/complete", json={"staff_id": w["staff"]}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_processing" and r.json()["technologist"] == "Anitha K"
    assert _cocktail(w["c1"]) == (4, 0)
    assert _cocktail(w["c2"]) == (5, 1)        # the other tube is still only reserved

    # mis-tap undo on step 1 reverses consumption and puts the order back in queue
    r = client.post(f"/api/station/tubes/{surf_t['id']}/steps/1/undo", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "in_queue"
    assert _cocktail(w["c1"]) == (5, 1)

    # batch advance: "Cocktail added" is step 1 for S1 only (IC1 starts with "Surface stain added")
    r = client.post(f"/api/station/orders/{o['id']}/advance",
                    json={"step_name": "Cocktail added", "staff_id": w["staff"]}, headers=h)
    assert r.status_code == 200
    for t in (surf_t, intra_t):
        steps = client.get("/api/station/queue", headers=h).json()["orders"][0]["tubes"]
    # finish every step of both tubes
    for t in (surf_t, intra_t):
        while True:
            card = next(c for c in client.get("/api/station/queue", headers=h).json()["orders"] + 
                        client.get("/api/station/queue", headers=h).json()["recent"] if c["id"] == o["id"])
            tube = next(x for x in card["tubes"] if x["id"] == t["id"])
            if tube["next_seq"] is None:
                break
            r = client.post(f"/api/station/tubes/{t['id']}/steps/{tube['next_seq']}/complete",
                            json={"staff_id": w["staff"]}, headers=h)
            assert r.status_code == 200, r.text

    q = client.get("/api/station/queue", headers=h).json()
    assert all(c["id"] != o["id"] for c in q["orders"])          # left the pending list
    assert any(c["id"] == o["id"] for c in q["recent"])          # visible for recall
    wl = client.get("/api/sample-orders/?lab_id=S-100", headers=h).json()[0]
    assert wl["status"] == "completed" and wl["tat_minutes"] is not None
    assert {t["steps_done"] for t in wl["tubes"]} == {4, 5}

    # undo the final step re-opens the order
    r = client.post(f"/api/station/tubes/{intra_t['id']}/steps/5/undo", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "in_processing"

    # undo window enforced
    with Session(engine) as s:
        st = s.exec(select(SampleOrderTubeStep).where(SampleOrderTubeStep.tube_id == intra_t["id"])
                    .where(SampleOrderTubeStep.seq == 4)).first()
        st.completed_at = datetime.now() - timedelta(minutes=30)
        s.add(st); s.commit()
    assert client.post(f"/api/station/tubes/{intra_t['id']}/steps/4/undo", headers=h).status_code == 409


def test_worklist_buttons_still_work(h, w):
    o = client.post("/api/sample-orders/", json={"lab_id": "S-200", "tubes": [{"panel_id": w["surf"]}]}, headers=h).json()
    assert client.post(f"/api/sample-orders/{o['id']}/start", headers=h).status_code == 200
    r = client.post(f"/api/sample-orders/{o['id']}/complete", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert r.json()["tubes"][0]["steps_done"] == r.json()["tubes"][0]["steps_total"]


def test_template_edit_does_not_touch_inflight(h, w):
    o = client.post("/api/sample-orders/", json={"lab_id": "S-300", "tubes": [{"panel_id": w["surf"]}]}, headers=h).json()
    client.put(f"/api/station/templates/{w['surf']}", json={"names": ["A", "B"]}, headers=h)
    card = next(c for c in client.get("/api/station/queue", headers=h).json()["orders"] if c["id"] == o["id"])
    assert len(card["tubes"][0]["steps"]) == 4


def test_station_token_role(h, w):
    assert client.post("/api/auth/station-token", headers=h).status_code == 403   # admin refused
    client.post("/api/users/", json={"username": "bench", "password": "Bench-pass-123", "role": "technologist"}, headers=h)
    tok = client.post("/api/auth/token", data={"username": "bench", "password": "Bench-pass-123"}).json()["access_token"]
    r = client.post("/api/auth/station-token", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()["role"] == "technologist"


def test_timers(h, w):
    from app.models import SampleOrderTubeStep
    r = client.put(f"/api/station/templates/{w['surf']}", json={"steps": [
        {"name": "Cocktail added", "wait_minutes": 99},         # ignored on step 1
        {"name": "Incubated", "wait_minutes": 15},
        {"name": "Acquired"},
    ]}, headers=h)
    assert r.status_code == 200, r.text
    assert [s["wait_minutes"] for s in r.json()["steps"]] == [None, 15, None]
    bad = client.put(f"/api/station/templates/{w['surf']}", json={"steps": [
        {"name": "A"}, {"name": "B", "wait_minutes": -3}]}, headers=h)
    assert bad.status_code == 400

    o = client.post("/api/sample-orders/", json={"lab_id": "T-1", "tubes": [{"panel_id": w["surf"]}]}, headers=h).json()
    tube = o["tubes"][0]["id"]
    assert client.post(f"/api/station/tubes/{tube}/steps/1/complete", json={}, headers=h).status_code == 200

    card = next(c for c in client.get("/api/station/queue", headers=h).json()["orders"] if c["id"] == o["id"])
    inc = card["tubes"][0]["steps"][1]
    assert inc["wait_minutes"] == 15 and inc["ready_at"]

    # early tap refused with a machine-readable code, then allowed with force
    r = client.post(f"/api/station/tubes/{tube}/steps/2/complete", json={}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "timer_not_elapsed"
    assert 14 * 60 < r.json()["remaining_seconds"] <= 15 * 60
    r = client.post(f"/api/station/tubes/{tube}/steps/2/complete", json={"force": True}, headers=h)
    assert r.status_code == 200
    assert r.json()["tubes"][0]["steps"][1]["completed_early_seconds"] > 14 * 60

    # once the wait has passed, no confirmation needed
    client.post(f"/api/station/tubes/{tube}/steps/2/undo", headers=h)
    with Session(engine) as s:
        st1 = s.exec(select(SampleOrderTubeStep).where(SampleOrderTubeStep.tube_id == tube)
                     .where(SampleOrderTubeStep.seq == 1)).first()
        st1.completed_at = datetime.now() - timedelta(minutes=16)
        s.add(st1); s.commit()
    r = client.post(f"/api/station/tubes/{tube}/steps/2/complete", json={}, headers=h)
    assert r.status_code == 200 and r.json()["tubes"][0]["steps"][1]["completed_early_seconds"] is None


def test_health_checks_database():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_timers_apply_to_samples_already_on_board(h, w):
    """Regression: timers set after a sample was queued must still show for it."""
    client.put(f"/api/station/templates/{w['surf']}", json={"steps": [
        {"name": "Cocktail added"}, {"name": "Incubated"}, {"name": "Acquired"}]}, headers=h)
    o = client.post("/api/sample-orders/", json={"lab_id": "T-LIVE", "tubes": [{"panel_id": w["surf"]}]}, headers=h).json()
    tube = o["tubes"][0]["id"]
    client.post(f"/api/station/tubes/{tube}/steps/1/complete", json={}, headers=h)

    r = client.put(f"/api/station/templates/{w['surf']}", json={"steps": [
        {"name": "Cocktail added"}, {"name": "Incubated", "wait_minutes": 20}, {"name": "Acquired"}]}, headers=h)
    assert r.json()["live_tubes_updated"] >= 1
    card = next(c for c in client.get("/api/station/queue", headers=h).json()["orders"] if c["id"] == o["id"])
    inc = card["tubes"][0]["steps"][1]
    assert inc["wait_minutes"] == 20 and inc["ready_at"] is not None

    # completed steps are never rewritten; removing a timer clears it on pending steps
    r = client.put(f"/api/station/templates/{w['surf']}", json={"steps": [
        {"name": "Cocktail added"}, {"name": "Incubated"}, {"name": "Acquired"}]}, headers=h)
    card = next(c for c in client.get("/api/station/queue", headers=h).json()["orders"] if c["id"] == o["id"])
    assert card["tubes"][0]["steps"][1]["wait_minutes"] is None
    assert card["tubes"][0]["steps"][0]["completed_at"] is not None
