"""Cart, pricing, checkout, orders, inventory integrity, wishlist, addresses, dashboards and per-user isolation."""
import threading

from sqlalchemy import select

from backend.app.models import Order, Product, Variant
from tests.conftest import ADDR, idem
from tests.helpers import Api, make_app


def vid(api, pid, **opts):
    d = api.get(f"/api/products/{pid}").get_json()
    return next(v["id"] for v in d["variants"] if all(v["options"].get(k) == x for k, x in opts.items()))


def add(api, pid, qty=1, **opts):
    body = {"product_id": pid, "quantity": qty}
    if opts is not None and opts != {}:
        body["variant_id"] = vid(api, pid, **opts)
    return api.post("/api/cart/items", body)


def buy(api, **extra):
    return api.post("/api/orders", {"address": ADDR, "payment_method": "demo_card", **extra}, headers=idem())


# ------------------------------------------------------------ cart
def test_guest_cart_persists_and_validates(api):
    assert api.post("/api/cart/items", {"product_id": "VRT-1001", "quantity": 1}).get_json()["error"]["code"] == "variant_required"
    assert api.post("/api/cart/items", {"product_id": "VRT-1001", "variant_id": 999999, "quantity": 1}).get_json()["error"]["code"] == "invalid_variant"
    assert api.post("/api/cart/items", {"product_id": "VRT-1009", "variant_id": 1, "quantity": 1}).get_json()["error"]["code"] == "invalid_variant"
    for q in (0, -1, "abc"):
        assert api.post("/api/cart/items", {"product_id": "VRT-1009", "quantity": q}).status_code == 400
    assert api.post("/api/cart/items", {"product_id": "VRT-1009", "quantity": 11}).get_json()["error"]["code"] == "max_quantity"
    assert api.post("/api/cart/items", {"product_id": "NOPE", "quantity": 1}).status_code == 404
    assert add(api, "VRT-1009", 2).status_code == 201
    cart = api.get("/api/cart").get_json()                     # same cookie -> same cart after a "refresh"
    assert cart["items_count"] == 2 and cart["lines"][0]["product_id"] == "VRT-1009"


def test_unavailable_products_cannot_be_added(api):
    assert api.post("/api/cart/items", {"product_id": "VRT-6001", "quantity": 1}).get_json()["error"]["code"] == "out_of_stock"
    assert api.post("/api/cart/items", {"product_id": "VRT-1005", "quantity": 1}).get_json()["error"]["code"] == "out_of_stock"
    d = api.get("/api/products/VRT-3003").get_json()           # every size sold out
    assert api.post("/api/cart/items", {"product_id": "VRT-3003", "variant_id": d["variants"][0]["id"], "quantity": 1}).get_json()["error"]["code"] == "out_of_stock"


def test_totals_and_shipping_policy_are_computed_on_the_server(api):
    add(api, "VRT-7002", 5)                                    # 5 x 199 = 995  -> at or below 999: flat fee
    c = api.get("/api/cart").get_json()
    assert (c["subtotal"], c["shipping"], c["total"]) == (995, 59, 1054) and c["free_shipping_remaining_text"]
    add(api, "VRT-7002", 1)                                    # 1194 > 999: free shipping
    c = api.get("/api/cart").get_json()
    assert (c["subtotal"], c["shipping"], c["total"], c["shipping_text"]) == (1194, 0, 1194, "Free")
    assert c["lines"][0]["line_total"] == 1194 and c["lines"][0]["unit_price"] == 199


def test_client_supplied_prices_are_ignored(shopper):
    r = shopper.post("/api/cart/items", {"product_id": "VRT-7002", "quantity": 1, "price": 1, "unit_price": 1, "total": 1})
    assert r.status_code == 201 and r.get_json()["total"] == 258        # 199 + 59 shipping
    o = shopper.post("/api/orders", {"address": ADDR, "payment_method": "demo_card", "total": 1, "subtotal": 1, "shipping": 0, "items": [{"price": 1}]}, headers=idem()).get_json()["order"]
    assert o["total"] == 258 and o["items"][0]["unit_price_text"] == "₹199"


