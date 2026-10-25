"""Cart, checkout quote and orders. Totals are always recomputed on the server; the browser never supplies a price."""
import re

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from .. import security, store
from ..http import assistant, body, cfg, db, error, pagination
from ..models import Address, Order, WishlistItem
from ..security import checkout_gate, current_user, login_required, rate_limited
from ..services import cart as cart_svc
from ..services import orders as orders_svc
from .catalog import card_list

bp = Blueprint("shop", __name__)


def _checkout_off():
    """Demo guard: no checkout, no payment flow, while CHECKOUT_ENABLED is off (the default)."""
    if not cfg("CHECKOUT_ENABLED"):
        return error(403, "checkout_disabled", "Checkout is disabled in this demo. Nothing is purchased and no payment details are requested.")
    return None


def _cart(create=False):
    u = current_user()
    return cart_svc.get_cart(db(), u, None if u else security.guest_key(), create=create)


def _priced():
    security.ensure_cookie()
    return cart_svc.price_cart(db(), _cart())


def _cart_error(e: cart_svc.CartError):
    db().rollback()
    return error(e.status, e.code, e.message, **e.extra)


@bp.get("/api/cart")
def cart_get():
    return jsonify(_priced())


@bp.post("/api/cart/items")
@rate_limited("write", "WRITE_RATE_LIMIT_PER_MIN")
def cart_add():
    b = body()
    try:
        qty = int(b.get("quantity", 1))
    except (TypeError, ValueError):
        return error(400, "invalid_quantity", "Quantity must be a whole number.")
    security.ensure_cookie()
    try:
        cart_svc.add_item(db(), _cart(create=True), str(b.get("product_id", "")), b.get("variant_id"), qty)
        db().commit()
    except cart_svc.CartError as e:
        return _cart_error(e)
    return jsonify(cart_svc.price_cart(db(), _cart())), 201


@bp.patch("/api/cart/items/<int:item_id>")
def cart_update(item_id):
    b = body()
    try:
        qty = int(b["quantity"]) if "quantity" in b else None
    except (TypeError, ValueError):
        return error(400, "invalid_quantity", "Quantity must be a whole number.")
    cart = _cart()
    if cart is None:
        return error(404, "not_found", "That item isn't in your cart.")
    try:
        cart_svc.update_item(db(), cart, item_id, qty, b.get("variant_id"))
        db().commit()
    except cart_svc.CartError as e:
        return _cart_error(e)
    return jsonify(cart_svc.price_cart(db(), _cart()))


@bp.delete("/api/cart/items/<int:item_id>")
def cart_remove(item_id):
    cart = _cart()
    if cart is None:
        return error(404, "not_found", "That item isn't in your cart.")
    try:
        cart_svc.remove_item(db(), cart, item_id)
        db().commit()
    except cart_svc.CartError as e:
        return _cart_error(e)
    return jsonify(cart_svc.price_cart(db(), _cart()))


@bp.delete("/api/cart")
def cart_clear():
    cart = _cart()
    if cart is not None:
        for i in list(cart.items):
            db().delete(i)
        cart.items.clear()
        db().commit()
    return jsonify(cart_svc.price_cart(db(), _cart()))


@bp.post("/api/cart/items/<int:item_id>/save-for-later")
@login_required
def save_for_later(item_id):
    u, s, cart = current_user(), db(), _cart()
    line = next((i for i in (cart.items if cart else []) if i.id == item_id), None)
    if line is None:
        return error(404, "not_found", "That item isn't in your cart.")
    if not s.scalar(select(WishlistItem.id).where(WishlistItem.user_id == u.id, WishlistItem.product_id == line.product_id)):
        s.add(WishlistItem(user_id=u.id, product_id=line.product_id))
    cart_svc.remove_item(s, cart, item_id)
    s.commit()
    return jsonify(cart_svc.price_cart(s, _cart()))


@bp.get("/api/cart/suggestions")
def cart_suggestions():
    a, cart = assistant(), _cart()
    ids = {i.product_id for i in (cart.items if cart else [])}
    seeds = [a.by_id[i] for i in ids if i in a.by_id]
    if not seeds:
        return jsonify({"items": [], "note": ""})
    tags = {t for p in seeds for t in p.use_cases}
    subs = {p.subcategory for p in seeds}
    out = []
    for p in a.products:
        if p.id in ids or p.stock != "in_stock" or p.subcategory in subs:
            continue
        shared = sorted(tags & set(p.use_cases))
        if shared:
            out.append((len(shared), p, shared))
    out.sort(key=lambda x: (-x[0], x[1].price or 0, x[1].id))
    cards = {c["id"]: c for c in card_list([p for _, p, _ in out[:4]])}
    return jsonify({"items": [{"product": cards[p.id], "reason": "Also listed for " + ", ".join(sh[:2])} for _, p, sh in out[:4] if p.id in cards],
                    "note": "Suggested because they share a listed use with items in your cart. This is not based on what other shoppers bought."})


