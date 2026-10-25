import re
import csv
import io
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.pincode import Pincode
from app.schemas.pincode_bulk import BulkUpsertResult, BulkRowError

PIN_RE = re.compile(r"^[1-9][0-9]{5}$")


def _parse_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes", "t")


def _validate_row(raw: dict) -> tuple[dict | None, str | None]:
    p = str(raw.get("pincode", "")).strip()
    if not PIN_RE.match(p):
        return None, "Invalid pincode format (must be 6 digits starting 1-9)"
    area = str(raw.get("area_name", "")).strip()
    city = str(raw.get("city", "")).strip()
    state = str(raw.get("state", "")).strip()
    if not (area and city and state):
        return None, "area_name, city, and state are required"
    try:
        fee = int(raw.get("delivery_fee_paise", 0) or 0)
        min_ord = int(raw.get("min_order_paise", 0) or 0)
        free_above = raw.get("free_delivery_above_paise")
        free_above = int(free_above) if free_above not in (None, "") else None
        eta = raw.get("eta_hours")
        eta = int(eta) if eta not in (None, "") else None
        if fee < 0 or min_ord < 0 or (free_above is not None and free_above < 0) or (eta is not None and eta < 0):
            return None, "Money and hours must be non-negative"
    except (ValueError, TypeError):
        return None, "Numeric field contains invalid integer"
    return {
        "pincode": p, "area_name": area, "city": city, "state": state,
        "is_serviceable": _parse_bool(raw.get("is_serviceable", True)),
        "delivery_fee_paise": fee, "min_order_paise": min_ord,
        "free_delivery_above_paise": free_above,
        "cod_available": _parse_bool(raw.get("cod_available", False)),
        "eta_hours": eta,
    }, None


async def process_bulk_upsert(session: AsyncSession, raw_rows: list[dict]) -> BulkUpsertResult:
    created, updated, invalid, errors = 0, 0, 0, []
    for idx, raw in enumerate(raw_rows, start=1):
        clean, err = _validate_row(raw)
        p = str(raw.get("pincode", "")).strip() or None
        if err or not clean:
            invalid += 1
            errors.append(BulkRowError(row=idx, pincode=p, reason=err or "Invalid row"))
            continue
        existing = (await session.execute(select(Pincode).where(Pincode.pincode == clean["pincode"]))).scalar_one_or_none()
        if existing:
            for k, v in clean.items():
                setattr(existing, k, v)
            updated += 1
        else:
            session.add(Pincode(**clean))
            created += 1
    await session.flush()
    return BulkUpsertResult(created=created, updated=updated, invalid=invalid, errors=errors)


async def process_csv_import(session: AsyncSession, content: bytes) -> BulkUpsertResult:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(r) for r in reader]
    return await process_bulk_upsert(session, rows[:500])

