"""Admin: server-side role enforcement, catalogue management that reaches the grounded assistant, order lifecycle, analytics from stored rows."""
import pytest
from sqlalchemy import select

from backend.app import bootstrap
from backend.app.models import Order, Product, User
from tests.conftest import ADDR, idem
from tests.helpers import Api, make_app
from tests.test_shop import add, buy

ADMIN_ROUTES = [("get", "/api/admin/summary"), ("get", "/api/admin/charts"), ("get", "/api/admin/products"), ("get", "/api/admin/products/VRT-1001"),
                ("post", "/api/admin/products"), ("put", "/api/admin/products/VRT-1001"), ("patch", "/api/admin/products/VRT-1001/inventory"),
                ("patch", "/api/admin/products/VRT-1001/price"), ("delete", "/api/admin/products/VRT-1001"), ("get", "/api/admin/categories"),
                ("post", "/api/admin/categories"), ("put", "/api/admin/categories/1"), ("delete", "/api/admin/categories/1"), ("get", "/api/admin/orders"),
                ("get", "/api/admin/orders/VO-X"), ("patch", "/api/admin/orders/VO-X/status"), ("get", "/api/admin/customers"), ("get", "/api/admin/health"), ("get", "/api/admin/ai")]


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_every_admin_route_enforces_role_on_the_server(demo_app, method, path):
    anon, cust = Api(demo_app), Api(demo_app)
    cust.register(f"cust-{abs(hash(path + method)) % 10**7}@example.com")
    call = lambda a: getattr(a, method)(path, {} if method != "get" and method != "delete" else None) if method in ("post", "put", "patch") else getattr(a, method)(path)
    assert call(anon).status_code == 401
    assert call(cust).status_code == 403


def test_no_default_admin_exists_and_weak_admin_passwords_are_refused():
    app = make_app()
    a = Api(app)
    for email in ("admin@verity.com", "admin@example.com", "admin@admin.com", "root@example.com"):
        for pw in ("admin", "admin123", "password", "Admin@123"):
            assert a.login(email, pw).status_code == 401
    db = app.extensions["verity"].db
    with db.scope() as s:
        assert s.scalar(select(User).where(User.role == "admin")) is None
    with pytest.raises(ValueError):
        bootstrap.ensure_admin(db, "boss@example.com", "admin123")
    with pytest.raises(ValueError):
        bootstrap.ensure_admin(db, "not-an-email", "Granite-Orbit-77")


def test_admin_created_from_environment_variables():
    app = make_app(ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD="Granite-Orbit-77")
    a = Api(app)
    r = a.login("boss@example.com", "Granite-Orbit-77")
    assert r.status_code == 200 and r.get_json()["user"]["role"] == "admin"
    weak = make_app(ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD="admin")              # ignored (logged), the app still starts
    assert Api(weak).login("boss@example.com", "admin").status_code == 401


def test_product_lifecycle_reaches_storefront_and_the_grounded_assistant(demo_app, admin, api):
    body = {"id": "TEST-9001", "title": "Zephyr Travel Pillow", "brand": "Testbrand", "category": "Bags", "subcategory": "Travel accessories", "price": 799,
            "stock_qty": 7, "description": "Memory-foam neck pillow.", "specs": {"weight_g": 310, "machine_washable": True}, "use_cases": ["travel"],
            "images": ["/assets/products/VRT-8001-1.svg"], "highlights": ["Memory foam"], "rating": 4.1}
    assert admin.post("/api/admin/products", {**body, "title": "x"}).status_code == 422
    assert admin.post("/api/admin/products", {**body, "price": "abc"}).status_code == 422
    assert admin.post("/api/admin/products", {**body, "images": ["javascript:alert(1)"]}).status_code == 422
    assert admin.post("/api/admin/products", {**body, "images": ["http://insecure.example/x.png"]}).status_code == 422
    assert admin.post("/api/admin/products", {**body, "images": ["data:image/svg+xml;base64,AAAA"]}).status_code == 422
    assert admin.post("/api/admin/products", {**body, "specs": {"Bad Key": 1}}).status_code == 422
    assert admin.post("/api/admin/products", body).status_code == 201
    assert admin.post("/api/admin/products", body).status_code == 422                       # duplicate id
    # visible in the storefront ...
    assert api.get("/api/products/TEST-9001").get_json()["price"] == 799
    # ... and the assistant answers from the NEW record, with citation
    chat = api.c.post("/api/chat", json={"message": "price of TEST-9001"}).get_json()
    assert "₹799" in chat["message"] and chat["citations"][0]["id"] == "TEST-9001" and chat["status"] == "answer"
    # price and stock edits change what the assistant states
    assert admin.patch("/api/admin/products/TEST-9001/price", {"price": 849}).status_code == 200
    assert "₹849" in api.c.post("/api/chat", json={"message": "price of TEST-9001"}).get_json()["message"]
    admin.patch("/api/admin/products/TEST-9001/inventory", {"stock_qty": 0})
    assert "out of stock" in api.c.post("/api/chat", json={"message": "is TEST-9001 in stock?"}).get_json()["message"]
    assert admin.patch("/api/admin/products/TEST-9001/inventory", {"stock_qty": -3}).status_code == 422
    # price history recorded the admin changes
    assert [p["price"] for p in api.get("/api/products/TEST-9001/price-history").get_json()["points"]] == [799, 849]
    # hiding removes it everywhere
    admin.put("/api/admin/products/TEST-9001", {"is_active": False})
    assert api.get("/api/products/TEST-9001").status_code == 404 and "TEST-9001" not in str(api.c.post("/api/chat", json={"message": "price of TEST-9001"}).get_json()["citations"])
    admin.put("/api/admin/products/TEST-9001", {"is_active": True})
    assert admin.delete("/api/admin/products/TEST-9001").status_code == 204 and api.get("/api/products/TEST-9001").status_code == 404
    assert api.c.post("/api/chat", json={"message": "price of TEST-9001"}).get_json()["status"] != "answer"


