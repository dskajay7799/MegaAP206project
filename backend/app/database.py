"""Engine/session management and repeatable schema migration (Alembic). SQLite for local dev, PostgreSQL (Neon) in production."""
import contextlib
import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from . import config

log = logging.getLogger("database")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE = ROOT / "instance" / "verity.db"


def resolve_url(settings: dict) -> tuple[str, str]:
    """Returns (sqlalchemy_url, kind). Production refuses an ephemeral database unless explicitly allowed."""
    url = config.normalise_db_url(settings.get("DATABASE_URL") or "")
    if url:
        return url, ("sqlite" if url.startswith("sqlite") else "postgresql")
    if settings.get("PRODUCTION") and not settings.get("ALLOW_EPHEMERAL_DB"):
        raise RuntimeError("DATABASE_URL is required when APP_ENV=production (accounts, carts and orders must survive restarts). "
                           "Set it to a PostgreSQL/Neon URL, or set ALLOW_EPHEMERAL_DB=1 for a throw-away demo.")
    DEFAULT_SQLITE.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_SQLITE}", "sqlite"


class Database:
    def __init__(self, url: str):
        self.url = url
        self.kind = "sqlite" if url.startswith("sqlite") else "postgresql"
        kw = {"future": True, "pool_pre_ping": True}
        if self.kind == "sqlite":
            kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
        else:
            kw.update(pool_size=5, max_overflow=5, pool_recycle=300)
        self.engine = create_engine(url, **kw)
        if self.kind == "sqlite":
            @event.listens_for(self.engine, "connect")
            def _pragmas(dbapi_conn, _rec):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA busy_timeout=30000")
                try:
                    cur.execute("PRAGMA journal_mode=WAL")
                except Exception:   # in-memory / read-only databases
                    pass
                cur.close()
        self.sessionmaker = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def session(self):
        return self.sessionmaker()

    @contextlib.contextmanager
    def scope(self):
        s = self.session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def ping(self) -> bool:
        try:
            with self.engine.connect() as c:
                c.execute(text("SELECT 1"))
            return True
        except Exception as e:
            log.warning("database ping failed: %s", type(e).__name__)
            return False

    def migrate(self):
        """Apply Alembic migrations up to head. On PostgreSQL an advisory lock serialises concurrent workers."""
        from alembic import command
        from alembic.config import Config
        cfg = Config()
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        cfg.set_main_option("sqlalchemy.url", self.url.replace("%", "%%"))
        lock = None
        try:
            if self.kind == "postgresql":
                lock = self.engine.connect()
                lock.execute(text("SELECT pg_advisory_lock(7272741)"))
            command.upgrade(cfg, "head")
        finally:
            if lock is not None:
                with contextlib.suppress(Exception):
                    lock.execute(text("SELECT pg_advisory_unlock(7272741)"))
                lock.close()

    def dispose(self):
        self.engine.dispose()