def test_update_change_variant_remove_clear(api):
    add(api, "VRT-2003", 1, colour="Black", size="M")
    line = api.get("/api/cart").get_json()["lines"][0]
    r = api.patch(f"/api/cart/items/{line['id']}", {"quantity": 3}).get_json()
    assert r["lines"][0]["quantity"] == 3
    other = vid(api, "VRT-2003", colour="Black", size="L")
    r = api.patch(f"/api/cart/items/{line['id']}", {"variant_id": other}).get_json()
    assert r["lines"][0]["variant_label"] == "Black / L" and len(r["lines"]) == 1
    add(api, "VRT-2003", 1, colour="Black", size="M")                                   # two lines, then switch one to the other's variant -> merge
    lines = api.get("/api/cart").get_json()["lines"]
    assert len(lines) == 2
    merged = api.patch(f"/api/cart/items/{lines[1]['id']}", {"variant_id": other}).get_json()
    assert len(merged["lines"]) == 1 and merged["lines"][0]["quantity"] == 4
    assert api.delete(f"/api/cart/items/{merged['lines'][0]['id']}").get_json()["lines"] == []
    add(api, "VRT-1009", 1)
    assert api.delete("/api/cart").get_json()["items_count"] == 0
    assert api.delete("/api/cart/items/424242").status_code == 404


def test_stock_limits_are_enforced(api):
    d = api.get("/api/products/VRT-6002").get_json()                    # dumbbells: tracked stock 4
    assert add(api, "VRT-6002", 4).status_code == 201
    r = add(api, "VRT-6002", 1)
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "insufficient_stock" and r.get_json()["error"]["available"] == 4


def test_guest_cart_merges_into_account_on_login(demo_app):
    a = Api(demo_app)
    a.register("merge@example.com")
    add(a, "VRT-1009", 2)
    a.post("/api/auth/logout")
    assert a.get("/api/cart").get_json()["items_count"] == 0            # logged out: a different (guest) cart
    add(a, "VRT-1009", 1)
    add(a, "VRT-7002", 2)
    r = a.login("merge@example.com", "Sunrise-Lamp-42").get_json()
    cart = a.get("/api/cart").get_json()
    assert r["cart_merged"] == 2 and {l["product_id"]: l["quantity"] for l in cart["lines"]} == {"VRT-1009": 3, "VRT-7002": 2}


def test_cart_flags_items_that_become_unavailable_or_change_price(demo_app, admin, shopper):
    add(shopper, "VRT-5001", 1)
    admin.put("/api/admin/products/VRT-5001", {"price": 600})
    assert shopper.get("/api/cart").get_json()["lines"][0]["unit_price"] == 600      # repriced from the catalogue, not the stale add-time price
    admin.put("/api/admin/products/VRT-5001", {"stock_qty": 0})
    c = shopper.get("/api/cart").get_json()
    assert c["lines"][0]["status"] == "out_of_stock" and not c["can_checkout"] and c["subtotal"] == 0
    assert buy(shopper).get_json()["error"]["code"] == "cart_changed"
    admin.put("/api/admin/products/VRT-5001", {"price": 549, "stock_qty": 45})
    shopper.delete("/api/cart")


def test_cart_suggestions_are_honest(shopper):
    add(shopper, "VRT-8001", 1, colour="Black")
    s = shopper.get("/api/cart/suggestions").get_json()
    assert s["items"] and "not based on what other shoppers bought" in s["note"]
    assert all(i["product"]["id"] != "VRT-8001" and i["reason"].startswith("Also listed for") for i in s["items"])


# ------------------------------------------------------------ checkout / orders / inventory
def test_checkout_requires_login_valid_address_and_payment(api, shopper):
    add(api, "VRT-1009", 1)
    assert buy(api).status_code == 401
    add(shopper, "VRT-1009", 1)
    bad = shopper.post("/api/orders", {"address": {**ADDR, "phone": "123", "pincode": "12"}, "payment_method": "demo_card"}, headers=idem())
    assert bad.status_code == 422 and {"phone", "pincode"} <= set(bad.get_json()["error"]["fields"])
    assert shopper.post("/api/orders", {"address": ADDR, "payment_method": "bitcoin"}, headers=idem()).get_json()["error"]["code"] == "invalid_payment"
    assert shopper.post("/api/orders", {"address": ADDR, "payment_method": "demo_card"}).get_json()["error"]["code"] == "idempotency_key_required"
    assert shopper.get("/api/cart").get_json()["items_count"] == 1       # failed attempts never consume the cart


