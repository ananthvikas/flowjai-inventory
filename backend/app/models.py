"""
models.py - SQLModel table definitions for flowjAI Inventory Manager.

Key rules for SQLModel 0.0.37 + SQLAlchemy 2.0 + Pydantic 2.x:
  - No from __future__ import annotations
  - Forward refs use quoted strings: List["X"], Optional["X"]
  - No @property on table classes - use plain methods
  - test_date not date in TestLog (avoids shadowing datetime.date)
"""

from datetime import date, datetime
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    """Return the current local system datetime. Used as default_factory for
    timestamp fields so the application uses the machine's local time."""
    return datetime.now()


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=64)
    email: Optional[str] = Field(default=None, max_length=128)
    hashed_password: str
    role: str = Field(default="technologist")
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)

    test_logs: List["TestLog"] = Relationship(back_populates="entered_by_user")
    orders_created: List["Order"] = Relationship(back_populates="created_by_user")
    alerts_acknowledged: List["Alert"] = Relationship(back_populates="acknowledged_by_user")
    cocktails_prepared: List["Cocktail"] = Relationship(back_populates="prepared_by_user")
    cocktail_usage_logs: List["CocktailUsageLog"] = Relationship(back_populates="entered_by_user")


class Fluorochrome(SQLModel, table=True):
    __tablename__ = "fluorochromes"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=32)
    excitation_nm: Optional[int] = None
    emission_nm: Optional[int] = None
    laser: Optional[str] = Field(default=None, max_length=32)

    antibodies: List["Antibody"] = Relationship(back_populates="fluorochrome")


class Antibody(SQLModel, table=True):
    __tablename__ = "antibodies"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=64)
    clone: Optional[str] = Field(default=None, max_length=64)
    vendor: Optional[str] = Field(default=None, max_length=64)
    catalog_no: Optional[str] = Field(default=None, max_length=64)
    # Standard fill volume for this catalogue number. When set, every receipt and
    # vial opening uses it unless a different volume is entered WITH a reason.
    vial_volume_ul: Optional[float] = None
    fluorochrome_id: Optional[int] = Field(default=None, foreign_key="fluorochromes.id")
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)

    fluorochrome: Optional["Fluorochrome"] = Relationship(back_populates="antibodies")
    panel_components: List["PanelComponent"] = Relationship(back_populates="antibody")
    stock_lots: List["StockLot"] = Relationship(back_populates="antibody")
    consumption_logs: List["ConsumptionLog"] = Relationship(back_populates="antibody")
    orders: List["Order"] = Relationship(back_populates="antibody")
    alert_rules: List["AlertRule"] = Relationship(back_populates="antibody")
    alerts: List["Alert"] = Relationship(back_populates="antibody")

    alternatives_from: List["AntibodyAlternative"] = Relationship(
        back_populates="source_antibody",
        sa_relationship_kwargs={"foreign_keys": "[AntibodyAlternative.antibody_id]"},
    )
    alternatives_to: List["AntibodyAlternative"] = Relationship(
        back_populates="alt_antibody",
        sa_relationship_kwargs={"foreign_keys": "[AntibodyAlternative.alt_antibody_id]"},
    )


class AntibodyAlternative(SQLModel, table=True):
    __tablename__ = "antibody_alternatives"

    id: Optional[int] = Field(default=None, primary_key=True)
    antibody_id: int = Field(foreign_key="antibodies.id", index=True)
    alt_antibody_id: int = Field(foreign_key="antibodies.id")
    note: Optional[str] = Field(default=None, max_length=256)

    source_antibody: Optional["Antibody"] = Relationship(
        back_populates="alternatives_from",
        sa_relationship_kwargs={"foreign_keys": "[AntibodyAlternative.antibody_id]"},
    )
    alt_antibody: Optional["Antibody"] = Relationship(
        back_populates="alternatives_to",
        sa_relationship_kwargs={"foreign_keys": "[AntibodyAlternative.alt_antibody_id]"},
    )


