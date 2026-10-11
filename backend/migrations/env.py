import os, sys
from pathlib import Path
from logging.config import fileConfig
from alembic import context

# Make migrations/_guards.py importable from the version scripts
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.models import (  # noqa
    User, Fluorochrome, Antibody, AntibodyAlternative,
    Panel, PanelComponent, StockLot, TestLog, ConsumptionLog,
    Cocktail, CocktailUsageLog, Order, AlertRule, Alert,
    VerificationLog, LabSetting, GlobalAlertDefault,
    StoreStock, Staff, SampleOrder, SampleOrderTube,
    ShipmentVerification, ShipmentVerificationAttachment,
    PanelProcessStep, SampleOrderTubeStep,
)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

def get_url():
    # Prefer environment variable; fall back to absolute path next to project root
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "flowjai.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"

def run_migrations_offline():
    context.configure(url=get_url(), target_metadata=target_metadata,
        literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()

def _fk_violations(connection):
    return connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()


def run_migrations_online():
    cfg = config.get_section(config.config_ini_section)
    cfg["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # SQLite can only change a column's constraints by rebuilding the table:
            # copy to a temp table, DROP the original, rename. The app turns
            # foreign_keys ON for every connection, and with it ON, dropping a table
            # that other rows reference fails ("FOREIGN KEY constraint failed" on
            # DROP TABLE cocktails, migration 008). Turn it off for this connection
            # only - it must happen outside a transaction - and verify below instead.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            if connection.exec_driver_sql("PRAGMA foreign_keys").scalar() != 0:
                raise RuntimeError("Could not disable foreign keys for the migration")
            # A rebuild interrupted part-way leaves its temp copy behind, which would
            # make the next attempt fail with "table ... already exists". The original
            # table is still intact at that point, so the leftover copy is safe to drop.
            leftovers = [r[0] for r in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '\\_alembic\\_tmp\\_%' ESCAPE '\\'")]
            for name in leftovers:
                connection.exec_driver_sql(f'DROP TABLE "{name}"')
            connection.commit()
            before = len(_fk_violations(connection))

        context.configure(connection=connection, target_metadata=target_metadata,
            render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()

        if sqlite:
            after = _fk_violations(connection)
            if len(after) > before:
                # The upgrade itself broke references - refuse rather than run on it.
                raise RuntimeError(
                    f"Upgrade left {len(after) - before} broken reference(s), e.g. {after[0]}")
            if after:
                print(f"[flowjai] Note: {len(after)} pre-existing broken reference(s) in the data "
                      f"(not caused by the upgrade), e.g. {after[0]}")
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
