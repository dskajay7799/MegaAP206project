"""Demo checkout: validation, atomic stock decrement, idempotency, order lifecycle.

No payment is processed. payment_status is 'demo_simulated' or 'pay_on_delivery' and the UI says so explicitly."""
import re
import secrets

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .. import money, store
from ..models import Order, OrderEvent, OrderItem, Product, Variant, utcnow
from . import cart as cart_svc

STATUSES = ["placed", "processing", "shipped", "delivered", "cancelled"]
STATUS_LABEL = {"placed": "Order placed", "processing": "Processing", "shipped": "Shipped", "delivered": "Delivered", "cancelled": "Cancelled"}
TRANSITIONS = {"placed": {"processing", "cancelled"}, "processing": {"shipped", "cancelled"}, "shipped": {"delivered"}, "delivered": set(), "cancelled": set()}
PAYMENT_METHODS = {
    "demo_card": ("demo_simulated", "Demo payment (simulated). No card details are collected and no money moves."),
    "cod": ("pay_on_delivery", "Pay on delivery (demo). Nothing is charged."),
}
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def validate_address(a: dict) -> tuple[dict, dict]:
    """Returns (clean, errors)."""
    g = lambda k: re.sub(r"\s+", " ", str(a.get(k) or "")).strip()
    clean = {"full_name": g("full_name")[:120], "phone": re.sub(r"[\s\-]", "", g("phone")), "line1": g("line1")[:200], "line2": g("line2")[:200],
             "city": g("city")[:80], "state": g("state")[:80], "pincode": re.sub(r"\s", "", g("pincode"))}
    clean["phone"] = re.sub(r"^(\+91|91|0)(?=\d{10}$)", "", clean["phone"])
    err = {}
    if len(clean["full_name"]) < 2:
        err["full_name"] = "Enter the recipient's full name."
    if not re.fullmatch(r"[6-9]\d{9}", clean["phone"]):
        err["phone"] = "Enter a 10-digit Indian mobile number."
    if len(clean["line1"]) < 5:
        err["line1"] = "Enter the street address."
    if len(clean["city"]) < 2:
        err["city"] = "Enter the city."
    if len(clean["state"]) < 2:
        err["state"] = "Enter the state."
    if not re.fullmatch(r"[1-9]\d{5}", clean["pincode"]):
        err["pincode"] = "Enter a 6-digit PIN code."
    return clean, err


def new_order_number(s) -> str:
    for _ in range(10):
        n = "VO-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))
        if not s.scalar(select(Order.id).where(Order.order_number == n)):
            return n
    raise RuntimeError("could not allocate an order number")


def _snapshot_items(s, priced: dict) -> list[OrderItem]:
    items = []
    for ln in priced["lines"]:
        row = s.get(Product, ln["product_id"])
        items.append(OrderItem(
            product_id=row.id, variant_id=ln["variant_id"], sku=(s.get(Variant, ln["variant_id"]).sku if ln["variant_id"] else row.sku), title=row.title,
            brand=row.brand, category=ln["category"], variant_label=ln["variant_label"], image=ln["image"] or "",
            unit_price_paise=round(ln["unit_price"] * 100), quantity=ln["quantity"], line_total_paise=round(ln["line_total"] * 100)))
    return items


def _decrement_stock(s, priced: dict):
    """Atomic conditional UPDATEs: succeeds only if enough stock remains, so concurrent buyers can never oversell."""
    wanted = sorted(((l["variant_id"] or 0, l["product_id"], l["quantity"]) for l in priced["lines"]))   # fixed order avoids deadlocks
    for vid, pid, qty in wanted:
        if vid:
            res = s.execute(update(Variant).where(Variant.id == vid, Variant.stock_qty >= qty).values(stock_qty=Variant.stock_qty - qty))
            if res.rowcount != 1:
                raise cart_svc.CartError(409, "out_of_stock", "Someone bought the last units while you were checking out. Review your cart.")
        else:
            row = s.get(Product, pid)
            if row.stock_qty is None:          # stock not tracked: in_stock status was already validated when pricing
                continue
            res = s.execute(update(Product).where(Product.id == pid, Product.stock_qty >= qty).values(stock_qty=Product.stock_qty - qty))
            if res.rowcount != 1:
                raise cart_svc.CartError(409, "out_of_stock", "Someone bought the last units while you were checking out. Review your cart.")