def test_order_is_created_with_demo_wording_snapshot_and_stock_decrement(demo_app, shopper):
    before = shopper.get("/api/products/VRT-1009").get_json()["stock_qty"]
    add(shopper, "VRT-1009", 2)
    add(shopper, "VRT-2003", 1, colour="White", size="S")
    vstock = lambda: next(v["stock_qty"] for v in shopper.get("/api/products/VRT-2003").get_json()["variants"] if v["options"] == {"colour": "White", "size": "S"})
    vbefore = vstock()
    r = buy(shopper)
    assert r.status_code == 201
    o = r.get_json()["order"]
    assert "No payment was taken" in r.get_json()["message"] and o["payment_status"] == "demo_simulated" and "no card details" in o["payment_note"].lower()
    assert o["status"] == "placed" and o["subtotal"] == 2 * 1099 + 699 and o["shipping_text"] == "Free" and len(o["items"]) == 2
    assert shopper.get("/api/products/VRT-1009").get_json()["stock_qty"] == before - 2 and vstock() == vbefore - 1
    assert shopper.get("/api/cart").get_json()["items_count"] == 0
    assert shopper.get(f"/api/orders/{o['order_number']}").get_json()["items"][0]["title"] == "FastPort 33W USB-C Charger"
    # the order keeps its snapshot even if the catalogue later changes
    from backend.app.models import Product as P
    with demo_app.extensions["verity"].db.scope() as s:
        row = s.get(P, "VRT-1009")
        row.price_paise = 1
    assert shopper.get(f"/api/orders/{o['order_number']}").get_json()["items"][0]["unit_price_text"] == "₹1,099"
    with demo_app.extensions["verity"].db.scope() as s:
        s.get(P, "VRT-1009").price_paise = 109900


def test_duplicate_submission_creates_one_order(shopper):
    add(shopper, "VRT-1009", 1)
    h = idem()
    first = shopper.post("/api/orders", {"address": ADDR, "payment_method": "cod"}, headers=h)
    again = shopper.post("/api/orders", {"address": ADDR, "payment_method": "cod"}, headers=h)
    assert first.status_code == 201 and again.status_code == 200 and again.get_json()["replayed"] is True
    assert first.get_json()["order"]["order_number"] == again.get_json()["order"]["order_number"]
    assert shopper.get("/api/orders").get_json()["total"] == 1
    third = shopper.post("/api/orders", {"address": ADDR, "payment_method": "cod"}, headers=idem())     # a different key with an empty cart
    assert third.status_code == 409 and third.get_json()["error"]["code"] == "empty_cart"


def test_last_unit_race_never_oversells():
    app = make_app()
    with app.extensions["verity"].db.scope() as s:
        s.get(Product, "VRT-6002").stock_qty = 1
    users = []
    for i in range(4):
        a = Api(app)
        a.register(f"racer{i}@example.com")
        assert add(a, "VRT-6002", 1).status_code == 201
        users.append(a)
    codes, barrier = [], threading.Barrier(len(users))

    def go(a):
        barrier.wait()
        codes.append(buy(a).status_code)
    threads = [threading.Thread(target=go, args=(a,)) for a in users]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(codes) == [201, 409, 409, 409], codes
    with app.extensions["verity"].db.scope() as s:
        assert s.get(Product, "VRT-6002").stock_qty == 0
        assert len(s.scalars(select(Order)).all()) == 1


def test_customer_cancel_restocks_and_late_cancel_is_refused(demo_app, shopper, admin):
    before = shopper.get("/api/products/VRT-1009").get_json()["stock_qty"]
    add(shopper, "VRT-1009", 2)
    n = buy(shopper).get_json()["order"]["order_number"]
    assert shopper.get("/api/products/VRT-1009").get_json()["stock_qty"] == before - 2
    r = shopper.post(f"/api/orders/{n}/cancel")
    assert r.status_code == 200 and r.get_json()["status"] == "cancelled" and shopper.get("/api/products/VRT-1009").get_json()["stock_qty"] == before
    assert shopper.post(f"/api/orders/{n}/cancel").status_code == 409
    add(shopper, "VRT-1009", 1)
    n2 = buy(shopper).get_json()["order"]["order_number"]
    assert admin.patch(f"/api/admin/orders/{n2}/status", {"status": "processing"}).status_code == 200
    assert shopper.post(f"/api/orders/{n2}/cancel").status_code == 409


