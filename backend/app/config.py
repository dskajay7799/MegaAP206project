"""Environment-based configuration.

Module-level constants are kept for the pieces that read them directly (the assistant's LLM layer and the original tests).
New application settings live in `load_settings()`, which builds a plain dict that the Flask factory stores in `app.config`;
tests pass overrides instead of mutating the environment.
"""
from dotenv import load_dotenv
import os
import secrets
from pathlib import Path

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
DEV_DATA_DIR = Path(os.getenv("DEV_DATA_DIR", ROOT / "demo_store"))
ALLOW_DEV_DATA = os.getenv("ALLOW_DEV_DATA", "0") == "1"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "500"))
FRONTEND_DIR = ROOT / "frontend"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
DATABASE_URL = os.getenv("DATABASE_URL", "")
ADMIN_KEY = os.getenv("ADMIN_KEY", "")
INR_PER_1K_TOKENS = float(os.getenv("INR_PER_1K_TOKENS", "0"))
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))
CORS_ORIGINS = [o.strip().rstrip("/") for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]  # e.g. https://your-site.netlify.app

DEV_KEY = "dev-only-insecure-key-change-me"


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def normalise_db_url(url: str) -> str:
    """Render/Neon hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the driver named explicitly."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def load_settings(overrides: dict | None = None) -> dict:
    env = os.getenv("APP_ENV", "development").lower()
    s = {
        "APP_ENV": env,
        "PRODUCTION": env == "production",
        "SECRET_KEY": os.getenv("SECRET_KEY", ""),
        "DATABASE_URL": os.getenv("DATABASE_URL", ""),
        "ALLOW_EPHEMERAL_DB": _flag("ALLOW_EPHEMERAL_DB"),
        "AUTO_MIGRATE": _flag("AUTO_MIGRATE", "1"),
        "DATA_DIR": DATA_DIR, "DEV_DATA_DIR": DEV_DATA_DIR, "ALLOW_DEV_DATA": ALLOW_DEV_DATA,
        "CORS_ORIGINS": list(CORS_ORIGINS), "FRONTEND_DIR": FRONTEND_DIR,
        "RATE_LIMIT_PER_MIN": RATE_LIMIT_PER_MIN, "AUTH_RATE_LIMIT_PER_MIN": int(os.getenv("AUTH_RATE_LIMIT_PER_MIN", "12")),
        "WRITE_RATE_LIMIT_PER_MIN": int(os.getenv("WRITE_RATE_LIMIT_PER_MIN", "120")),
        "TRUSTED_PROXY_HOPS": int(os.getenv("TRUSTED_PROXY_HOPS", "1")),
        "MAX_MESSAGE_CHARS": MAX_MESSAGE_CHARS, "ADMIN_KEY": ADMIN_KEY,
        # cookies / sessions
        "COOKIE_SECURE": _flag("COOKIE_SECURE", "1" if env == "production" else "0"),
        "COOKIE_SAMESITE": os.getenv("COOKIE_SAMESITE", "Lax"),
        "SESSION_IDLE_DAYS": float(os.getenv("SESSION_IDLE_DAYS", "7")),
        "SESSION_MAX_DAYS": float(os.getenv("SESSION_MAX_DAYS", "30")),
        "MAX_FAILED_LOGINS": int(os.getenv("MAX_FAILED_LOGINS", "5")),
        "LOCKOUT_MINUTES": float(os.getenv("LOCKOUT_MINUTES", "10")),
        # storefront policy numbers (must match the policy text; checked by a test for the demo store)
        "SHIPPING_FEE_RUPEES": int(os.getenv("SHIPPING_FEE_RUPEES", "59")),
        "FREE_SHIPPING_ABOVE_RUPEES": int(os.getenv("FREE_SHIPPING_ABOVE_RUPEES", "999")),
        "MAX_QTY_PER_LINE": int(os.getenv("MAX_QTY_PER_LINE", "10")),
        # Demo build: order placement is OFF. No payment, card, UPI or bank details are ever collected, and no order can be created.
        "CHECKOUT_ENABLED": _flag("CHECKOUT_ENABLED", "0"),
        # The public demo has NO checkout: the order API refuses unless this is deliberately switched on (API only, no UI, still no payments).
        # privacy
        "LOG_CHATS": _flag("LOG_CHATS", "0"),
        # bootstrap (never logged)
        "ADMIN_EMAIL": os.getenv("ADMIN_EMAIL", "").strip().lower(), "ADMIN_PASSWORD": os.getenv("ADMIN_PASSWORD", ""),
        "SEED_DEMO": _flag("SEED_DEMO"), "DEMO_PASSWORD": os.getenv("DEMO_PASSWORD", ""),
        # email (password reset)
        "SMTP_HOST": os.getenv("SMTP_HOST", ""), "SMTP_PORT": int(os.getenv("SMTP_PORT", "587")),
        "SMTP_USER": os.getenv("SMTP_USER", ""), "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", ""),
        "MAIL_FROM": os.getenv("MAIL_FROM", ""), "PUBLIC_URL": os.getenv("PUBLIC_URL", "").rstrip("/"),
        "DEV_SHOW_RESET_LINK": _flag("DEV_SHOW_RESET_LINK"),
        "TESTING": False,
    }
    if overrides:
        s.update(overrides)
        if "APP_ENV" in overrides and "PRODUCTION" not in overrides:
            s["PRODUCTION"] = s["APP_ENV"] == "production"
    if s["PRODUCTION"]:
        s["COOKIE_SECURE"] = True            # production is HTTPS-only; there is no switch to turn this off
    if not s["SECRET_KEY"]:
        if s["PRODUCTION"]:
            raise RuntimeError("SECRET_KEY must be set when APP_ENV=production.")
        s["SECRET_KEY"] = DEV_KEY
    if s["PRODUCTION"] and s["SECRET_KEY"] == DEV_KEY:
        raise RuntimeError("Refusing to start in production with the development SECRET_KEY.")
    return s


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