class Panel(SQLModel, table=True):
    __tablename__ = "panels"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=128)
    test_code: str = Field(index=True, max_length=32)          # tube/panel code e.g. CL1, CL2
    test_group: Optional[str] = Field(default=None, index=True, max_length=64)  # protocol e.g. cLPD
    department: Optional[str] = Field(default=None, max_length=64)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)

    components: List["PanelComponent"] = Relationship(back_populates="panel")
    test_logs: List["TestLog"] = Relationship(back_populates="panel")
    cocktails: List["Cocktail"] = Relationship(back_populates="panel")


class PanelComponent(SQLModel, table=True):
    __tablename__ = "panel_components"

    id: Optional[int] = Field(default=None, primary_key=True)
    panel_id: int = Field(foreign_key="panels.id", index=True)
    antibody_id: int = Field(foreign_key="antibodies.id", index=True)
    volume_per_tube_ul: float
    tubes_per_test: int = Field(default=1)

    panel: Optional["Panel"] = Relationship(back_populates="components")
    antibody: Optional["Antibody"] = Relationship(back_populates="panel_components")

    def ul_per_test(self) -> float:
        return self.volume_per_tube_ul * self.tubes_per_test


class StockLot(SQLModel, table=True):
    __tablename__ = "stock_lots"

    id: Optional[int] = Field(default=None, primary_key=True)
    antibody_id: int = Field(foreign_key="antibodies.id", index=True)
    lot_no: str = Field(max_length=64)
    initial_volume_ul: float
    current_volume_ul: float
    date_received: date
    date_opened: Optional[date] = None
    expiry_date: Optional[date] = None
    last_verified_date: Optional[date] = None
    last_verified_volume_ul: Optional[float] = None
    empty_vial_tare_g: Optional[float] = None   # per-vial empty weight; removes inter-vial tare variation in gravimetric verification
    # Vendor shipment this vial arrived in. Carried over from StoreStock when a
    # vial is opened, so every cocktail can be traced back to a shipment.
    shipment_id: Optional[str] = Field(default=None, max_length=64, index=True)
    # Audit notes: non-standard starting volume, starting-volume corrections.
    notes: Optional[str] = Field(default=None, max_length=1024)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)

    antibody: Optional["Antibody"] = Relationship(back_populates="stock_lots")
    consumption_logs: List["ConsumptionLog"] = Relationship(back_populates="stock_lot")


class TestLog(SQLModel, table=True):
    __tablename__ = "test_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    test_date: date = Field(index=True)
    panel_id: Optional[int] = Field(default=None, foreign_key="panels.id", index=True)
    panel_name_adhoc: Optional[str] = Field(default=None, max_length=128)  # label for ad hoc logs
    count: int
    entry_method: str = Field(default="manual")
    entered_by: int = Field(foreign_key="users.id")
    notes: Optional[str] = Field(default=None, max_length=512)
    created_at: datetime = Field(default_factory=utc_now)

    panel: Optional["Panel"] = Relationship(back_populates="test_logs")
    entered_by_user: Optional["User"] = Relationship(back_populates="test_logs")
    consumption_logs: List["ConsumptionLog"] = Relationship(back_populates="test_log")


class ConsumptionLog(SQLModel, table=True):
    """
    Records antibody volume deducted from a stock lot.
    Linked to either a TestLog (fresh stock run) or a Cocktail (mixing event).
    Exactly one of test_log_id / cocktail_id will be set.
    """
    __tablename__ = "consumption_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    test_log_id: Optional[int] = Field(default=None, foreign_key="test_logs.id", index=True)
    cocktail_id: Optional[int] = Field(default=None, foreign_key="cocktails.id", index=True)
    antibody_id: int = Field(foreign_key="antibodies.id", index=True)
    stock_lot_id: int = Field(foreign_key="stock_lots.id")
    volume_consumed_ul: float
    timestamp: datetime = Field(default_factory=utc_now)

    test_log: Optional["TestLog"] = Relationship(back_populates="consumption_logs")
    cocktail: Optional["Cocktail"] = Relationship(back_populates="consumption_logs")
    antibody: Optional["Antibody"] = Relationship(back_populates="consumption_logs")
    stock_lot: Optional["StockLot"] = Relationship(back_populates="consumption_logs")