def test_orders_are_private_to_their_owner(demo_app, shopper):
    add(shopper, "VRT-1009", 1)
    n = buy(shopper).get_json()["order"]["order_number"]
    other = Api(demo_app)
    other.register("snoop@example.com")
    assert other.get(f"/api/orders/{n}").status_code == 404 and other.post(f"/api/orders/{n}/cancel").status_code == 404
    assert other.get("/api/orders").get_json()["total"] == 0 and shopper.get("/api/orders").get_json()["total"] == 1
    assert other.get("/api/account/dashboard").get_json()["orders_count"] == 0


def test_cannot_check_out_with_someone_elses_address(demo_app, shopper):
    other = Api(demo_app)
    other.register("owner@example.com")
    aid = other.post("/api/account/addresses", ADDR).get_json()["id"]
    add(shopper, "VRT-1009", 1)
    assert shopper.post("/api/orders", {"address_id": aid, "payment_method": "cod"}, headers=idem()).status_code == 404
    assert shopper.put(f"/api/account/addresses/{aid}", ADDR).status_code == 404 and shopper.delete(f"/api/account/addresses/{aid}").status_code == 404


# ------------------------------------------------------------ account data
def test_wishlist_persists_across_sessions_and_is_private(demo_app, shopper):
    assert shopper.post("/api/account/wishlist", {"product_id": "NOPE"}).status_code == 404
    assert shopper.post("/api/account/wishlist", {"product_id": "VRT-1001"}).status_code == 201
    shopper.post("/api/account/wishlist", {"product_id": "VRT-1001"})                 # idempotent
    shopper.post("/api/account/wishlist", {"product_id": "VRT-2003"})
    shopper.post("/api/auth/logout")
    shopper.login(shopper.email, "Sunrise-Lamp-42")
    me = shopper.get("/api/auth/me").get_json()
    assert sorted(me["wishlist_ids"]) == ["VRT-1001", "VRT-2003"] and len(shopper.get("/api/account/wishlist").get_json()["items"]) == 2
    other = Api(demo_app)
    other.register("nowish@example.com")
    assert other.get("/api/account/wishlist").get_json()["items"] == []
    assert shopper.delete("/api/account/wishlist/VRT-1001").status_code == 204 and shopper.get("/api/account/wishlist").get_json()["ids"] == ["VRT-2003"]


def test_addresses_crud_and_default(shopper):
    assert shopper.post("/api/account/addresses", {**ADDR, "pincode": "x"}).status_code == 422
    a1 = shopper.post("/api/account/addresses", {**ADDR, "label": "Home"}).get_json()
    a2 = shopper.post("/api/account/addresses", {**ADDR, "label": "Work", "is_default": True}).get_json()
    items = shopper.get("/api/account/addresses").get_json()["items"]
    assert a1["is_default"] is True and [i["label"] for i in items if i["is_default"]] == ["Work"]
    assert shopper.put(f"/api/account/addresses/{a1['id']}", {**ADDR, "line1": "New line 1"}).get_json()["line1"] == "New line 1"
    add(shopper, "VRT-1009", 1)
    assert shopper.post("/api/orders", {"address_id": a2["id"], "payment_method": "cod"}, headers=idem()).status_code == 201
    assert shopper.delete(f"/api/account/addresses/{a1['id']}").status_code == 204


def test_new_customer_sees_no_fabricated_history(shopper):
    d = shopper.get("/api/account/dashboard").get_json()
    assert d["orders_count"] == 0 and d["recent_orders"] == [] and d["spending"]["order_count"] == 0
    assert d["spending"]["by_month"] == [] and d["spending"]["by_category"] == [] and d["spending"]["total"] == 0 and d["wishlist_count"] == 0
    r = shopper.get("/api/recommendations").get_json()
    assert r["items"] == [] and r["enough_data"] is False and "preferences" in r["reason"].lower()


