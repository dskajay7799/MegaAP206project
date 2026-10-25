"""Cart: server-side lines, authoritative pricing, stock validation, guest→account merge.

The browser only ever sends (product_id, variant_id, quantity). Prices, availability and totals are always recomputed here
from the current catalogue, so a tampered client cannot change what it pays."""
from sqlalchemy import select

from .. import money, store
from ..http import cfg
from ..models import Cart, CartItem, Product, Variant, utcnow


class CartError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def get_cart(s, user=None, guest_hash: str | None = None, create: bool = False) -> Cart | None:
    q = select(Cart).where(Cart.user_id == user.id) if user else select(Cart).where(Cart.guest_hash == guest_hash)
    cart = s.scalar(q)
    if cart is None and create:
        cart = Cart(user_id=user.id) if user else Cart(guest_hash=guest_hash)
        s.add(cart)
        s.flush()
    return cart


def _max_for(row: Product, variant: Variant | None) -> int | None:
    """Tracked stock for the chosen variant/product, or None when stock isn't tracked."""
    if variant is not None:
        return variant.stock_qty
    return row.stock_qty


def _resolve(s, product_id: str, variant_id) -> tuple[Product, Variant | None]:
    row = s.get(Product, product_id)
    if row is None or not row.is_active:
        raise CartError(404, "product_unavailable", "That product is no longer available.")
    variants = store.active_variants(row)
    variant = None
    if variants:
        if variant_id in (None, ""):
            raise CartError(400, "variant_required", "Choose a size or colour first.")
        variant = next((v for v in variants if v.id == int(variant_id)), None) if str(variant_id).isdigit() else None
        if variant is None:
            raise CartError(400, "invalid_variant", "That option isn't available for this product.")
    elif variant_id not in (None, ""):
        raise CartError(400, "invalid_variant", "This product has no options to choose.")
    if row.price_paise is None:
        raise CartError(409, "no_price", "This product has no listed price, so it can't be bought.")
    return row, variant


def _clamp_check(row: Product, variant: Variant | None, qty: int):
    cap = cfg("MAX_QTY_PER_LINE")
    if qty < 1:
        raise CartError(400, "invalid_quantity", "Quantity must be at least 1.")
    status, _ = store.stock_info(row)
    tracked = _max_for(row, variant)
    if tracked is None and status != "in_stock":
        raise CartError(409, "out_of_stock", "This product is out of stock.")
    if tracked is not None and tracked <= 0:
        raise CartError(409, "out_of_stock", "This option is out of stock.", available=0)
    if qty > cap:
        raise CartError(409, "max_quantity", f"You can buy up to {cap} of one item at a time.", available=cap)
    if tracked is not None and qty > tracked:
        raise CartError(409, "insufficient_stock", f"Only {tracked} available.", available=tracked)


def add_item(s, cart: Cart, product_id: str, variant_id, quantity: int) -> CartItem:
    row, variant = _resolve(s, product_id, variant_id)
    key = str(variant.id) if variant else ""
    line = next((i for i in cart.items if i.product_id == product_id and i.variant_key == key), None)
    new_qty = (line.quantity if line else 0) + quantity
    _clamp_check(row, variant, new_qty)
    if line:
        line.quantity = new_qty
    else:
        line = CartItem(cart_id=cart.id, product_id=product_id, variant_id=variant.id if variant else None, variant_key=key, quantity=new_qty)
        cart.items.append(line)
    cart.updated_at = utcnow()
    s.flush()
    return line


def update_item(s, cart: Cart, item_id: int, quantity=None, variant_id=None) -> CartItem:
    line = next((i for i in cart.items if i.id == item_id), None)
    if line is None:
        raise CartError(404, "not_found", "That item isn't in your cart.")
    row = s.get(Product, line.product_id)
    vid = line.variant_id if variant_id is None else variant_id
    qty = line.quantity if quantity is None else quantity
    row, variant = _resolve(s, line.product_id, vid)
    _clamp_check(row, variant, qty)
    new_key = str(variant.id) if variant else ""
    other = next((i for i in cart.items if i is not line and i.product_id == line.product_id and i.variant_key == new_key), None)
    if other:                                              # switching to a variant already in the cart merges the lines
        merged = other.quantity + qty
        _clamp_check(row, variant, merged)
        other.quantity = merged
        cart.items.remove(line)
        s.delete(line)
        line = other
    else:
        line.quantity, line.variant_id, line.variant_key = qty, (variant.id if variant else None), new_key
    cart.updated_at = utcnow()
    s.flush()
    return line


