"""Headers, CSP, cookies, CORS, production guards, migrations, secrets hygiene, catalogue-source protection, hostile input."""
import re
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from backend.app import store
from backend.app.database import Database
from backend.app.models import Base, Product
from tests.helpers import ROOT, Api, make_app


def test_security_headers_and_strict_csp(api):
    r = api.c.get("/")
    assert r.status_code == 200
    csp = r.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in csp and "'unsafe-eval'" not in csp and "script-src 'self'" in csp and "style-src 'self'" in csp
    assert "font-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp and "base-uri 'self'" in csp
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY" and r.headers["Referrer-Policy"] == "no-referrer"
    assert "Strict-Transport-Security" not in r.headers                                   # only in production (HTTPS)


def test_private_and_api_responses_are_never_cached(shopper):
    for path in ("/api/auth/me", "/api/cart", "/api/orders", "/api/account/dashboard", "/api/products", "/api/meta"):
        assert shopper.c.get(path).headers["Cache-Control"] == "no-store", path
    assert "max-age" in shopper.c.get("/assets/products/VRT-1001-1.svg").headers["Cache-Control"]
    assert shopper.c.get("/styles/base.css").headers["Cache-Control"] == "no-cache"


def test_cors_allows_only_configured_origins_with_credentials(api):
    ok = api.c.get("/api/meta", headers={"Origin": "https://shop.example.app"})
    assert ok.headers["Access-Control-Allow-Origin"] == "https://shop.example.app" and ok.headers["Access-Control-Allow-Credentials"] == "true"
    assert "Access-Control-Allow-Origin" not in api.c.get("/api/meta", headers={"Origin": "https://evil.example"}).headers
    pre = api.c.options("/api/cart/items", headers={"Origin": "https://shop.example.app", "Access-Control-Request-Method": "POST"})
    assert pre.status_code == 204 and "X-CSRF-Token" in pre.headers["Access-Control-Allow-Headers"] and "Idempotency-Key" in pre.headers["Access-Control-Allow-Headers"]
    assert "*" not in ok.headers["Access-Control-Allow-Origin"]


def test_production_refuses_unsafe_configuration(tmp_path):
    base = dict(APP_ENV="production", DATABASE_URL=f"sqlite:///{tmp_path}/p.db", ALLOW_DEV_DATA=True)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        make_app(**base, SECRET_KEY="")
    with pytest.raises(RuntimeError, match="development SECRET_KEY"):
        make_app(**base, SECRET_KEY="dev-only-insecure-key-change-me")
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        make_app(APP_ENV="production", DATABASE_URL="", SECRET_KEY="x" * 32, ALLOW_DEV_DATA=True)
    app = make_app(**base, SECRET_KEY="x" * 32)
    r = Api(app).c.get("/api/auth/me")
    assert "Secure" in r.headers["Set-Cookie"] and "HttpOnly" in r.headers["Set-Cookie"] and "Strict-Transport-Security" in r.headers
    assert Api(app).c.get("/").headers["Strict-Transport-Security"].startswith("max-age=")


def test_cross_origin_mode_uses_samesite_none_secure():
    app = make_app(COOKIE_SAMESITE="None", COOKIE_SECURE=True)
    cookie = Api(app).c.get("/api/auth/me").headers["Set-Cookie"]
    assert "SameSite=None" in cookie and "Secure" in cookie


def test_no_synthetic_catalogue_in_production_without_explicit_opt_in(tmp_path):
    with pytest.raises(RuntimeError, match="Catalogue/policy not found"):
        make_app(APP_ENV="production", SECRET_KEY="x" * 32, DATABASE_URL=f"sqlite:///{tmp_path}/q.db", ALLOW_DEV_DATA=False)


def test_real_catalogue_is_never_replaced_by_synthetic_and_vice_versa(tmp_path):
    url = f"sqlite:///{tmp_path}/swap.db"
    real = tmp_path / "real"
    real.mkdir()
    (real / "catalogue.json").write_text('[{"id":"R-1","title":"Real Widget","price":10,"stock":"in_stock","category":"Tools","description":"A real widget."}]')
    (real / "policy.txt").write_text("Returns\nReturn within 30 days.\n")
    a1 = make_app(DATABASE_URL=url)                                                      # starts on the synthetic demo store
    assert a1.extensions["verity"].runtime.source == "demo-store" and len(a1.extensions["verity"].runtime.assistant().products) == 52
    a2 = make_app(DATABASE_URL=url, DATA_DIR=real)                                       # real data arrives: synthetic catalogue is replaced
    rt = a2.extensions["verity"].runtime
    assert rt.source == "challenge" and [p.id for p in rt.assistant().products] == ["R-1"]
    a3 = make_app(DATABASE_URL=url)                                                      # synthetic data must not overwrite the real catalogue
    assert a3.extensions["verity"].runtime.source == "challenge" and [p.id for p in a3.extensions["verity"].runtime.assistant().products] == ["R-1"]
    assert Api(a3).get("/api/health").get_json()["synthetic_data"] is False


