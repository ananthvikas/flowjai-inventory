"""
seed.py — Demo data for evaluation and development.

Panels included:
  1. Lymphocyte Subset Screen (LSS) — 8-colour
  2. B-ALL MRD (BMRD) — 12-colour (simplified for demo)
  3. T/NK panel (TNK) — 10-colour

Evaluation only. Load it on a throwaway install with:  python run.py --demo
Never run it against a live laboratory database.
"""

from datetime import date, timedelta
from random import randint, uniform

from sqlmodel import Session, select

from app.auth import hash_password
from app.database import create_db_and_tables, engine
from app.models import (
    Alert,
    AlertRule,
    Antibody,
    AntibodyAlternative,
    ConsumptionLog,
    Fluorochrome,
    Panel,
    PanelComponent,
    StockLot,
    TestLog,
    User,
)


def seed():
    create_db_and_tables()

    with Session(engine) as session:
        # Skip if already seeded
        if session.exec(select(User)).first():
            print("Database already seeded — skipping.")
            return

        print("Seeding demo data...")

        # ----------------------------------------------------------------
        # Users
        # ----------------------------------------------------------------
        admin = User(
            username="admin",
            email="admin@flowjai.lab",
            hashed_password=hash_password("admin123"),
            role="admin",
        )
        tech = User(
            username="technologist",
            email="tech@flowjai.lab",
            hashed_password=hash_password("tech123"),
            role="technologist",
        )
        svc = User(
            username="service",
            email="service@flowjai.lab",
            hashed_password=hash_password("ecivres"),
            role="service",
        )
        session.add_all([admin, tech, svc])
        session.flush()

        # ----------------------------------------------------------------
        # Fluorochromes
        # ----------------------------------------------------------------
        fluors = {
            name: Fluorochrome(name=name, excitation_nm=ex, emission_nm=em, laser=laser)
            for name, ex, em, laser in [
                ("FITC",  488, 519,  "Blue 488nm"),
                ("PE",    488, 578,  "Blue 488nm"),
                ("PE-Cy7",488, 785,  "Blue 488nm"),
                ("APC",   638, 660,  "Red 638nm"),
                ("APC-H7",638, 785,  "Red 638nm"),
                ("BV421", 405, 421,  "Violet 405nm"),
                ("BV510", 405, 510,  "Violet 405nm"),
                ("BV605", 405, 605,  "Violet 405nm"),
                ("BV711", 405, 711,  "Violet 405nm"),
                ("BV786", 405, 786,  "Violet 405nm"),
                ("PerCP-Cy5.5", 488, 695, "Blue 488nm"),
                ("PE-CF594", 488, 612, "Blue 488nm"),
            ]
        }
        for fc in fluors.values():
            session.add(fc)
        session.flush()

        # ----------------------------------------------------------------
        # Antibodies
        # ----------------------------------------------------------------
        ab_data = [
            # (name, clone, vendor, fluorochrome_name)
            ("CD45",  "2B11",    "BD",        "PerCP-Cy5.5"),
            ("CD3",   "UCHT1",   "BD",        "PE-Cy7"),
            ("CD4",   "RPA-T4",  "BD",        "APC-H7"),
            ("CD8",   "RPA-T8",  "BD",        "FITC"),
            ("CD19",  "SJ25C1",  "BD",        "BV421"),
            ("CD16",  "3G8",     "BD",        "PE"),
            ("CD56",  "NCAM16.2","BD",        "APC"),
            ("CD38",  "HIT2",    "BD",        "APC"),
            ("CD10",  "HI10a",   "BioLegend", "BV421"),
            ("CD20",  "2H7",     "BioLegend", "BV510"),
            ("CD34",  "581",     "BD",        "PE-CF594"),
            ("CD58",  "2-82",    "BD",        "BV711"),
            ("CD66c", "B13.9",   "BD",        "BV605"),
            ("CD123", "7G3",     "BD",        "BV786"),
            ("CD33",  "P67.6",   "BD",        "PE"),
            ("TdT",   "HZB-55",  "Dako",      "FITC"),
            ("CD7",   "M-T701",  "BD",        "BV421"),
            ("CD5",   "UCHT2",   "BD",        "PE"),
            # PE alternatives for CD3 and CD4
            ("CD3",   "SK7",     "BioLegend", "APC"),
            ("CD4",   "OKT4",    "BioLegend", "PE"),
        ]
        abs_map: dict[str, list[Antibody]] = {}
        for name, clone, vendor, fluor_name in ab_data:
            ab = Antibody(
                name=name,
                clone=clone,
                vendor=vendor,
                catalog_no=f"{vendor[:2].upper()}-{name}-{fluor_name[:2]}",
                fluorochrome_id=fluors[fluor_name].id,
            )
            session.add(ab)
            abs_map.setdefault(name, []).append(ab)
        session.flush()

        # For convenience, grab first instance of each marker
        def ab(name: str) -> Antibody:
            return abs_map[name][0]

        # ----------------------------------------------------------------
        # Alternatives: CD3-APC and CD4-PE as fallbacks
        # ----------------------------------------------------------------
        session.add(AntibodyAlternative(
            antibody_id=ab("CD3").id,
            alt_antibody_id=abs_map["CD3"][1].id,
            note="Same panel position, different fluor — update panel comp table if substituting",
        ))
        session.add(AntibodyAlternative(
            antibody_id=ab("CD4").id,
            alt_antibody_id=abs_map["CD4"][1].id,
            note="PE channel — check for PE tandem bleedthrough in 12-colour config",
        ))
        session.flush()

        # ----------------------------------------------------------------
        # Panels
        # ----------------------------------------------------------------
        lss = Panel(name="Lymphocyte Subset Screen", test_code="LSS", department="Haematology")
        bmrd = Panel(name="B-ALL MRD 12-colour", test_code="BMRD", department="Haematology")
        tnk = Panel(name="T/NK Panel", test_code="TNK", department="Haematology")
        session.add_all([lss, bmrd, tnk])
        session.flush()

        # LSS components: CD45, CD3, CD4, CD8, CD19, CD16, CD56
        lss_components = [
            (ab("CD45"),  5.0, 1),
            (ab("CD3"),   5.0, 1),
            (ab("CD4"),   5.0, 1),
            (ab("CD8"),   5.0, 1),
            (ab("CD19"),  5.0, 1),
            (ab("CD16"),  10.0, 1),
            (ab("CD56"),  5.0, 1),
        ]
        for antibody, vol, tubes in lss_components:
            session.add(PanelComponent(
                panel_id=lss.id, antibody_id=antibody.id,
                volume_per_tube_ul=vol, tubes_per_test=tubes,
            ))

        # BMRD components: 12-colour MRD panel (B-ALL)
        bmrd_components = [
            (ab("CD45"),  5.0, 1),
            (ab("CD19"),  5.0, 1),
            (ab("CD10"),  5.0, 1),
            (ab("CD20"),  5.0, 1),
            (ab("CD34"),  5.0, 1),
            (ab("CD38"),  5.0, 1),
            (ab("CD58"),  5.0, 1),
            (ab("CD66c"), 10.0, 1),
            (ab("CD123"), 5.0, 1),
            (ab("TdT"),   5.0, 1),
            (ab("CD7"),   5.0, 1),
        ]
        for antibody, vol, tubes in bmrd_components:
            session.add(PanelComponent(
                panel_id=bmrd.id, antibody_id=antibody.id,
                volume_per_tube_ul=vol, tubes_per_test=tubes,
            ))

        # TNK components
        tnk_components = [
            (ab("CD45"),  5.0, 1),
            (ab("CD3"),   5.0, 1),
            (ab("CD4"),   5.0, 1),
            (ab("CD8"),   5.0, 1),
            (ab("CD56"),  5.0, 1),
            (ab("CD16"),  10.0, 1),
            (ab("CD5"),   5.0, 1),
            (ab("CD7"),   5.0, 1),
        ]
        for antibody, vol, tubes in tnk_components:
            session.add(PanelComponent(
                panel_id=tnk.id, antibody_id=antibody.id,
                volume_per_tube_ul=vol, tubes_per_test=tubes,
            ))
        session.flush()

        # ----------------------------------------------------------------
        # Stock Lots — varied levels to show dashboard states
        # ----------------------------------------------------------------
        stock_scenarios = [
            # (antibody, lot_no, initial_ul, current_ul, days_ago_received, expiry_days_ahead)
            (ab("CD45"),  "LOT-CD45-01", 1000, 280,  90, 300),
            (ab("CD3"),   "LOT-CD3-01",  500,  45,   60, 180),   # ← LOW — should trigger alert
            (ab("CD4"),   "LOT-CD4-01",  500,  380,  30, 270),
            (ab("CD8"),   "LOT-CD8-01",  500,  490,  10, 365),
            (ab("CD19"),  "LOT-CD19-01", 500,  220,  45, 250),
            (ab("CD16"),  "LOT-CD16-01", 1000, 600,  20, 300),
            (ab("CD56"),  "LOT-CD56-01", 500,  150,  50, 180),
            (ab("CD38"),  "LOT-CD38-01", 500,  480,   5, 365),
            (ab("CD10"),  "LOT-CD10-01", 500,  300,  40, 200),
            (ab("CD20"),  "LOT-CD20-01", 500,  100,  60, 120),   # ← expiry warning scenario
            (ab("CD34"),  "LOT-CD34-01", 500,  350,  25, 300),
            (ab("CD58"),  "LOT-CD58-01", 500,  420,  15, 350),
            (ab("CD66c"), "LOT-CD66-01", 1000, 750,  10, 365),
            (ab("CD123"), "LOT-CD123-01",500,  250,  30, 240),
            (ab("TdT"),   "LOT-TDT-01",  500,  460,   7, 300),
            (ab("CD7"),   "LOT-CD7-01",  500,  180,  55, 200),
            (ab("CD5"),   "LOT-CD5-01",  500,  400,  20, 300),
            (ab("CD33"),  "LOT-CD33-01", 500,  490,   3, 365),
        ]
        lots_map: dict[int, StockLot] = {}
        today = date.today()
        for antibody, lot_no, initial, current, days_ago, expiry_days in stock_scenarios:
            lot = StockLot(
                antibody_id=antibody.id,
                lot_no=lot_no,
                initial_volume_ul=initial,
                current_volume_ul=current,
                date_received=today - timedelta(days=days_ago),
                date_opened=today - timedelta(days=days_ago - 1),
                expiry_date=today + timedelta(days=expiry_days),
            )
            session.add(lot)
            lots_map[antibody.id] = lot
        session.flush()

        # ----------------------------------------------------------------
        # Historical test logs + consumption (90 days)
        # ----------------------------------------------------------------
        # Realistic daily volumes: LSS ~8/day, BMRD ~4/day, TNK ~3/day
        panels_schedule = [
            (lss,  8, 3),   # (panel, avg_daily, std_dev)
            (bmrd, 4, 2),
            (tnk,  3, 1),
        ]
        for days_back in range(90, 0, -1):
            log_date = today - timedelta(days=days_back)
            if log_date.weekday() >= 5:  # skip weekends
                continue

            for panel_obj, avg, std in panels_schedule:
                count = max(1, round(avg + uniform(-std, std)))
                log = TestLog(
                    test_date=log_date,
                    panel_id=panel_obj.id,
                    count=count,
                    entry_method="seed_data",
                    entered_by=tech.id,
                )
                session.add(log)
                session.flush()

                # Simplified consumption: deduct from the lot directly
                # (bypassing full FIFO logic to keep seed fast)
                panel_comps = session.exec(
                    select(PanelComponent).where(PanelComponent.panel_id == panel_obj.id)
                ).all()
                for comp in panel_comps:
                    lot = lots_map.get(comp.antibody_id)
                    if not lot:
                        continue
                    vol = round(comp.ul_per_test() * count, 2)
                    clog = ConsumptionLog(
                        test_log_id=log.id,
                        antibody_id=comp.antibody_id,
                        stock_lot_id=lot.id,
                        volume_consumed_ul=vol,
                    )
                    session.add(clog)

        # ----------------------------------------------------------------
        # Alert rules (non-default thresholds for CD3 — it's critical)
        # ----------------------------------------------------------------
        session.add(AlertRule(
            antibody_id=ab("CD3").id,
            lead_time_days=35,
            safety_stock_ul=50.0,
            alert_threshold_days=45,
        ))

        session.commit()
        print("✓ Seed complete.")
        print("  Service login:      service / ecivres   (validation access)")
        print("  Admin login:        admin / admin123")
        print("  Technologist login: technologist / tech123")
        print("  CD3 is seeded low — run /api/alerts/run to see shortage alert.")


if __name__ == "__main__":
    seed()