def test_customer_spending_is_computed_from_their_orders(shopper):
    add(shopper, "VRT-1009", 1)                                   # Electronics 1099 (free shipping above 999)
    buy(shopper)
    add(shopper, "VRT-2003", 2, colour="Black", size="M")         # Fashion 2 x 699 = 1398
    buy(shopper)
    add(shopper, "VRT-7002", 1)
    n = buy(shopper).get_json()["order"]["order_number"]          # Books & Stationery 199 + 59 shipping
    shopper.post(f"/api/orders/{n}/cancel")                        # cancelled orders are not spending
    sp = shopper.get("/api/account/dashboard").get_json()["spending"]
    assert sp["order_count"] == 2 and sp["total"] == 1099 + 1398
    assert {c["label"]: c["value"] for c in sp["by_category"]} == {"Electronics": 1099, "Fashion": 1398}
    assert sum(m["value"] for m in sp["by_month"]) == 1099 + 1398


def test_preferences_drive_recommendations_and_can_be_deleted(shopper):
    assert shopper.put("/api/account/preferences", {"budget_min": 5000, "budget_max": 100}).status_code == 422
    r = shopper.put("/api/account/preferences", {"categories": ["Footwear", "Not A Category"], "requirements": ["running", "fakeneed"], "budget_max": 3000})
    assert r.get_json()["categories"] == ["Footwear"] and r.get_json()["requirements"] == ["running"]      # unknown values are dropped, not stored
    rec = shopper.get("/api/recommendations").get_json()
    assert rec["enough_data"] and rec["items"] and all(i["product"]["price"] <= 3000 and i["reasons"] for i in rec["items"])
    assert rec["items"][0]["product"]["category"] == "Footwear"
    assert shopper.delete("/api/account/preferences").status_code == 204
    assert shopper.get("/api/account/preferences").get_json()["saved"] is False and shopper.get("/api/recommendations").get_json()["items"] == []


def test_saved_comparisons_chats_and_privacy_controls(demo_app, shopper):
    assert shopper.post("/api/account/comparisons", {"product_ids": ["VRT-1001"]}).status_code == 400
    c = shopper.post("/api/account/comparisons", {"product_ids": ["VRT-1001", "VRT-1002"], "name": "Headphones"}).get_json()
    ch = shopper.post("/api/account/chats", {"messages": [{"role": "user", "text": "headphones under 3000"}, {"role": "assistant", "text": "Pulse Lite [VRT-1002]"}], "product_ids": ["VRT-1002", "NOPE"]}).get_json()
    assert ch["product_ids"] == ["VRT-1002"] and ch["kind"] == "shortlist" and ch["title"].startswith("headphones")
    other = Api(demo_app)
    other.register("curious@example.com")
    assert other.get("/api/account/comparisons").get_json()["items"] == [] and other.get("/api/account/chats").get_json()["items"] == []
    assert other.delete(f"/api/account/comparisons/{c['id']}").status_code == 404 and other.delete(f"/api/account/chats/{ch['id']}").status_code == 404
    assert shopper.delete("/api/account/chats").status_code == 204 and shopper.get("/api/account/chats").get_json()["items"] == []
    assert shopper.delete(f"/api/account/comparisons/{c['id']}").status_code == 204


def test_price_watch_states_its_limits(shopper):
    assert shopper.put("/api/account/watches/VRT-1001", {"target_price": 0}).status_code == 422
    assert shopper.put("/api/account/watches/VRT-1001", {"target_price": 5500}).status_code == 200
    shopper.put("/api/account/watches/VRT-2003", {"target_price": 500})
    w = shopper.get("/api/account/watches").get_json()
    assert "does not send emails" in w["note"] and {i["product"]["id"]: i["reached"] for i in w["items"]} == {"VRT-1001": True, "VRT-2003": False}


def test_data_export_contains_only_own_data(demo_app, shopper):
    add(shopper, "VRT-1009", 1)
    buy(shopper)
    d = shopper.get("/api/account/export").get_json()
    assert d["profile"]["email"] == shopper.email and len(d["orders"]) == 1 and "password" not in str(d).lower()
