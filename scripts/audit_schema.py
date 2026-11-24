import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, inspect
from app.core.config import get_settings
from app.core.db import Base
import app.models

settings = get_settings()
db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2")
engine = create_engine(db_url)
insp = inspect(engine)

db_tables = set(insp.get_table_names())
orm_tables = set(Base.metadata.tables.keys())

print("=== TABLES IN DB ===")
print(sorted(db_tables))
print("\n=== TABLES IN ORM ===")
print(sorted(orm_tables))
print("\n=== MISSING TABLES IN DB ===")
print(sorted(orm_tables - db_tables))
print("\n=== EXTRA TABLES IN DB (excluding alembic_version) ===")
print(sorted(db_tables - orm_tables - {"alembic_version"}))

print("\n=== COLUMN LEVEL COMPARISON ===")
mismatches = 0
for table_name in sorted(orm_tables & db_tables):
    orm_cols = {c.name: c for c in Base.metadata.tables[table_name].columns}
    db_cols = {c["name"]: c for c in insp.get_columns(table_name)}
    
    missing_in_db = set(orm_cols.keys()) - set(db_cols.keys())
    missing_in_orm = set(db_cols.keys()) - set(orm_cols.keys())
    
    if missing_in_db or missing_in_orm:
        mismatches += 1
        print(f"\nTable '{table_name}':")
        if missing_in_db:
            print(f"  Missing in DB: {sorted(missing_in_db)}")
        if missing_in_orm:
            print(f"  Missing in ORM: {sorted(missing_in_orm)}")
            
    for col_name in sorted(set(orm_cols.keys()) & set(db_cols.keys())):
        orm_c = orm_cols[col_name]
        db_c = db_cols[col_name]
        # check nullable
        if orm_c.nullable != db_c["nullable"]:
            mismatches += 1
            print(f"  Column '{table_name}.{col_name}' nullable mismatch: ORM={orm_c.nullable}, DB={db_c['nullable']}")
        
        # check type str representation
        orm_type_str = str(orm_c.type)
        db_type_str = str(db_c["type"])
        # print if types look significantly different
        # print(f"    {col_name}: ORM={orm_type_str} | DB={db_type_str}")

print(f"\nTotal column mismatches found: {mismatches}")

print("\n=== CHECK CONSTRAINTS COMPARISON ===")
for table_name in sorted(orm_tables & db_tables):
    db_checks = insp.get_check_constraints(table_name)
    orm_checks = [c.name for c in Base.metadata.tables[table_name].constraints if c.__class__.__name__ == 'CheckConstraint']
    db_check_names = [c["name"] for c in db_checks if c["name"]]
    missing_checks = set(orm_checks) - set(db_check_names)
    if missing_checks:
        print(f"Table '{table_name}' missing Check Constraints in DB: {missing_checks}")

print("\n=== DATA TYPE AND NULLABLE CHECK ===")
for table_name, table in Base.metadata.tables.items():
    if table_name not in db_tables:
        continue
    db_cols = {c['name']: c for c in insp.get_columns(table_name)}
    for col in table.columns:
        if col.name not in db_cols:
            print(f"MISSING COLUMN in {table_name}: {col.name}")
            continue
        db_c = db_cols[col.name]
        if col.nullable != db_c['nullable']:
            print(f"NULLABLE MISMATCH in {table_name}.{col.name}: ORM={col.nullable}, DB={db_c['nullable']}")
        db_type = str(db_c['type']).upper()
        orm_type = str(col.type).upper()
        # compare base types if needed
        # print(f"{table_name}.{col.name}: ORM={orm_type} DB={db_type}")

print("\n=== FOREIGN KEY COMPARISON ===")
for table_name in sorted(orm_tables & db_tables):
    db_fks = insp.get_foreign_keys(table_name)
    orm_fk_cols = {c.name for c in Base.metadata.tables[table_name].columns if c.foreign_keys}
    db_fk_cols = {col for fk in db_fks for col in fk["constrained_columns"]}
    missing_fk = orm_fk_cols - db_fk_cols
    if missing_fk:
        print(f"Table '{table_name}' missing FK in DB for columns: {missing_fk}")

print("\n=== INDEX COMPARISON ===")
for table_name in sorted(orm_tables & db_tables):
    orm_indexes = {idx.name for idx in Base.metadata.tables[table_name].indexes if idx.name}
    db_indexes = {idx["name"] for idx in insp.get_indexes(table_name) if idx["name"]}
    missing_idx_in_db = orm_indexes - db_indexes
    if missing_idx_in_db:
        print(f"Table '{table_name}' missing indexes in DB: {missing_idx_in_db}")

print("\n=== AUDIT COMPLETE ===")