def test_variant_management_and_deleting_products_keeps_order_history(demo_app, admin, shopper):
    admin.post("/api/admin/products", {"id": "TEST-9002", "title": "Trial Tee", "category": "Fashion", "price": 500, "stock_qty": None,
                                       "variants": [{"sku": "TT-S", "options": {"size": "S"}, "stock_qty": 3}, {"sku": "TT-M", "options": {"size": "M"}, "stock_qty": 0}]})
    d = shopper.get("/api/products/TEST-9002").get_json()
    assert [v["label"] for v in d["variants"]] == ["S", "M"] and d["stock_qty"] == 3
    assert shopper.post("/api/cart/items", {"product_id": "TEST-9002", "variant_id": d["variants"][1]["id"], "quantity": 1}).get_json()["error"]["code"] == "out_of_stock"
    add(shopper, "TEST-9002", 2, size="S")
    n = buy(shopper).get_json()["order"]["order_number"]
    assert shopper.get("/api/products/TEST-9002").get_json()["variants"][0]["stock_qty"] == 1
    assert admin.delete("/api/admin/products/TEST-9002").status_code == 204
    o = shopper.get(f"/api/orders/{n}").get_json()
    assert o["items"][0]["title"] == "Trial Tee" and o["items"][0]["variant_label"] == "S"


def test_category_management(admin):
    assert admin.post("/api/admin/categories", {"name": "A"}).status_code == 422
    c = admin.post("/api/admin/categories", {"name": "Garden"}).get_json()
    assert admin.post("/api/admin/categories", {"name": "garden"}).status_code == 409
    assert admin.put(f"/api/admin/categories/{c['id']}", {"name": "Garden & Outdoor"}).get_json()["name"] == "Garden & Outdoor"
    footwear = next(x for x in admin.get("/api/admin/categories").get_json()["items"] if x["name"] == "Footwear")
    assert footwear["products"] == 6 and admin.delete(f"/api/admin/categories/{footwear['id']}").status_code == 409     # in use
    assert admin.delete(f"/api/admin/categories/{c['id']}").status_code == 204


def test_order_status_workflow(demo_app, admin, shopper):
    stock = lambda: shopper.get("/api/products/VRT-1009").get_json()["stock_qty"]
    start = stock()
    add(shopper, "VRT-1009", 1)
    n = buy(shopper).get_json()["order"]["order_number"]
    patch = lambda s: admin.patch(f"/api/admin/orders/{n}/status", {"status": s})
    assert patch("delivered").status_code == 409 and patch("nonsense").status_code == 400          # can't skip steps / unknown status
    for s in ("processing", "shipped", "delivered"):
        r = patch(s)
        assert r.status_code == 200 and r.get_json()["status"] == s
    assert patch("cancelled").status_code == 409 and patch("processing").status_code == 409
    assert [e["status"] for e in shopper.get(f"/api/orders/{n}").get_json()["events"]] == ["placed", "processing", "shipped", "delivered"]
    assert stock() == start - 1
    add(shopper, "VRT-1009", 1)
    n2 = buy(shopper).get_json()["order"]["order_number"]
    admin.patch(f"/api/admin/orders/{n2}/status", {"status": "processing"})
    assert admin.patch(f"/api/admin/orders/{n2}/status", {"status": "cancelled", "note": "stock error"}).status_code == 200
    assert stock() == start - 1                                                                    # the cancelled order's unit went back on the shelf
    listed = admin.get(f"/api/admin/orders?q={n}").get_json()
    assert listed["total"] == 1 and listed["items"][0]["contact_email"] == shopper.email


def test_admin_customer_list_exposes_only_what_order_management_needs(demo_app, admin, shopper):
    r = admin.get(f"/api/admin/customers?q={shopper.email}").get_json()
    assert r["total"] == 1 and set(r["items"][0]) == {"id", "name", "email", "joined", "orders", "spent_text", "is_demo"}
    assert "password" not in str(r).lower()


