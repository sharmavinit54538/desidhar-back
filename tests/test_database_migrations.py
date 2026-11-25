import os
import pytest
from sqlalchemy import create_engine, inspect, text
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

from app.core.config import get_settings
from app.core.db import Base
import app.models

_ALEMBIC_INI_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini")


def test_single_alembic_head():
    """Verify that Alembic has a single head and no branching issues."""
    alembic_cfg = Config(_ALEMBIC_INI_PATH)
    alembic_cfg.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic"),
    )
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 Alembic head, got {len(heads)}: {heads}"
    assert heads[0] == script.get_current_head()


def test_database_is_at_head():
    """Verify that the current database revision matches the migration head."""
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL.replace("+asyncpg", "+psycopg2"))
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()
        alembic_cfg = Config(_ALEMBIC_INI_PATH)
        alembic_cfg.set_main_option(
            "script_location",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic"),
        )
        expected_head = ScriptDirectory.from_config(alembic_cfg).get_current_head()
        assert current_rev == expected_head, f"Database is at {current_rev}, expected {expected_head}"


def test_schema_matches_orm_models():
    """Verify that all ORM tables and columns exist in the PostgreSQL database with correct nullability."""
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL.replace("+asyncpg", "+psycopg2"))
    insp = inspect(engine)

    db_tables = set(insp.get_table_names())
    orm_tables = set(Base.metadata.tables.keys())

    # All ORM tables must exist in the database
    missing_tables = orm_tables - db_tables
    assert not missing_tables, f"Missing tables in database: {missing_tables}"

    # Verify column existence and nullability
    for table_name in orm_tables:
        orm_cols = {c.name: c for c in Base.metadata.tables[table_name].columns}
        db_cols = {c["name"]: c for c in insp.get_columns(table_name)}

        missing_cols = set(orm_cols.keys()) - set(db_cols.keys())
        assert not missing_cols, f"Table '{table_name}' is missing columns: {missing_cols}"

        for col_name, orm_c in orm_cols.items():
            db_c = db_cols[col_name]
            assert orm_c.nullable == db_c["nullable"], (
                f"Column '{table_name}.{col_name}' nullable mismatch: ORM={orm_c.nullable}, DB={db_c['nullable']}"
            )

    orders = {c["name"]: c for c in insp.get_columns("orders")}
    from sqlalchemy import Date, DateTime, String
    for name in ("estimated_delivery_date", "estimated_delivery_end_date", "revised_delivery_date"):
        assert isinstance(orders[name]["type"], Date), f"orders.{name} must be DATE, got {orders[name]['type']}"
    for name in ("placed_at", "confirmed_at", "packed_at", "shipped_at", "out_for_delivery_at", "delivered_at"):
        col_type = orders[name]["type"]
        assert isinstance(col_type, DateTime) and col_type.timezone, f"orders.{name} must be TIMESTAMPTZ, got {col_type}"
    for name in ("delay_reason", "delivery_speed"):
        assert isinstance(orders[name]["type"], String), f"orders.{name} must be VARCHAR, got {orders[name]['type']}"


def test_product_check_constraints_exist():
    """Verify that the check constraints on products table exist in PostgreSQL."""
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL.replace("+asyncpg", "+psycopg2"))
    insp = inspect(engine)
    db_checks = {c["name"] for c in insp.get_check_constraints("products")}

    expected_checks = {
        "ck_cost_price_paise_non_negative",
        "ck_gst_rate_percent_range",
        "ck_max_qty_per_order_positive",
    }
    missing_checks = expected_checks - db_checks
    assert not missing_checks, f"Missing check constraints on products: {missing_checks}"
