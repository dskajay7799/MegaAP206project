import itertools

import pytest

from tests.helpers import Api, make_app

_n = itertools.count(1)


@pytest.fixture(scope="module")
def demo_app():
    """A fresh app + database per test module, so state changed by one module (prices, stock) can never leak into another."""
    return make_app()


@pytest.fixture()
def api(demo_app):
    demo_app.extensions["verity"].limiter.clear()
    return Api(demo_app)


@pytest.fixture()
def shopper(demo_app):
    """A registered, signed-in customer with a unique email (tests never share accounts)."""
    a = Api(demo_app)
    n = next(_n)
    r = a.register(f"shopper{n}@example.com", "Sunrise-Lamp-42", f"Shopper {n}")
    assert r.status_code == 201, r.get_json()
    a.email = f"shopper{n}@example.com"
    return a


@pytest.fixture()
def admin(demo_app):
    from backend.app import bootstrap
    db = demo_app.extensions["verity"].db
    bootstrap.ensure_admin(db, "root@example.com", "Granite-Orbit-77", "Root Admin")
    a = Api(demo_app)
    assert a.login("root@example.com", "Granite-Orbit-77").status_code == 200
    return a


ADDR = {"full_name": "Test Shopper", "phone": "9876543210", "line1": "12 MG Road", "city": "Vijayawada", "state": "Andhra Pradesh", "pincode": "520010"}
_k = itertools.count(1)


def idem():
    return {"Idempotency-Key": f"test-key-{next(_k):06d}"}
