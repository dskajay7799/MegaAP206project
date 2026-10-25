import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.models import Base  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    from backend.app import config as app_config
    return config.get_main_option("sqlalchemy.url") or app_config.normalise_db_url(os.getenv("DATABASE_URL", ""))


def run_migrations_offline():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(_url().replace("%%", "%"), poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