class Cocktail(SQLModel, table=True):
    """
    A pre-mixed antibody cocktail prepared from a panel for N tests.
    Full antibody volume is deducted from stock at mixing time.
    Tests are then logged against the cocktail without further stock deduction.
    """
    __tablename__ = "cocktails"

    id: Optional[int] = Field(default=None, primary_key=True)
    cocktail_code: Optional[str] = Field(default=None, unique=True, index=True, max_length=64)
    panel_id: int = Field(foreign_key="panels.id", index=True)
    prepared_by: int = Field(foreign_key="users.id")                 # login account used
    # The person who actually mixed it. Staff share a login on the bench PC, so
    # the login alone doesn't identify who prepared the cocktail.
    prepared_by_staff_id: Optional[int] = Field(default=None, foreign_key="staff.id", index=True)
    prepared_date: date
    total_tests: int
    remaining_tests: int
    # Tests promised to queued sample orders but not yet physically consumed.
    # available_to_reserve = remaining_tests - reserved_tests. Reserving a tube
    # increments this; moving a sample order to "in processing" decrements both
    # reserved_tests and remaining_tests (and writes a CocktailUsageLog).
    reserved_tests: int = Field(default=0)
    expiry_date: Optional[date] = None
    lot_notes: Optional[str] = Field(default=None, max_length=256)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)

    panel: Optional["Panel"] = Relationship(back_populates="cocktails")
    prepared_by_user: Optional["User"] = Relationship(back_populates="cocktails_prepared")
    consumption_logs: List["ConsumptionLog"] = Relationship(back_populates="cocktail")
    usage_logs: List["CocktailUsageLog"] = Relationship(back_populates="cocktail")


class CocktailUsageLog(SQLModel, table=True):
    """
    Records tests run using a pre-mixed cocktail.
    Decrements cocktail.remaining_tests only - no stock deduction.
    """
    __tablename__ = "cocktail_usage_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    cocktail_id: int = Field(foreign_key="cocktails.id", index=True)
    # Set when the test was consumed by a worklist tube, so a mis-tap on the
    # processing station can be reversed exactly.
    sample_order_tube_id: Optional[int] = Field(default=None, foreign_key="sample_order_tubes.id", index=True)
    test_date: date
    count: int
    entered_by: int = Field(foreign_key="users.id")
    notes: Optional[str] = Field(default=None, max_length=512)
    created_at: datetime = Field(default_factory=utc_now)

    cocktail: Optional["Cocktail"] = Relationship(back_populates="usage_logs")
    entered_by_user: Optional["User"] = Relationship(back_populates="cocktail_usage_logs")


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    antibody_id: int = Field(foreign_key="antibodies.id", index=True)
    quantity_vials: int
    volume_per_vial_ul: float
    order_date: date
    expected_delivery_date: Optional[date] = None
    status: str = Field(default="pending")
    po_number: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=512)
    created_by: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utc_now)

    antibody: Optional["Antibody"] = Relationship(back_populates="orders")
    created_by_user: Optional["User"] = Relationship(back_populates="orders_created")


class AlertRule(SQLModel, table=True):
    __tablename__ = "alert_rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    antibody_id: int = Field(foreign_key="antibodies.id", unique=True)
    lead_time_days: int = Field(default=35)
    safety_stock_ul: float = Field(default=0.0)
    alert_threshold_days: int = Field(default=42)

    antibody: Optional["Antibody"] = Relationship(back_populates="alert_rules")


class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: Optional[int] = Field(default=None, primary_key=True)
    antibody_id: int = Field(foreign_key="antibodies.id", index=True)
    alert_type: str = Field(max_length=32)
    message: str = Field(max_length=512)
    days_remaining: Optional[float] = None
    triggered_at: datetime = Field(default_factory=utc_now)
    acknowledged_by: Optional[int] = Field(default=None, foreign_key="users.id")
    acknowledged_at: Optional[datetime] = None

    antibody: Optional["Antibody"] = Relationship(back_populates="alerts")
    acknowledged_by_user: Optional["User"] = Relationship(back_populates="alerts_acknowledged")


