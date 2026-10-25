"""Shared test utilities: build isolated apps (own SQLite file, chosen data folder) and a CSRF-aware API client."""
import os
import tempfile
from pathlib import Path

os.environ["GROQ_API_KEY"] = ""          # tests never call a real LLM
ROOT = Path(__file__).resolve().parents[1]


def make_app(**over):
    from backend.app.main import create_app
    base = {"DATABASE_URL": f"sqlite:///{tempfile.mktemp(suffix='.db', dir=os.environ.get('TMPDIR', '/tmp'))}", "APP_ENV": "test", "ALLOW_DEV_DATA": True, "DATA_DIR": Path("/nonexistent"),
            "DEV_DATA_DIR": ROOT / "demo_store", "RATE_LIMIT_PER_MIN": 1000, "AUTH_RATE_LIMIT_PER_MIN": 1000, "WRITE_RATE_LIMIT_PER_MIN": 10000,
            "CORS_ORIGINS": ["https://shop.example.app"], "TESTING": True, "CHECKOUT_ENABLED": True, "SECRET_KEY": "test-secret-key-not-for-production"}
    base.update(over)
    return create_app(base)


class Api:
    """Wraps Flask's test client; carries the session cookie and the CSRF token exactly as the browser app does."""

    def __init__(self, app):
        self.app, self.c, self.csrf = app, app.test_client(), ""
        self.refresh()

    def refresh(self):
        r = self.c.get("/api/auth/me").get_json()
        self.csrf = r["csrf"]
        return r

    def _go(self, method, path, json=None, headers=None, csrf=True):
        h = dict(headers or {})
        if csrf:
            h.setdefault("X-CSRF-Token", self.csrf)
        r = getattr(self.c, method)(path, json=json, headers=h) if json is not None or method != "get" else self.c.get(path, headers=h)
        if r.is_json and isinstance(r.get_json(), dict) and "csrf" in r.get_json() and r.status_code < 300 and path.startswith("/api/auth"):
            self.csrf = r.get_json()["csrf"]
        return r

    def get(self, p, **k):
        return self._go("get", p, **k)

    def post(self, p, json=None, **k):
        return self._go("post", p, json if json is not None else {}, **k)

    def put(self, p, json=None, **k):
        return self._go("put", p, json if json is not None else {}, **k)

    def patch(self, p, json=None, **k):
        return self._go("patch", p, json if json is not None else {}, **k)

    def delete(self, p, json=None, **k):
        return self._go("delete", p, json, **k)

    def register(self, email="shopper@example.com", password="Sunrise-Lamp-42", name="Test Shopper"):
        return self.post("/api/auth/register", {"name": name, "email": email, "password": password})

    def login(self, email, password):
        return self.post("/api/auth/login", {"email": email, "password": password})
