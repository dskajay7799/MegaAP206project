"""Flask application factory: configuration, database, catalogue runtime, security hooks, blueprints.

Business logic lives in `services/`, HTTP in `routes/`. `gunicorn backend.app.main:app` still works: `app` is created lazily on first access."""
import logging
import time
import uuid
from types import SimpleNamespace

from flask import Flask, g, jsonify, request, send_from_directory

from . import config, security, store
from .database import Database, resolve_url
from .http import error

logging.basicConfig(level=config.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api")

PRIVATE_PREFIXES = ("/api/auth", "/api/cart", "/api/account", "/api/orders", "/api/admin", "/api/checkout", "/api/recommendations")


def create_app(overrides: dict | None = None) -> Flask:
    settings = config.load_settings(overrides)
    app = Flask(__name__, static_folder=None)
    app.config.update(settings)
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000
    url, _ = resolve_url(settings)
    database = Database(url)
    if settings["AUTO_MIGRATE"]:
        database.migrate()
    sections, source = store.ensure_catalogue(database, settings)
    runtime = store.Runtime(database, sections, source)
    app.extensions["verity"] = SimpleNamespace(db=database, runtime=runtime, limiter=security.RateLimiter(), settings=settings, started=time.time())

    from . import bootstrap
    bootstrap.run(app)
    runtime.assistant()           # build the index now so the first request isn't slow and misconfiguration fails at startup

    @app.before_request
    def _before():
        g.rid = uuid.uuid4().hex[:8]
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            return "", 204
        return security.check_csrf()

    @app.after_request
    def _after(resp):
        resp.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                             "Permissions-Policy": "camera=(), microphone=(self), geolocation=()", "Cross-Origin-Opener-Policy": "same-origin"})
        if settings["PRODUCTION"]:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
            origin = request.headers.get("Origin", "").rstrip("/")
            if origin and origin in [o.rstrip("/") for o in app.config["CORS_ORIGINS"]]:
                resp.headers.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin", "Access-Control-Allow-Credentials": "true",
                                     "Access-Control-Allow-Headers": "Content-Type, X-CSRF-Token, Idempotency-Key, X-Admin-Key",
                                     "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS", "Access-Control-Max-Age": "600"})
        else:
            connect = " ".join(["'self'", *app.config["CORS_ORIGINS"]])
            resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; font-src 'self'; "
                                                      f"connect-src {connect}; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
            if request.path.startswith("/assets/"):
                resp.headers["Cache-Control"] = "public, max-age=86400"
            elif resp.status_code == 200:
                resp.headers["Cache-Control"] = "no-cache"
        return security.apply_cookie(resp)

    @app.teardown_appcontext
    def _close(exc):
        s = g.pop("db", None)
        if s is not None:
            if exc:
                s.rollback()
            s.close()

    @app.errorhandler(404)
    def _404(_e):
        return error(404, "not_found", "Not found.") if request.path.startswith("/api/") else ("Not found", 404)

    @app.errorhandler(405)
    def _405(_e):
        return error(405, "method_not_allowed", "Method not allowed.")

    @app.errorhandler(413)
    def _413(_e):
        return error(413, "too_large", "That request is too large.")

    @app.errorhandler(500)
    def _500(_e):
        log.exception("unhandled error rid=%s", g.get("rid"))
        return error(500, "internal_error", "Something went wrong on our side. Please try again.")

    from .routes import register
    register(app)

    @app.get("/")
    def index():
        return send_from_directory(app.config["FRONTEND_DIR"], "index.html")

    @app.get("/<path:name>")
    def assets(name):
        if name.startswith("api/"):
            return error(404, "not_found", "Not found.")
        return send_from_directory(app.config["FRONTEND_DIR"], name)

    log.info("Verity ready: db=%s catalogue_source=%s env=%s", database.kind, runtime.source, settings["APP_ENV"])
    return app


def __getattr__(name):          # lazy `app` for gunicorn / `flask --app backend.app.main`
    if name == "app":
        global _APP
        try:
            return _APP
        except NameError:
            _APP = create_app()
            return _APP
    raise AttributeError(name)