# ---------------------------------------------------------------------------
# Verification Log — tracks system estimate vs measured at each verification
# ---------------------------------------------------------------------------

class VerificationLog(SQLModel, table=True):
    """
    Created whenever a stock lot is physically verified.
    Stores the system estimate before correction so accuracy can be reported.
    """
    __tablename__ = "verification_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    stock_lot_id: int = Field(foreign_key="stock_lots.id", index=True)
    antibody_id: int = Field(foreign_key="antibodies.id", index=True)
    verified_by: int = Field(foreign_key="users.id")
    verification_date: date
    system_estimate_ul: float       # current_volume_ul before correction
    measured_volume_ul: float       # what the tech actually measured
    delta_ul: float                 # measured - estimate (negative = overestimate)
    delta_pct: Optional[float]      # delta / estimate * 100
    # Measurement method metadata — important for agreement analysis. The
    # physical measurement is itself an estimate; recording how it was made
    # lets the reference uncertainty be reported honestly in validation.
    measurement_method: str = Field(default="pipette")   # "pipette" | "gravimetric"
    pipette_increment_ul: Optional[float] = Field(default=None)  # resolution floor of the measurement
    verification_cycle: Optional[str] = Field(default=None, max_length=64)  # e.g. prep batch / cycle label
    created_at: datetime = Field(default_factory=utc_now)



# ---------------------------------------------------------------------------
# Lab Settings — key/value store for admin-configurable lab identity
# ---------------------------------------------------------------------------

class LabSetting(SQLModel, table=True):
    __tablename__ = "lab_settings"

    key: str = Field(primary_key=True, max_length=64)
    value: Optional[str] = Field(default=None, max_length=512)
    updated_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Global Alert Defaults — system-wide thresholds (overridden per-antibody)
# ---------------------------------------------------------------------------

class GlobalAlertDefault(SQLModel, table=True):
    __tablename__ = "global_alert_defaults"

    id: Optional[int] = Field(default=None, primary_key=True)
    lead_time_days: int = Field(default=35)
    alert_threshold_days: int = Field(default=42)
    safety_stock_ul: float = Field(default=0.0)
    updated_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Store Stock — whole unopened vials in the stockroom
# ---------------------------------------------------------------------------

class StoreStock(SQLModel, table=True):
    __tablename__ = "store_stock"

    id: Optional[int] = Field(default=None, primary_key=True)
    antibody_id: int = Field(foreign_key="antibodies.id", index=True)
    lot_no: str = Field(max_length=64)
    vendor: Optional[str] = Field(default=None, max_length=128)
    catalog_no: Optional[str] = Field(default=None, max_length=64)
    quantity: int = Field(default=1)           # vials remaining in store
    volume_per_vial_ul: float = Field(default=500.0)  # µl per vial (for forecast)
    received_date: date
    expiry_date: Optional[date] = Field(default=None)
    shipment_id: Optional[str] = Field(default=None, max_length=64, index=True)
    notes: Optional[str] = Field(default=None, max_length=256)
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Staff — master list of people referenced on sample orders.
# Decoupled from `users` (login accounts): a requesting pathologist is not a
# system login, and the processing technologist may differ from whoever keys
# in the order. Admin-maintained under Lab Settings.
# ---------------------------------------------------------------------------

class Staff(SQLModel, table=True):
    __tablename__ = "staff"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, max_length=128)
    role: str = Field(default="technologist", index=True)  # "pathologist" | "technologist"
    initials: Optional[str] = Field(default=None, max_length=16)  # short label for dense tables
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utc_now)

    orders_requested: List["SampleOrder"] = Relationship(
        back_populates="requesting_pathologist",
        sa_relationship_kwargs={"foreign_keys": "[SampleOrder.requesting_pathologist_id]"},
    )
    orders_processed: List["SampleOrder"] = Relationship(
        back_populates="processing_technologist",
        sa_relationship_kwargs={"foreign_keys": "[SampleOrder.processing_technologist_id]"},
    )


