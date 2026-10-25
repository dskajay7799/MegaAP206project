"""Management commands.   python -m backend.manage <command> [options]

  migrate                         apply database migrations (also run automatically at start-up unless AUTO_MIGRATE=0)
  create-admin --email E          create/promote an administrator; password from --password-env VAR or a hidden prompt
  seed-demo [--orders N]          create clearly flagged DEMO customers + historical orders (synthetic catalogue only, never in production)
  reseed-catalogue --yes          re-import the catalogue files, replacing the stored catalogue (discards admin catalogue edits)
  check-images                    verify every catalogue image: bundled file exists / URL is https
  rebuild-demo-store              regenerate demo_store/ and frontend/assets/products/ (illustrations)
"""
import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from .app import bootstrap, config, store
from .app.database import Database, resolve_url
from .app.models import Product

ROOT = Path(__file__).resolve().parents[1]


def _db(settings):
    url, _ = resolve_url(settings)
    db = Database(url)
    db.migrate()
    store.ensure_catalogue(db, settings)          # idempotent: imports the catalogue only when the database has none
    return db


def _password(args, prompt="Password: ") -> str:
    if args.password_env:
        pw = os.getenv(args.password_env, "")
        if not pw:
            sys.exit(f"Environment variable {args.password_env} is empty.")
        return pw
    pw = getpass.getpass(prompt)
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords did not match.")
    return pw


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--name", default="Store Admin")
    a.add_argument("--password-env", help="read the password from this environment variable (never pass passwords on the command line)")
    d = sub.add_parser("seed-demo")
    d.add_argument("--orders", type=int, default=36)
    d.add_argument("--password-env")
    d.add_argument("--admin-email", help="also create a DEMO administrator with the same password (development only)")
    d.add_argument("--force", action="store_true", help="allow when APP_ENV=production (never on a real store)")
    r = sub.add_parser("reseed-catalogue")
    r.add_argument("--yes", action="store_true")
    sub.add_parser("check-images")
    sub.add_parser("rebuild-demo-store")
    args = ap.parse_args(argv)
    settings = config.load_settings()

    if args.cmd == "rebuild-demo-store":
        return subprocess.call([sys.executable, str(ROOT / "scripts" / "build_demo_store.py")])
    db = _db(settings)
    if args.cmd == "migrate":
        print("Database is up to date.")
    elif args.cmd == "create-admin":
        print(f"Admin {args.email}: {bootstrap.ensure_admin(db, args.email, _password(args), args.name)}")
    elif args.cmd == "seed-demo":
        if settings["PRODUCTION"] and not args.force:
            sys.exit("Refusing to seed demo data when APP_ENV=production.")
        pw = _password(args, "Demo password (used for all demo accounts): ")
        print(bootstrap.seed_demo(db, pw, args.orders, settings=settings))
        if args.admin_email:
            print(f"Demo admin {args.admin_email}: {bootstrap.ensure_admin(db, args.admin_email, pw, 'Demo Admin', demo=True)}")
        print("Demo accounts:", ", ".join(e for _, e in bootstrap.DEMO_USERS))
    elif args.cmd == "reseed-catalogue":
        if not args.yes:
            sys.exit("This replaces the stored catalogue. Re-run with --yes.")
        from .app import catalogue
        products, _, source = catalogue.resolve_data(settings["DATA_DIR"], settings["DEV_DATA_DIR"], settings["ALLOW_DEV_DATA"])
        with db.scope() as s:
            store.import_products(s, products, source, replace=True)
        print(f"Re-imported {len(products)} products from {source}.")
    elif args.cmd == "check-images":
        from .app.catalogue import safe_image
        bad, n = [], 0
        with db.scope() as s:
            for p in s.scalars(select(Product)).unique():
                for img in p.images or []:
                    n += 1
                    if not safe_image(img) or (img.startswith("/assets/") and not (config.FRONTEND_DIR / img.lstrip("/")).exists()):
                        bad.append((p.id, img))
        print(f"{n} images checked, {len(bad)} problems")
        for b in bad[:20]:
            print("  ", *b)
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
