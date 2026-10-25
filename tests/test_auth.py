"""Registration, login, sessions, lockout, CSRF, password change/reset, account deletion, data isolation."""
import datetime as dt

import pytest
from sqlalchemy import select

from backend.app.models import AuthSession, PasswordReset
from tests.helpers import Api, make_app


def test_register_validates_and_blocks_duplicates(api):
    r = api.post("/api/auth/register", {"name": "A", "email": "bad", "password": "short"})
    assert r.status_code == 422 and {"name", "email", "password"} <= set(r.get_json()["error"]["fields"])
    assert api.register("dup@example.com").status_code == 201
    other = Api(api.app)
    r = other.register("DUP@example.com")                             # case-insensitive duplicate
    assert r.status_code == 409 and r.get_json()["error"]["code"] == "email_taken"
    for pw in ("password123", "alllettersonly", "12345678901"):
        assert Api(api.app).register(f"p{pw[:4]}@example.com", pw).status_code == 422


def test_passwords_are_hashed_never_stored_plaintext(demo_app, shopper):
    from backend.app.models import User
    with demo_app.extensions["verity"].db.scope() as s:
        u = s.scalar(select(User).where(User.email == shopper.email))
        assert "Sunrise-Lamp-42" not in u.password_hash and u.password_hash.startswith(("scrypt:", "pbkdf2:"))
    me = shopper.get("/api/auth/me").get_json()
    assert "password_hash" not in str(me) and "Sunrise-Lamp-42" not in str(me)


def test_login_logout_and_protected_routes(demo_app, shopper):
    assert shopper.get("/api/orders").status_code == 200
    shopper.post("/api/auth/logout")
    assert shopper.get("/api/orders").status_code == 401 and shopper.get("/api/account/wishlist").status_code == 401
    assert shopper.get("/api/auth/me").get_json()["user"] is None
    assert shopper.login(shopper.email, "Sunrise-Lamp-42").status_code == 200
    assert shopper.get("/api/auth/me").get_json()["user"]["email"] == shopper.email


def test_wrong_password_message_is_generic(api, shopper):
    a = Api(shopper.app)
    known = a.login(shopper.email, "wrong-wrong-1").get_json()["error"]
    unknown = a.login("nobody@example.com", "wrong-wrong-1").get_json()["error"]
    assert known["message"] == unknown["message"] and known["code"] == unknown["code"] == "invalid_credentials"


def test_lockout_after_repeated_failures(demo_app):
    a = Api(demo_app)
    a.register("lock@example.com")
    a.post("/api/auth/logout")
    for _ in range(demo_app.config["MAX_FAILED_LOGINS"]):
        assert a.login("lock@example.com", "wrong-wrong-1").status_code == 401
    assert a.login("lock@example.com", "Sunrise-Lamp-42").status_code == 401          # even the right password is refused while locked
    from backend.app.models import User
    with demo_app.extensions["verity"].db.scope() as s:
        u = s.scalar(select(User).where(User.email == "lock@example.com"))
        u.locked_until = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
    assert a.login("lock@example.com", "Sunrise-Lamp-42").status_code == 200


def test_csrf_and_origin_enforced(demo_app, shopper):
    c = shopper.c
    assert c.post("/api/cart/items", json={"product_id": "VRT-1009"}).status_code == 403                                  # no token
    assert c.post("/api/cart/items", json={"product_id": "VRT-1009"}, headers={"X-CSRF-Token": "x" * 43}).status_code == 403  # wrong token
    ok = {"X-CSRF-Token": shopper.csrf}
    assert c.post("/api/cart/items", json={"product_id": "VRT-1009"}, headers=ok).status_code == 201
    assert c.post("/api/cart/items", json={"product_id": "VRT-1009"}, headers={**ok, "Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/cart/items", json={"product_id": "VRT-1009"}, headers={**ok, "Origin": "https://shop.example.app"}).status_code == 201


def test_csrf_token_is_bound_to_the_session(demo_app, shopper):
    stolen = shopper.csrf
    other = Api(demo_app)
    assert other.c.post("/api/cart/items", json={"product_id": "VRT-1009"}, headers={"X-CSRF-Token": stolen}).status_code == 403


def test_session_cookie_attributes_and_storage(demo_app, shopper):
    r = Api(demo_app).c.get("/api/auth/me")
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Path=/" in cookie
    from backend.app.models import AuthSession
    token = shopper.c.get_cookie("verity_sid").value
    with demo_app.extensions["verity"].db.scope() as s:
        hashes = [x.token_hash for x in s.scalars(select(AuthSession))]
        assert token not in hashes and len(hashes[0]) == 64          # only a hash is stored, a DB leak can't be replayed


def test_session_expiry_idle_and_absolute(demo_app, shopper):
    with demo_app.extensions["verity"].db.scope() as s:
        row = s.scalars(select(AuthSession).order_by(AuthSession.id.desc())).first()
        row.last_seen_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=demo_app.config["SESSION_IDLE_DAYS"] + 1)
    assert shopper.get("/api/orders").status_code == 401
    a = Api(demo_app)
    a.register("expire@example.com")
    with demo_app.extensions["verity"].db.scope() as s:
        row = s.scalars(select(AuthSession).order_by(AuthSession.id.desc())).first()
        row.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    assert a.get("/api/orders").status_code == 401


