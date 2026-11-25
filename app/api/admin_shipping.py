import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.models.shipping_rule import ShippingRule
from app.models.user import User
from app.schemas.shipping_rule import ShippingRuleIn, ShippingRuleOut

router = APIRouter(prefix="/admin/shipping/rules", tags=["admin-shipping"])


@router.get("", response_model=list[ShippingRuleOut])
async def list_rules(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    return list((await db.execute(select(ShippingRule).order_by(ShippingRule.pincode, ShippingRule.city, ShippingRule.state))).scalars().all())


@router.post("", response_model=ShippingRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(data: ShippingRuleIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rule = ShippingRule(**data.model_dump())
    db.add(rule)
    await db.flush()
    return rule


@router.put("/{rule_id}", response_model=ShippingRuleOut)
async def replace_rule(rule_id: uuid.UUID, data: ShippingRuleIn, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rule = await db.get(ShippingRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Shipping rule not found")
    for key, value in data.model_dump().items():
        setattr(rule, key, value)
    await db.flush()
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rule = await db.get(ShippingRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Shipping rule not found")
    await db.delete(rule)