def test_analytics_are_derived_from_stored_records():
    app = make_app()
    admin = Api(app)
    bootstrap.ensure_admin(app.extensions["verity"].db, "root@example.com", "Granite-Orbit-77")
    admin.login("root@example.com", "Granite-Orbit-77")
    s = admin.get("/api/admin/summary").get_json()                                       # brand-new database: honest zeros
    assert s["orders"] == {"total": 0, "active": 0, "cancelled": 0} and s["order_value"]["value"] == 0 and s["revenue"]["value"] == 0 and s["customers"] == 0
    assert s["products"]["active"] == 52 and s["demo"]["orders"] == 0 and s["inventory"]["out_of_stock"] >= 3 and s["inventory"]["low_items"]
    ch = admin.get("/api/admin/charts").get_json()
    assert sum(d["orders"] for d in ch["sales"]) == 0 and all(x["value"] == 0 for x in ch["orders_by_status"]) and ch["top_products"] == []
    assert sum(x["value"] for x in ch["category_distribution"]) == 52 and sum(x["value"] for x in ch["stock_distribution"]) == 52
    a, b = Api(app), Api(app)
    a.register("a@example.com"), b.register("b@example.com")
    add(a, "VRT-1009", 2)
    n1 = buy(a).get_json()["order"]["order_number"]                                      # 2 x 1099 = 2198
    add(b, "VRT-7002", 3)
    n2 = buy(b).get_json()["order"]["order_number"]                                      # 3 x 199 = 597 + 59
    add(b, "VRT-1009", 1)
    n3 = buy(b).get_json()["order"]["order_number"]                                      # 1099, will be cancelled
    b.post(f"/api/orders/{n3}/cancel")
    for st in ("processing", "shipped", "delivered"):
        admin.patch(f"/api/admin/orders/{n1}/status", {"status": st})
    s = admin.get("/api/admin/summary").get_json()
    assert s["customers"] == 2 and s["orders"] == {"total": 3, "active": 2, "cancelled": 1}
    assert s["order_value"]["value"] == 2198 + 597 + 59 and s["revenue"]["value"] == 2198        # revenue = delivered only
    ch = admin.get("/api/admin/charts").get_json()
    assert {x["key"]: x["value"] for x in ch["orders_by_status"]} == {"placed": 1, "processing": 0, "shipped": 0, "delivered": 1, "cancelled": 1}
    assert ch["top_products"] == [{"id": "VRT-7002", "label": "Gel Pens, Pack of 10", "value": 3}, {"id": "VRT-1009", "label": "FastPort 33W USB-C Charger", "value": 2}]   # ranked by units ordered; the cancelled order is excluded
    assert sum(d["orders"] for d in ch["sales"]) == 2
    assert {c["label"]: c["value"] for c in ch["category_revenue"]} == {"Electronics": 2198, "Books & Stationery": 597}   # line totals only: shipping is not category revenue


def test_demo_seeded_data_is_flagged_and_excludable():
    app = make_app()
    db = app.extensions["verity"].db
    bootstrap.ensure_admin(db, "root@example.com", "Granite-Orbit-77")
    res = bootstrap.seed_demo(db, "Seeded-Pass-2026", 20, settings=dict(app.config))
    assert res["orders"] == 20 and bootstrap.seed_demo(db, "Seeded-Pass-2026", 20, settings=dict(app.config))["orders"] == 0       # idempotent
    admin = Api(app)
    admin.login("root@example.com", "Granite-Orbit-77")
    s = admin.get("/api/admin/summary").get_json()
    assert s["orders"]["total"] == 20 and s["demo"]["orders"] == 20 and "demo seeder" in s["demo"]["note"] and s["customers"] == 4
    z = admin.get("/api/admin/summary?include_demo=0").get_json()
    assert z["orders"]["total"] == 0 and z["customers"] == 0 and z["order_value"]["value"] == 0
    assert all(o["is_demo_seeded"] for o in admin.get("/api/admin/orders?page_size=50").get_json()["items"])
    with db.scope() as sess:
        assert sess.scalar(select(Order).where(Order.is_demo.is_(False))) is None


def test_stats_endpoint_needs_the_admin_key_and_health_endpoints_need_admin(demo_app, admin):
    assert Api(demo_app).get("/api/stats").status_code == 403
    keyed = Api(make_app(ADMIN_KEY="s3cret-key-for-tests"))
    assert keyed.get("/api/stats", headers={"X-Admin-Key": "wrong"}).status_code == 403
    assert keyed.get("/api/stats", headers={"X-Admin-Key": "s3cret-key-for-tests"}).status_code == 200
    h = admin.get("/api/admin/health").get_json()
    assert h["database"]["ok"] and h["database"]["migration"] == "0001" and h["catalogue"]["synthetic"] is True and h["ai"]["mode"] == "grounded"
    assert "off" in admin.get("/api/admin/ai").get_json()["note"].lower()
