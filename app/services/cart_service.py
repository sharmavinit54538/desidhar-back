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