def remove_item(s, cart: Cart, item_id: int):
    line = next((i for i in cart.items if i.id == item_id), None)
    if line is None:
        raise CartError(404, "not_found", "That item isn't in your cart.")
    cart.items.remove(line)
    s.delete(line)
    s.flush()


def shipping_for(subtotal_paise: int, settings: dict | None = None) -> int:
    """Policy: free above the threshold, otherwise a flat fee. `settings` lets CLI/seed code run outside a request."""
    get = (lambda k: settings[k]) if settings is not None else cfg
    if subtotal_paise <= 0:
        return 0
    return 0 if subtotal_paise > get("FREE_SHIPPING_ABOVE_RUPEES") * 100 else get("SHIPPING_FEE_RUPEES") * 100


def price_cart(s, cart: Cart | None) -> dict:
    lines, subtotal, issues = [], 0, []
    for it in (cart.items if cart else []):
        row = s.get(Product, it.product_id)
        variant = s.get(Variant, it.variant_id) if it.variant_id else None
        if row is None or not row.is_active:
            continue
        unit = store.unit_price_paise(row, variant)
        tracked = _max_for(row, variant)
        status, msg, max_qty = "ok", "", min(cfg("MAX_QTY_PER_LINE"), tracked) if tracked is not None else cfg("MAX_QTY_PER_LINE")
        if unit is None:
            status, msg = "unavailable", "No listed price."
        elif variant is not None and not variant.is_active:
            status, msg = "unavailable", "This option is no longer offered."
        elif tracked is not None and tracked <= 0 or (tracked is None and store.stock_info(row)[0] != "in_stock"):
            status, msg = "out_of_stock", "Out of stock. Remove it or pick another option."
        elif tracked is not None and it.quantity > tracked:
            status, msg = "insufficient", f"Only {tracked} available. Reduce the quantity."
        total = (unit or 0) * it.quantity
        if status == "ok":
            subtotal += total
        else:
            issues.append({"item_id": it.id, "product_id": row.id, "message": msg})
        lines.append({
            "id": it.id, "product_id": row.id, "variant_id": variant.id if variant else None, "title": row.title, "brand": row.brand,
            "image": (row.images or [None])[0], "category": row.category.name if row.category else "", "variant_label": store.variant_label(variant),
            "options": variant.options if variant else {}, "has_variants": bool(store.active_variants(row)),
            "unit_price": money.to_rupees(unit), "unit_price_text": money.text(unit), "quantity": it.quantity,
            "line_total": money.to_rupees(total), "line_total_text": money.text(total), "status": status, "message": msg, "max_qty": max_qty,
        })
    ship = shipping_for(subtotal)
    free_above = cfg("FREE_SHIPPING_ABOVE_RUPEES") * 100
    return {
        "lines": lines, "items_count": sum(l["quantity"] for l in lines), "subtotal": money.to_rupees(subtotal), "subtotal_text": money.text(subtotal),
        "shipping": money.to_rupees(ship), "shipping_text": "Free" if subtotal and ship == 0 else money.text(ship),
        "total": money.to_rupees(subtotal + ship), "total_text": money.text(subtotal + ship), "subtotal_paise": subtotal, "shipping_paise": ship,
        "total_paise": subtotal + ship, "free_shipping_remaining_text": money.text(free_above - subtotal + 100) if 0 < subtotal <= free_above else None,
        "free_shipping_threshold_text": money.text(free_above), "issues": issues, "can_checkout": bool(lines) and not issues and subtotal > 0,
        "currency": "INR", "checkout_enabled": bool(cfg("CHECKOUT_ENABLED")), "note": "Totals are calculated on the server from current catalogue prices. Prices include taxes (demo store).",
    }


def merge_guest_into_user(s, user, guest_hash: str):
    guest = get_cart(s, None, guest_hash)
    if guest is None or not guest.items:
        if guest is not None:
            s.delete(guest)
        return 0
    mine = get_cart(s, user, create=True)
    moved = 0
    for it in list(guest.items):
        try:
            add_item(s, mine, it.product_id, it.variant_id, it.quantity)
            moved += 1
        except CartError:
            try:   # as many as stock allows
                row, variant = _resolve(s, it.product_id, it.variant_id)
                tracked = _max_for(row, variant)
                have = next((i.quantity for i in mine.items if i.product_id == it.product_id and i.variant_key == (str(variant.id) if variant else "")), 0)
                room = (tracked if tracked is not None else cfg("MAX_QTY_PER_LINE")) - have
                if room > 0:
                    add_item(s, mine, it.product_id, it.variant_id, min(room, it.quantity))
                    moved += 1
            except CartError:
                pass        # item no longer purchasable: dropped, the shopper sees the cart as it truly is
    s.delete(guest)
    s.flush()
    return moved