# ---------------------------------------------------------------------------
# Sample Order — a lab sample (one accession / lab ID) with one or more tubes
# requested by a pathologist. Replaces the staff Google-sheet worklist.
#
# Status lifecycle:
#   in_queue -> in_processing -> completed   (+ cancelled)
#   - in_queue:      created; tubes reserve tests from matching cocktails
#   - in_processing: cocktail physically added; reserved tests are consumed
#                    (CocktailUsageLog written, cocktail.remaining_tests -1/tube)
#   - completed:     tubes acquired on the cytometer; timestamp only
#
# TAT timestamps are stamped at each transition for turnaround analysis.
# NOTE: distinct from `orders` (Order), which tracks vendor PURCHASE orders.
# ---------------------------------------------------------------------------

class SampleOrder(SQLModel, table=True):
    __tablename__ = "sample_orders"

    id: Optional[int] = Field(default=None, primary_key=True)
    lab_id: str = Field(index=True, max_length=64)  # accession / barcode value
    requesting_pathologist_id: Optional[int] = Field(default=None, foreign_key="staff.id", index=True)
    processing_technologist_id: Optional[int] = Field(default=None, foreign_key="staff.id", index=True)
    status: str = Field(default="in_queue", index=True)  # in_queue|in_processing|completed|cancelled
    priority: str = Field(default="routine")             # routine | urgent
    notes: Optional[str] = Field(default=None, max_length=512)
    # Sample-quality remark from the bench (clots, fibrin, degeneration, low count…).
    # Editable at any status — problems are often seen during acquisition.
    sample_comment: Optional[str] = Field(default=None, max_length=512)
    sample_comment_updated_at: Optional[datetime] = None
    sample_comment_updated_by: Optional[int] = Field(default=None, foreign_key="users.id")
    # The person behind the comment (shared bench login): from the staff list.
    sample_comment_staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    # Tap-to-toggle quality flags (bench tablet / worklist): comma-separated codes
    # from services/sample_flags.SAMPLE_FLAGS, e.g. "fibrin,low_volume".
    sample_flags: Optional[str] = Field(default=None, max_length=128)
    sample_flags_updated_at: Optional[datetime] = None
    sample_flags_staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")

    # TAT timestamps
    ordered_at: datetime = Field(default_factory=utc_now, index=True)  # request time (editable)
    processing_started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    created_by: int = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=utc_now)

    requesting_pathologist: Optional["Staff"] = Relationship(
        back_populates="orders_requested",
        sa_relationship_kwargs={"foreign_keys": "[SampleOrder.requesting_pathologist_id]"},
    )
    processing_technologist: Optional["Staff"] = Relationship(
        back_populates="orders_processed",
        sa_relationship_kwargs={"foreign_keys": "[SampleOrder.processing_technologist_id]"},
    )
    tubes: List["SampleOrderTube"] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SampleOrderTube(SQLModel, table=True):
    """
    One requested tube on a sample order = one panel = one cocktail test.
    Reservation is tracked per tube against a specific cocktail.
    """
    __tablename__ = "sample_order_tubes"

    id: Optional[int] = Field(default=None, primary_key=True)
    sample_order_id: int = Field(foreign_key="sample_orders.id", index=True)
    panel_id: int = Field(foreign_key="panels.id", index=True)
    reserved_cocktail_id: Optional[int] = Field(default=None, foreign_key="cocktails.id", index=True)
    # awaiting_cocktail = no cocktail had a free test at reserve time
    # reserved          = a cocktail test is held for this tube
    # consumed          = cocktail physically added (order moved to in_processing)
    status: str = Field(default="awaiting_cocktail")
    created_at: datetime = Field(default_factory=utc_now)

    order: Optional["SampleOrder"] = Relationship(back_populates="tubes")


# ---------------------------------------------------------------------------
# Shipment-to-shipment verification (regulatory QC)
#
# Raised automatically when an antibody is received under a shipment ID that
# differs from the shipment of its previous stock. One record per
# (antibody, shipment). Must be closed within VERIFICATION_WINDOW_HOURS with
# evidence for BOTH the previous and the new shipment attached.
#
# Status: open -> closed. Outcome on close: acceptable | not_acceptable.
# A closed record is immutable (attachments can no longer be removed).
# ---------------------------------------------------------------------------

