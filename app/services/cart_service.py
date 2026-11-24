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


def _product_image_url(product) -> str | None:
    """Get the primary image URL for a product from its images relationship."""
    if product.images:
        return product.images[0].url
    return None


def _variant_label(product) -> str:
    """Generate a readable variant/pack label like '500 ml' or '1 kg'."""
    unit_str = product.unit.value if hasattr(product.unit, "value") else str(product.unit)
    pack = product.pack_size
    # Clean up trailing zeros for display: "1.00" -> "1", "0.50" -> "0.5"
    try:
        num = float(pack)
        pack_str = f"{num:g}"
    except (ValueError, TypeError):
        pack_str = str(pack)
    return f"{pack_str} {unit_str}"


async def get_cart_view(session: AsyncSession, user_id: uuid.UUID) -> dict:
    cart = await get_or_create_cart(session, user_id)
    items_out = []
    subtotal = 0
    total_mrp = 0
    for item in cart.items:
        p = item.product
        line = p.price_paise * item.quantity
        mrp_line = p.mrp_paise * item.quantity
        subtotal += line
        total_mrp += mrp_line
        item_discount = mrp_line - line
        discount_percent = round((1 - p.price_paise / p.mrp_paise) * 100, 1) if p.mrp_paise > 0 else 0.0

        warning = None
        if not p.is_active:
            warning = "This product is currently unavailable"
        elif p.stock_qty <= 0:
            warning = "Out of stock"
        elif p.stock_qty < item.quantity:
            warning = f"Only {p.stock_qty} left in stock"

        # Get category info
        cat_name = None
        cat_slug = None
        if p.category:
            cat_name = p.category.name
            cat_slug = p.category.slug

        # Get image URL
        image_url = _product_image_url(p)

        # Short description (first 140 chars)
        short_desc = None
        if p.description:
            short_desc = p.description[:140] if len(p.description) > 140 else p.description

        items_out.append({
            "id": item.id,
            "product_id": p.id,
            "name": p.name,
            "slug": p.slug,
            "unit": p.unit.value,
            "pack_size": p.pack_size,
            "unit_price_paise": p.price_paise,
            "unit_mrp_paise": p.mrp_paise,
            "quantity": item.quantity,
            "line_total_paise": line,
            "line_mrp_total_paise": mrp_line,
            "discount_paise": item_discount,
            "discount_percent": discount_percent,
            "stock_qty": p.stock_qty,
            "max_qty_per_order": p.max_qty_per_order,
            "is_active": p.is_active,
            "stock_warning": warning,
            "image_url": image_url,
            "category_name": cat_name,
            "category_slug": cat_slug,
            "description": short_desc,
            "is_veg": p.is_veg,
            "gst_rate_percent": float(p.gst_rate_percent),
            "variant_label": _variant_label(p),
        })

    product_discount = total_mrp - subtotal
    item_count = sum(i["quantity"] for i in items_out)

    summary = {
        "item_count": item_count,
        "total_mrp_paise": total_mrp,
        "product_discount_paise": product_discount,
        "coupon_discount_paise": 0,
        "coupon_code": None,
        "subtotal_paise": subtotal,
        "delivery_charge_paise": None,  # Calculated at checkout with address
        "delivery_charge_note": "Calculated at checkout",
        "packaging_charge_paise": 0,
        "tax_paise": 0,  # Prices are tax-inclusive
        "total_savings_paise": product_discount,
        "total_paise": subtotal,
    }

    return {
        "id": cart.id,
        "items": items_out,
        "subtotal_paise": subtotal,
        "item_count": item_count,
        "summary": summary,
    }


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


async def remove_cart_item(session: AsyncSession, user_id: uuid.UUID, prod_id: uuid.UUID) -> tuple[bool, str | None]:
    """Remove a specific item from cart by product_id."""
    cart = await get_or_create_cart(session, user_id)
    result = await session.execute(
        delete(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == prod_id)
    )
    await session.flush()
    if result.rowcount == 0:
        return False, "Item not found in cart"
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
            "mrp": round(product.mrp_paise / 100.0, 2),
            "line_total": line_total,
            "available_stock": product.stock_qty,
            "is_valid": is_valid,
            "available": is_valid,
            "issues": item_issues,
            "message": item_issues[0] if item_issues else None,
            "name": product.name,
            "variant_label": pack_label,
            "image_url": _product_image_url(product),
            "slug": product.slug,
            "discount_percent": round((1 - product.price_paise / product.mrp_paise) * 100, 1) if product.mrp_paise > 0 else 0.0,
        })

    all_valid = all(i["is_valid"] for i in validated_items) if validated_items else True
    subtotal = round(sum(i["line_total"] for i in validated_items if i["is_valid"]), 2)

    return {
        "valid": all_valid,
        "items": validated_items,
        "issues": top_issues,
        "subtotal": subtotal,
    }

