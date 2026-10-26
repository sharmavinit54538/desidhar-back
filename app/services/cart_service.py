import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.product import Product


async def get_or_create_cart(session: AsyncSession, user_id: uuid.UUID) -> Cart:
    cart = (await session.execute(select(Cart).where(Cart.user_id == user_id))).scalar_one_or_none()
    if not cart:
        cart = Cart(user_id=user_id)
        session.add(cart)
        await session.flush()
    return cart


async def get_cart_view(session: AsyncSession, user_id: uuid.UUID) -> dict:
    cart = await get_or_create_cart(session, user_id)
    items_out = []
    subtotal = 0
    for item in cart.items:
        p = item.product
        line = p.price_paise * item.quantity
        subtotal += line
        warning = f"Only {p.stock_qty} left in stock" if p.stock_qty < item.quantity else None
        items_out.append({
            "id": item.id, "product_id": p.id, "name": p.name, "slug": p.slug, "unit": p.unit.value,
            "pack_size": p.pack_size, "unit_price_paise": p.price_paise, "unit_mrp_paise": p.mrp_paise,
            "quantity": item.quantity, "line_total_paise": line, "stock_qty": p.stock_qty,
            "is_active": p.is_active, "stock_warning": warning,
        })
    return {"id": cart.id, "items": items_out, "subtotal_paise": subtotal, "item_count": sum(i["quantity"] for i in items_out)}


async def update_cart_item(session: AsyncSession, user_id: uuid.UUID, prod_id: uuid.UUID, qty: int) -> tuple[bool, str | None]:
    cart = await get_or_create_cart(session, user_id)
    p = (await session.execute(select(Product).where(Product.id == prod_id))).scalar_one_or_none()
    if not p:
        return False, "Product not found"
    if qty == 0:
        await session.execute(delete(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == prod_id))
        await session.flush()
        return True, None
    if not p.is_active:
        return False, "Product is currently inactive"
    if qty > p.stock_qty:
        return False, f"Requested quantity ({qty}) exceeds available stock ({p.stock_qty})"
    if qty > p.max_qty_per_order:
        return False, f"Maximum allowed quantity per order is {p.max_qty_per_order}"

    item = (await session.execute(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == prod_id))).scalar_one_or_none()
    if item:
        item.quantity = qty
    else:
        session.add(CartItem(cart_id=cart.id, product_id=prod_id, quantity=qty))
    await session.flush()
    return True, None


async def clear_cart(session: AsyncSession, user_id: uuid.UUID) -> None:
    cart = await get_or_create_cart(session, user_id)
    await session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    await session.flush()


async def validate_cart_items(
    session: AsyncSession,
    items: list,
) -> dict:
    validated_items: list[dict] = []
    top_issues: list[str] = []

    for item in items:
        item_issues: list[str] = []
        prod_id_str = str(getattr(item, "product_id", "") or "")
        var_id_val = getattr(item, "variant_id", None)
        var_id_str = str(var_id_val) if var_id_val is not None else None
        qty = int(getattr(item, "quantity", 1))

        try:
            prod_uuid = uuid.UUID(prod_id_str)
        except (ValueError, TypeError, AttributeError):
            prod_uuid = None

        if prod_uuid is None:
            issue_msg = "Invalid product ID format"
            validated_items.append({
                "product_id": prod_id_str,
                "variant_id": var_id_str,
                "quantity": qty,
                "price": 0.0,
                "unit_price": 0.0,
                "line_total": 0.0,
                "available_stock": 0,
                "is_valid": False,
                "available": False,
                "issues": [issue_msg],
                "message": issue_msg,
                "name": None,
                "variant_label": None,
            })
            top_issues.append(f"Product {prod_id_str or 'unknown'}: {issue_msg}")
            continue

        product = (await session.execute(select(Product).where(Product.id == prod_uuid))).scalar_one_or_none()

        if not product:
            issue_msg = "Product does not exist"
            validated_items.append({
                "product_id": prod_id_str,
                "variant_id": var_id_str,
                "quantity": qty,
                "price": 0.0,
                "unit_price": 0.0,
                "line_total": 0.0,
                "available_stock": 0,
                "is_valid": False,
                "available": False,
                "issues": [issue_msg],
                "message": issue_msg,
                "name": None,
                "variant_label": None,
            })
            top_issues.append(f"Product {prod_id_str}: {issue_msg}")
            continue

        if not product.is_active:
            item_issues.append("Product is currently unavailable")

        if product.stock_qty <= 0:
            item_issues.append("Product is out of stock")
        elif qty > product.stock_qty:
            item_issues.append(f"Only {product.stock_qty} units available in stock")

        if product.max_qty_per_order and qty > product.max_qty_per_order:
            item_issues.append(f"Maximum {product.max_qty_per_order} units allowed per order")

        if qty <= 0:
            item_issues.append("Quantity must be greater than 0")

        unit_str = product.unit.value if hasattr(product.unit, "value") else str(product.unit)
        pack_label = f"{product.pack_size} {unit_str}".strip()
        price_rupees = round(product.price_paise / 100.0, 2)
        is_valid = len(item_issues) == 0
        line_total = round(price_rupees * qty, 2) if is_valid else 0.0

        for iss in item_issues:
            top_issues.append(f"{product.name}: {iss}")

        validated_items.append({
            "product_id": str(product.id),
            "variant_id": var_id_str,
            "quantity": qty,
            "price": price_rupees,
            "unit_price": price_rupees,
            "line_total": line_total,
            "available_stock": product.stock_qty,
            "is_valid": is_valid,
            "available": is_valid,
            "issues": item_issues,
            "message": item_issues[0] if item_issues else None,
            "name": product.name,
            "variant_label": pack_label,
        })

    all_valid = all(i["is_valid"] for i in validated_items) if validated_items else True
    subtotal = round(sum(i["line_total"] for i in validated_items if i["is_valid"]), 2)

    return {
        "valid": all_valid,
        "items": validated_items,
        "issues": top_issues,
        "subtotal": subtotal,
    }