def test_login_rotates_the_session_token(demo_app):
    a = Api(demo_app)
    before = a.c.get_cookie("verity_sid").value
    a.register("rotate@example.com")
    assert a.c.get_cookie("verity_sid").value != before


def test_password_change_revokes_other_sessions(demo_app, shopper):
    second = Api(demo_app)
    assert second.login(shopper.email, "Sunrise-Lamp-42").status_code == 200
    assert shopper.post("/api/auth/password/change", {"current_password": "bad-bad-1", "new_password": "Newer-Pass-9988"}).status_code == 403
    assert shopper.post("/api/auth/password/change", {"current_password": "Sunrise-Lamp-42", "new_password": "Newer-Pass-9988"}).status_code == 200
    assert second.get("/api/orders").status_code == 401 and shopper.get("/api/orders").status_code == 200
    assert Api(demo_app).login(shopper.email, "Newer-Pass-9988").status_code == 200


def test_password_reset_is_honest_when_email_is_not_configured(demo_app):
    a = Api(demo_app)
    r = a.post("/api/auth/password/forgot", {"email": "x@example.com"})
    assert r.status_code == 501 and "isn't set up" in r.get_json()["error"]["message"]


def test_dev_reset_flow_labelled_demo_and_never_in_production():
    app = make_app(DEV_SHOW_RESET_LINK=True)
    a = Api(app)
    a.register("reset@example.com")
    a.post("/api/auth/logout")
    r = a.post("/api/auth/password/forgot", {"email": "reset@example.com"}).get_json()
    assert r["demo"] is True and "nothing was sent" in r["message"] and "#/reset?token=" in r["demo_reset_link"]
    token = r["demo_reset_link"].split("token=")[1]
    assert a.post("/api/auth/password/reset", {"token": token, "new_password": "short"}).status_code == 422
    assert a.post("/api/auth/password/reset", {"token": token, "new_password": "Fresh-Start-5521"}).status_code == 200
    assert a.post("/api/auth/password/reset", {"token": token, "new_password": "Fresh-Start-5522"}).status_code == 400      # single use
    assert a.login("reset@example.com", "Fresh-Start-5521").status_code == 200
    prod = make_app(APP_ENV="production", ALLOW_EPHEMERAL_DB=True, DEV_SHOW_RESET_LINK=True, SECRET_KEY="prod-secret-xxxxxxxxxxxxxxxx")
    assert Api(prod).post("/api/auth/password/forgot", {"email": "reset@example.com"}).status_code == 501              # token is never returned in production


def test_expired_reset_token_rejected(demo_app):
    app = make_app(DEV_SHOW_RESET_LINK=True)
    a = Api(app)
    a.register("old@example.com")
    link = a.post("/api/auth/password/forgot", {"email": "old@example.com"}).get_json()["demo_reset_link"]
    with app.extensions["verity"].db.scope() as s:
        for pr in s.scalars(select(PasswordReset)):
            pr.expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    assert a.post("/api/auth/password/reset", {"token": link.split("token=")[1], "new_password": "Fresh-Start-5521"}).status_code == 400


def test_auth_rate_limit(demo_app):
    app = make_app(AUTH_RATE_LIMIT_PER_MIN=4)
    a = Api(app)
    codes = [a.login("nobody@example.com", "wrong-wrong-1").status_code for _ in range(7)]
    assert codes[:4] == [401] * 4 and codes[4:] == [429] * 3


def test_account_deletion_removes_data_but_keeps_anonymised_orders(demo_app):
    from tests.conftest import ADDR, idem
    a = Api(demo_app)
    a.register("gone@example.com")
    a.post("/api/cart/items", {"product_id": "VRT-1009", "quantity": 1})
    o = a.post("/api/orders", {"address": ADDR, "payment_method": "cod"}, headers=idem()).get_json()["order"]
    assert a.delete("/api/account", {"password": "wrong"}).status_code == 403
    assert a.delete("/api/account", {"password": "Sunrise-Lamp-42"}).status_code == 200
    assert Api(demo_app).login("gone@example.com", "Sunrise-Lamp-42").status_code == 401
    from backend.app.models import Order
    with demo_app.extensions["verity"].db.scope() as s:
        row = s.scalar(select(Order).where(Order.order_number == o["order_number"]))
        assert row is not None and row.user_id is None and row.ship_name == "Deleted account" and row.ship_line1 == ""