def place_order(s, user, cart, address: dict, payment_method: str, idem_key: str, contact_email: str, version_bump: bool = True):
    """Returns (order, replayed). Raises CartError for any condition the shopper can fix."""
    if idem_key:
        existing = s.scalar(select(Order).where(Order.user_id == user.id, Order.idempotency_key == idem_key))
        if existing:
            return existing, True
    if payment_method not in PAYMENT_METHODS:
        raise cart_svc.CartError(400, "invalid_payment", "Choose a payment option.")
    clean, errs = validate_address(address)
    if errs:
        raise cart_svc.CartError(422, "invalid_address", "Check the highlighted address fields.", fields=errs)
    priced = cart_svc.price_cart(s, cart)
    if not priced["lines"]:
        raise cart_svc.CartError(409, "empty_cart", "Your cart is empty.")
    if not priced["can_checkout"]:
        raise cart_svc.CartError(409, "cart_changed", "Some items in your cart changed. Review them before placing the order.", issues=priced["issues"])
    try:
        _decrement_stock(s, priced)
        pay_status, _ = PAYMENT_METHODS[payment_method]
        order = Order(
            order_number=new_order_number(s), user_id=user.id, status="placed", payment_method=payment_method, payment_status=pay_status,
            subtotal_paise=priced["subtotal_paise"], shipping_paise=priced["shipping_paise"], total_paise=priced["total_paise"],
            contact_email=contact_email, ship_name=clean["full_name"], ship_phone=clean["phone"], ship_line1=clean["line1"], ship_line2=clean["line2"],
            ship_city=clean["city"], ship_state=clean["state"], ship_pincode=clean["pincode"], idempotency_key=idem_key or None)
        order.items = _snapshot_items(s, priced)
        order.events = [OrderEvent(status="placed", note="Demo order placed. No payment was taken.", actor="customer")]
        s.add(order)
        for it in list(cart.items):
            s.delete(it)
        cart.items.clear()
        s.flush()
        s.commit()
        return order, False
    except IntegrityError:
        s.rollback()
        existing = s.scalar(select(Order).where(Order.user_id == user.id, Order.idempotency_key == idem_key)) if idem_key else None
        if existing:
            return existing, True
        raise
    except cart_svc.CartError:
        s.rollback()
        raise


def restock(s, order: Order):
    for it in order.items:
        if it.variant_id:
            s.execute(update(Variant).where(Variant.id == it.variant_id).values(stock_qty=Variant.stock_qty + it.quantity))
        elif it.product_id:
            row = s.get(Product, it.product_id)
            if row is not None and row.stock_qty is not None:
                s.execute(update(Product).where(Product.id == it.product_id).values(stock_qty=Product.stock_qty + it.quantity))


def set_status(s, order: Order, new: str, actor: str, note: str = ""):
    if new not in STATUSES:
        raise cart_svc.CartError(400, "invalid_status", "Unknown order status.")
    if new not in TRANSITIONS.get(order.status, set()):
        raise cart_svc.CartError(409, "invalid_transition", f"An order that is “{STATUS_LABEL[order.status].lower()}” can't move to “{STATUS_LABEL[new].lower()}”.")
    if new == "cancelled" and not order.is_demo:
        restock(s, order)
    order.status = new
    order.updated_at = utcnow()
    order.events.append(OrderEvent(status=new, note=note[:200], actor=actor))
    s.flush()


def serialize(o: Order, admin: bool = False) -> dict:
    d = {
        "order_number": o.order_number, "status": o.status, "status_label": STATUS_LABEL.get(o.status, o.status), "created_at": o.created_at.isoformat(),
        "payment_method": o.payment_method, "payment_status": o.payment_status,
        "payment_note": PAYMENT_METHODS.get(o.payment_method, ("", ""))[1],
        "subtotal": money.to_rupees(o.subtotal_paise), "subtotal_text": money.text(o.subtotal_paise),
        "shipping_text": "Free" if o.shipping_paise == 0 else money.text(o.shipping_paise),
        "total": money.to_rupees(o.total_paise), "total_text": money.text(o.total_paise), "currency": o.currency, "is_demo_seeded": o.is_demo,
        "items": [{"product_id": i.product_id, "title": i.title, "brand": i.brand, "variant_label": i.variant_label, "image": i.image or None, "category": i.category,
                   "quantity": i.quantity, "unit_price_text": money.text(i.unit_price_paise), "line_total_text": money.text(i.line_total_paise), "sku": i.sku} for i in o.items],
        "ship_to": {"name": o.ship_name, "phone": o.ship_phone, "line1": o.ship_line1, "line2": o.ship_line2, "city": o.ship_city, "state": o.ship_state, "pincode": o.ship_pincode},
        "events": [{"status": e.status, "label": STATUS_LABEL.get(e.status, e.status), "note": e.note, "at": e.at.isoformat(), "actor": e.actor} for e in o.events],
        "can_cancel": o.status == "placed", "next_statuses": sorted(TRANSITIONS.get(o.status, set()), key=STATUSES.index),
    }
    if admin:
        d.update({"contact_email": o.contact_email, "user_id": o.user_id})
    return d