def test_restart_keeps_accounts_orders_and_admin_edits(tmp_path):
    url = f"sqlite:///{tmp_path}/persist.db"
    from tests.conftest import ADDR, idem
    app = make_app(DATABASE_URL=url)
    a = Api(app)
    a.register("keeper@example.com")
    a.post("/api/cart/items", {"product_id": "VRT-1009", "quantity": 1})
    n = a.post("/api/orders", {"address": ADDR, "payment_method": "cod"}, headers=idem()).get_json()["order"]["order_number"]
    with app.extensions["verity"].db.scope() as s:
        s.get(Product, "VRT-1009").title = "Edited by admin"
        store.bump_version(s)
    restarted = Api(make_app(DATABASE_URL=url))                                          # a fresh process on the same database
    assert restarted.login("keeper@example.com", "Sunrise-Lamp-42").status_code == 200
    assert restarted.get(f"/api/orders/{n}").status_code == 200
    assert restarted.get("/api/products/VRT-1009").get_json()["title"] == "Edited by admin"       # importing again did not overwrite admin edits


def test_migrations_match_models(tmp_path):
    db = Database(f"sqlite:///{tmp_path}/m.db")
    db.migrate()
    with db.engine.connect() as c:
        assert compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata) == []
    db.migrate()                                                                          # idempotent


def test_frontend_contains_no_secrets():
    pat = re.compile(r"gsk_[A-Za-z0-9]{10,}|GROQ_API_KEY|ADMIN_KEY|SECRET_KEY|ADMIN_PASSWORD|DATABASE_URL|postgres(ql)?://|X-Admin-Key", re.I)
    hits = [(str(f.relative_to(ROOT)), m.group(0)) for f in (ROOT / "frontend").rglob("*") if f.is_file() and f.suffix in (".js", ".html", ".css", ".json", ".svg") for m in [pat.search(f.read_text("utf-8", "ignore"))] if m]
    assert hits == []


def test_rate_limit_uses_the_configured_proxy_hop():
    app = make_app(RATE_LIMIT_PER_MIN=2, TRUSTED_PROXY_HOPS=2)
    c = app.test_client()
    hit = lambda xff: c.post("/api/chat", json={"message": "price of VRT-1001"}, headers={"X-Forwarded-For": xff}).status_code
    assert [hit("1.1.1.1, 9.9.9.9") for _ in range(3)] == [200, 200, 429]                # client 1.1.1.1 (behind two proxies)
    assert hit("2.2.2.2, 9.9.9.9") == 200                                                  # a different client behind the same proxy has its own budget
    assert hit("6.6.6.6, 1.1.1.1, 9.9.9.9") == 429                                         # a forged extra left-most entry can't dodge the limit: the client is read from the right (1.1.1.1)
    one = make_app(RATE_LIMIT_PER_MIN=2, TRUSTED_PROXY_HOPS=1).test_client()
    codes = [one.post("/api/chat", json={"message": "price of VRT-1001"}, headers={"X-Forwarded-For": f"{i}.{i}.{i}.{i}, 9.9.9.9"}).status_code for i in range(1, 5)]
    assert codes == [200, 200, 429, 429]                                                   # hop 1 = the proxy itself: every user shares one bucket (hence the setting)


@pytest.mark.parametrize("payload", ["' OR 1=1 --", "'; DROP TABLE products; --", "<script>alert(1)</script>", "%00", "../../etc/passwd", "𝕏" * 300])
def test_hostile_input_never_causes_a_server_error(api, payload):
    assert api.get("/api/products", ).status_code == 200
    for path in (f"/api/products?q={payload}", f"/api/products/{payload}", f"/api/products?category={payload}&brand={payload}&ids={payload}", f"/api/compare?ids={payload},{payload}x"):
        assert api.c.get(path).status_code < 500, path
    for ep in ("/api/chat", "/api/smartmatch"):
        r = api.c.post(ep, json={"message": payload, "text": payload})
        assert r.status_code < 500, ep
    assert api.post("/api/auth/login", {"email": payload, "password": payload}).status_code in (401, 429)
    assert api.get("/api/products").get_json()["total"] == 52                              # nothing was damaged


def test_oversized_and_malformed_bodies_are_rejected_cleanly(api):
    assert api.c.post("/api/chat", data="x" * 1_200_000, content_type="application/json").status_code == 413
    assert api.c.post("/api/chat", data="{not json", content_type="application/json").status_code == 400
    assert api.c.post("/api/smartmatch", data="[]", content_type="application/json").status_code == 400
    assert api.c.get("/api/does-not-exist").get_json()["error"]["code"] == "not_found" and api.c.delete("/api/meta").status_code in (403, 405)


def test_error_responses_never_leak_internals(api):
    r = api.c.get("/api/products/%27")
    body = r.get_data(as_text=True)
    assert "Traceback" not in body and "sqlalchemy" not in body.lower() and ".py" not in body