@bp.get("/api/checkout/quote")
@checkout_gate
def quote():
    if (off := _checkout_off()):
        return off
    priced = _priced()
    return jsonify({**priced, "payment_methods": [{"id": k, "label": v[1].split(".")[0], "note": v[1]} for k, v in orders_svc.PAYMENT_METHODS.items()],
                    "shipping_policy": "Standard shipping, 3 to 6 business days. Free above ₹%d, otherwise ₹%d." % (cfg("FREE_SHIPPING_ABOVE_RUPEES"), cfg("SHIPPING_FEE_RUPEES")),
                    "demo_notice": "Demo checkout: no payment is taken and no card details are collected."})


@bp.post("/api/orders")
@checkout_gate
@login_required
@rate_limited("write", "WRITE_RATE_LIMIT_PER_MIN")
def place_order():
    if (off := _checkout_off()):
        return off
    b, u, s = body(), current_user(), db()
    key = request.headers.get("Idempotency-Key", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{8,80}", key):
        return error(400, "idempotency_key_required", "Missing or invalid Idempotency-Key header.")
    if b.get("address_id") not in (None, ""):
        a = s.scalar(select(Address).where(Address.id == int(b["address_id"]), Address.user_id == u.id)) if str(b["address_id"]).isdigit() else None
        if a is None:
            return error(404, "not_found", "That saved address wasn't found.")
        addr = {"full_name": a.full_name, "phone": a.phone, "line1": a.line1, "line2": a.line2, "city": a.city, "state": a.state, "pincode": a.pincode}
    else:
        addr = b.get("address") if isinstance(b.get("address"), dict) else {}
    cart = _cart()
    if cart is None:
        return error(409, "empty_cart", "Your cart is empty.")
    try:
        order, replayed = orders_svc.place_order(s, u, cart, addr, str(b.get("payment_method", "")), key, u.email)
    except cart_svc.CartError as e:
        return _cart_error(e)
    if not replayed and b.get("save_address") and not b.get("address_id"):
        clean, errs = orders_svc.validate_address(addr)
        if not errs and (s.scalar(select(func.count()).select_from(Address).where(Address.user_id == u.id)) or 0) < 10:
            s.add(Address(user_id=u.id, label="Saved at checkout", is_default=False, **clean))
            s.commit()
    resp = jsonify({"order": orders_svc.serialize(order), "replayed": replayed, "message": "Demo order placed. No payment was taken."})
    resp.status_code = 200 if replayed else 201
    return resp


@bp.get("/api/orders")
@login_required
def orders_list():
    page, size = pagination(10, 50)
    u, s = current_user(), db()
    total = s.scalar(select(func.count()).select_from(Order).where(Order.user_id == u.id)) or 0
    rows = s.scalars(select(Order).where(Order.user_id == u.id).order_by(Order.created_at.desc(), Order.id.desc()).offset((page - 1) * size).limit(size)).all()
    return jsonify({"items": [orders_svc.serialize(o) for o in rows], "total": total, "page": page, "pages": max(1, -(-total // size))})


def _mine(number: str) -> Order | None:
    return db().scalar(select(Order).where(Order.order_number == number, Order.user_id == current_user().id))


@bp.get("/api/orders/<number>")
@login_required
def order_get(number):
    o = _mine(number)
    return jsonify(orders_svc.serialize(o)) if o else error(404, "not_found", "Order not found.")


@bp.post("/api/orders/<number>/cancel")
@login_required
def order_cancel(number):
    o = _mine(number)
    if o is None:
        return error(404, "not_found", "Order not found.")
    if o.status != "placed":
        return error(409, "invalid_transition", "Only orders that are still “Order placed” can be cancelled online.")
    try:
        orders_svc.set_status(db(), o, "cancelled", "customer", "Cancelled by customer")
        db().commit()
    except cart_svc.CartError as e:
        return _cart_error(e)
    return jsonify(orders_svc.serialize(o))