class ShipmentVerification(SQLModel, table=True):
    __tablename__ = "shipment_verifications"

    id: Optional[int] = Field(default=None, primary_key=True)
    antibody_id: int = Field(foreign_key="antibodies.id", index=True)
    shipment_id: str = Field(max_length=64, index=True)            # the NEW shipment
    new_lot_no: Optional[str] = Field(default=None, max_length=64)
    previous_shipment_id: Optional[str] = Field(default=None, max_length=64)  # None = legacy stock with no shipment ID
    previous_lot_no: Optional[str] = Field(default=None, max_length=64)
    lot_changed: bool = Field(default=False)                       # new lot as well as new shipment

    status: str = Field(default="open", index=True)                # open | closed
    triggered_at: datetime = Field(default_factory=utc_now)
    due_at: datetime
    triggered_by: Optional[int] = Field(default=None, foreign_key="users.id")

    outcome: Optional[str] = Field(default=None, max_length=32)    # acceptable | not_acceptable
    comments: Optional[str] = Field(default=None, max_length=1024)
    closed_by: Optional[int] = Field(default=None, foreign_key="users.id")
    closed_by_staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")  # person who signed off
    closed_at: Optional[datetime] = None

    # Alerts raised for this record, so closing can acknowledge them
    alert_id: Optional[int] = Field(default=None, foreign_key="alerts.id")
    overdue_alert_id: Optional[int] = Field(default=None, foreign_key="alerts.id")

    attachments: List["ShipmentVerificationAttachment"] = Relationship(back_populates="verification")


class ShipmentVerificationAttachment(SQLModel, table=True):
    """Evidence file (image / document) for a shipment verification.
    role = previous | new — which shipment the evidence belongs to."""
    __tablename__ = "shipment_verification_attachments"

    id: Optional[int] = Field(default=None, primary_key=True)
    verification_id: int = Field(foreign_key="shipment_verifications.id", index=True)
    role: str = Field(max_length=16)                    # previous | new
    original_filename: str = Field(max_length=255)
    stored_filename: str = Field(max_length=255)        # relative to the uploads dir
    content_type: Optional[str] = Field(default=None, max_length=128)
    size_bytes: int
    sha256: str = Field(max_length=64)                  # integrity check for audit
    uploaded_by: int = Field(foreign_key="users.id")
    uploaded_at: datetime = Field(default_factory=utc_now)

    verification: Optional["ShipmentVerification"] = Relationship(back_populates="attachments")


# ---------------------------------------------------------------------------
# Processing steps (bench station / tablet)
#
# PanelProcessStep is the TEMPLATE: the ordered steps for a panel, or the
# lab-wide default when panel_id is NULL. Step 1 always means "cocktail added"
# — completing it consumes the tube's reserved cocktail test.
#
# SampleOrderTubeStep is the per-tube COPY, made when the tube is ordered, so
# editing a template never changes samples already in progress.
# ---------------------------------------------------------------------------

class PanelProcessStep(SQLModel, table=True):
    __tablename__ = "panel_process_steps"

    id: Optional[int] = Field(default=None, primary_key=True)
    panel_id: Optional[int] = Field(default=None, foreign_key="panels.id", index=True)  # NULL = lab default
    seq: int
    name: str = Field(max_length=64)
    # Minimum minutes after the PREVIOUS step before this one is due (e.g. an
    # incubation). None = no timer. Ignored on step 1.
    wait_minutes: Optional[int] = None


class SampleOrderTubeStep(SQLModel, table=True):
    __tablename__ = "sample_order_tube_steps"

    id: Optional[int] = Field(default=None, primary_key=True)
    tube_id: int = Field(foreign_key="sample_order_tubes.id", index=True)
    seq: int
    name: str = Field(max_length=64)
    wait_minutes: Optional[int] = None                 # frozen from the template
    completed_at: Optional[datetime] = None
    completed_early_seconds: Optional[int] = None      # tapped this many seconds before its timer ran out
    completed_by_staff_id: Optional[int] = Field(default=None, foreign_key="staff.id")
    completed_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
