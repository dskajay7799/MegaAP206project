"""The shipped demo has checkout OFF: no order can be created, nothing payment-related is exposed, and browsing/cart/assistant work without signing in."""
import os

from backend.app import config
from tests.conftest import ADDR, idem
from tests.helpers import Api, make_app


def test_checkout_is_off_by_default_in_configuration():
    assert config.load_settings({"SECRET_KEY": "x" * 32})["CHECKOUT_ENABLED"] is False
    assert "CHECKOUT_ENABLED" not in os.environ or os.environ["CHECKOUT_ENABLED"] in ("", "0")


def test_no_order_can_be_placed_when_checkout_is_disabled():
    a = Api(make_app(CHECKOUT_ENABLED=False))
    a.register("buyer@example.com")
    assert a.post("/api/cart/items", {"product_id": "VRT-1009", "quantity": 1}).status_code == 201          # the cart still works
    for body in ({"address": ADDR, "payment_method": "demo_card"}, {}, {"payment_method": "upi", "upi_id": "x@bank"}, {"card_number": "4111111111111111"}):
        r = a.post("/api/orders", body, headers=idem())
        assert r.status_code == 403 and r.get_json()["error"]["code"] == "checkout_disabled" and "disabled in this demo" in r.get_json()["error"]["message"]
    assert a.get("/api/checkout/quote").status_code == 403
    assert a.get("/api/orders").get_json()["total"] == 0 and a.get("/api/cart").get_json()["items_count"] == 1          # nothing was consumed or created
    anon = Api(make_app(CHECKOUT_ENABLED=False))
    assert anon.post("/api/orders", {}, headers=idem()).get_json()["error"]["code"] == "checkout_disabled"            # same answer when signed out


def test_meta_and_cart_report_checkout_disabled():
    a = Api(make_app(CHECKOUT_ENABLED=False))
    m = a.get("/api/meta").get_json()["commerce"]
    assert m["checkout"] == "disabled" and m["checkout_enabled"] is False and "disabled in this demo" in m["checkout_note"]
    assert a.get("/api/cart").get_json()["checkout_enabled"] is False
    assert "payment_methods" not in str(m)


def test_everything_except_checkout_works_without_an_account():
    a = Api(make_app(CHECKOUT_ENABLED=False))
    assert a.get("/api/products?q=headphones").get_json()["total"] == 3
    assert a.post("/api/cart/items", {"product_id": "VRT-1009", "quantity": 2}).get_json()["total"] == 2198
    assert a.post("/api/smartmatch", {"text": "headphones under 3000"}).status_code == 200 and a.post("/api/basket", {"budget": 4000, "purpose": "study"}).status_code == 200
    assert a.get("/api/compare?ids=VRT-1001,VRT-1002").status_code == 200
    r = a.c.post("/api/chat", json={"message": "can I pay with UPI"}).get_json()
    assert r["status"] == "refused" and r["citations"] == []                                                        # the assistant never handles payments


def test_no_frontend_code_collects_payment_details():
    import re
    from tests.helpers import ROOT
    pat = re.compile(r"card[_ -]?number|cvv|cvc|expiry|\\bupi\\b|ifsc|account[_ -]?number|net ?banking|razorpay|stripe|paypal|payu|cashfree", re.I)
    hits = [f.name for f in (ROOT / "frontend").rglob("*.js") if pat.search(f.read_text("utf-8", "ignore"))]
    assert hits == []
