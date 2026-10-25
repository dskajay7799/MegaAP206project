"""Database-backed catalogue.

* `import_products` seeds the DB from the file source (official R3 data, or the labelled demo store).
* `Runtime` rebuilds the grounded assistant whenever `catalogue_version` changes, so admin edits are immediately what the
  assistant retrieves, cites and verifies against. Multiple gunicorn workers stay consistent because the version lives in the DB.
* `serialize` turns a row into the JSON the storefront renders.
"""
import datetime as dt
import logging
import re
import threading

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import catalogue as cat
from . import money, specs as specs_mod
from .assistant import Assistant
from .models import Category, Meta, PriceObservation, Product, Variant, utcnow

log = logging.getLogger("store")
SYNTHETIC_SOURCES = {"dev-sample", "demo-store"}
LOW_STOCK = 5


# ---------------------------------------------------------------- meta / version
def meta_get(s: Session, key: str, default: str = "") -> str:
    row = s.get(Meta, key)
    return row.value if row else default


def meta_set(s: Session, key: str, value: str):
    row = s.get(Meta, key)
    if row:
        row.value = value
    else:
        s.add(Meta(key=key, value=value))


def bump_version(s: Session):
    meta_set(s, "catalogue_version", str(int(meta_get(s, "catalogue_version", "0") or 0) + 1))


# ---------------------------------------------------------------- stock
def active_variants(row: Product) -> list[Variant]:
    return [v for v in row.variants if v.is_active]


def stock_info(row: Product) -> tuple[str, int | None]:
    """(status, tracked quantity or None). With variants, stock is the sum of the active variants."""
    vs = active_variants(row)
    if vs:
        total = sum(v.stock_qty for v in vs)
        return ("in_stock" if total > 0 else "out_of_stock"), total
    if row.stock_qty is not None:
        return ("in_stock" if row.stock_qty > 0 else "out_of_stock"), row.stock_qty
    return (row.stock_status or "unknown"), None


def variant_label(v: Variant | None) -> str:
    return " / ".join(str(x) for x in (v.options or {}).values()) if v else ""


def unit_price_paise(row: Product, variant: Variant | None = None) -> int | None:
    if row.price_paise is None:
        return None
    return row.price_paise + (variant.price_delta_paise if variant else 0)


# ---------------------------------------------------------------- import
def _category(s: Session, name: str, cache: dict, order: list) -> Category | None:
    if not name:
        return None
    if name not in cache:
        row = s.scalar(select(Category).where(Category.name == name))
        if not row:
            row = Category(name=name, sort_order=len(order))
            s.add(row)
            s.flush()
        cache[name] = row
        order.append(name)
    return cache[name]


def import_products(s: Session, products: list[cat.Product], source: str, *, replace: bool = False):
    now = utcnow()
    if replace:
        for model in (Product, Category):
            for row in s.scalars(select(model)).all():
                s.delete(row)
        s.flush()
    cache, order, seen_skus, obs = {}, [], set(), []
    for p in products:
        c = _category(s, p.category, cache, order)
        created = now - dt.timedelta(days=p.added_days_ago) if p.added_days_ago is not None else now
        row = Product(
            id=p.id, sku=p.sku, title=p.title, brand=p.brand, category=c, subcategory=p.subcategory, description=p.description,
            price_paise=money.to_paise(p.price), mrp_paise=money.to_paise(p.mrp), rating=p.rating, specs=dict(p.specs), attributes=dict(p.raw_attributes),
            highlights=list(p.highlights), use_cases=list(p.use_cases), images=list(p.images), featured=p.featured,
            data_origin=p.data_origin, created_at=created, updated_at=created, stock_status=p.stock)
        vs = cat.expand_options(p)
        if vs:
            for v in vs:
                sku, n = v["sku"], 1
                while sku in seen_skus:
                    n += 1
                    sku = f"{v['sku']}-{n}"
                seen_skus.add(sku)
                row.variants.append(Variant(sku=sku, options=v["options"], stock_qty=v["stock_qty"]))
        elif p.stock_qty is not None:
            row.stock_qty = p.stock_qty
        s.add(row)
        if row.price_paise is not None:
            obs.append(PriceObservation(product_id=p.id, price_paise=row.price_paise, observed_at=created, source="catalogue"))
            for h in p.price_history:       # simulated demo history, labelled as such everywhere it is shown
                price = money.to_paise(h.get("price"))
                if price is not None and isinstance(h.get("days_ago"), int):
                    obs.append(PriceObservation(product_id=p.id, price_paise=price, observed_at=now - dt.timedelta(days=h["days_ago"]), source="simulated-demo"))
    s.flush()                               # products must exist before rows that reference them (no ORM relationship links them)
    s.add_all(obs)
    meta_set(s, "catalogue_source", source)
    bump_version(s)
    s.flush()
    log.info("Imported %d products (source=%s)", len(products), source)


def ensure_catalogue(db, settings: dict):
    """Seed on first run; never swap a real catalogue for a synthetic one; replace synthetic data when real data arrives."""
    products, sections, source = cat.resolve_data(settings["DATA_DIR"], settings["DEV_DATA_DIR"], settings["ALLOW_DEV_DATA"])
    with db.scope() as s:
        n = s.scalar(select(func.count()).select_from(Product)) or 0
        stored = meta_get(s, "catalogue_source")
        if n == 0:
            import_products(s, products, source)
        elif stored != source:
            if stored in SYNTHETIC_SOURCES and source not in SYNTHETIC_SOURCES:
                log.warning("Replacing synthetic catalogue (%s) with %s data; carts and wishlists referencing old products are dropped, orders keep their snapshots.", stored, source)
                import_products(s, products, source, replace=True)
            elif stored not in SYNTHETIC_SOURCES and source in SYNTHETIC_SOURCES:
                log.error("Database holds a %s catalogue but only synthetic data was resolved; keeping the database catalogue.", stored)
                return sections, stored
            else:
                log.warning("Catalogue source changed (%s -> %s). Run `python -m backend.manage reseed-catalogue` to re-import.", stored, source)
                return sections, stored
    return sections, source


# ---------------------------------------------------------------- DB row -> assistant product
def option_lists(row: Product) -> dict[str, list[str]]:
    out: dict[str, list] = {}
    for v in active_variants(row):
        for k, val in (v.options or {}).items():
            if str(val) not in out.setdefault(k, []):
                out[k].append(str(val))
    return out


def to_assistant(row: Product) -> cat.Product:
    status, qty = stock_info(row)
    opts = {k.capitalize(): ", ".join(v) for k, v in option_lists(row).items()}
    attrs = {**specs_mod.display_attributes(row.specs or {}, opts), **(row.attributes or {})}
    return cat.Product(
        id=row.id, title=row.title, description=row.description or "", price=money.to_rupees(row.price_paise), stock=status,
        category=row.category.name if row.category else "", rating=row.rating, attributes=attrs, image=(row.images or [None])[0],
        brand=row.brand or "", subcategory=row.subcategory or "", sku=row.sku or "", specs=dict(row.specs or {}), highlights=list(row.highlights or []),
        use_cases=list(row.use_cases or []), images=list(row.images or []), stock_qty=qty, featured=row.featured, data_origin=row.data_origin, created_at=row.created_at)


class Runtime:
    """Holds the policy sections and a lazily rebuilt Assistant that tracks `catalogue_version`."""

    def __init__(self, db, sections, source: str):
        self.db, self.sections, self.source = db, sections, source
        self._lock = threading.Lock()
        self._version = None
        self._assistant: Assistant | None = None
        self._cats: list[dict] = []

    def _db_version(self) -> str:
        with self.db.engine.connect() as c:
            return c.execute(text("SELECT value FROM meta WHERE key='catalogue_version'")).scalar() or "0"

    def assistant(self) -> Assistant:
        v = self._db_version()
        if self._assistant is None or v != self._version:
            with self._lock:
                if self._assistant is None or v != self._version:
                    with self.db.scope() as s:
                        rows = s.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.id)).unique().all()
                        prods = [to_assistant(r) for r in rows]
                        self.source = meta_get(s, "catalogue_source", self.source)
                    self._assistant = Assistant(prods, self.sections)
                    self._version = v
                    log.info("Assistant index rebuilt: %d products (catalogue_version=%s)", len(prods), v)
        return self._assistant


# ---------------------------------------------------------------- serialisation
def _badges(row: Product, status: str, qty) -> list[dict]:
    out = []
    if status == "out_of_stock":
        out.append({"id": "sold-out", "label": "Sold out"})
    elif qty is not None and 0 < qty <= LOW_STOCK:
        out.append({"id": "low-stock", "label": f"Only {qty} left"})
    if row.created_at and (utcnow() - row.created_at).days <= 30 and row.data_origin != "catalogue":
        out.append({"id": "new", "label": "New"})
    return out


def serialize(row: Product, detail: bool = False) -> dict:
    status, qty = stock_info(row)
    imgs = list(row.images or [])
    d = {
        "id": row.id, "sku": row.sku, "title": row.title, "brand": row.brand or "", "category": row.category.name if row.category else "",
        "subcategory": row.subcategory or "", "price": money.to_rupees(row.price_paise), "price_text": money.text(row.price_paise),
        "mrp_text": money.text(row.mrp_paise) if row.mrp_paise and row.price_paise and row.mrp_paise > row.price_paise else None,
        "stock": status, "stock_text": {"in_stock": "In stock", "out_of_stock": "Out of stock"}.get(status, "Stock not listed"),
        "stock_qty": qty, "rating": row.rating, "rating_is_demo": row.data_origin == "demo",
        "image": imgs[0] if imgs else None, "images": imgs, "featured": row.featured, "use_cases": list(row.use_cases or []),
        "has_variants": bool(active_variants(row)), "data_origin": row.data_origin, "badges": _badges(row, status, qty),
        "attributes": dict(list(to_assistant(row).attributes.items())[:4]),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if detail:
        a = to_assistant(row)
        d.update({
            "description": row.description or "", "attributes": a.attributes, "highlights": list(row.highlights or []),
            "specs": [{"key": k, "label": specs_mod.label(k), "value": v, "display": specs_mod.fmt(k, v), "unit": specs_mod.unit(k),
                       "numeric": specs_mod.is_number(v), "better": specs_mod.better(k)} for k, v in (row.specs or {}).items() if v not in (None, "")],
            "options": option_lists(row),
            "variants": [{"id": v.id, "sku": v.sku, "options": v.options, "label": variant_label(v), "stock_qty": v.stock_qty, "available": v.stock_qty > 0,
                          "price": money.to_rupees(unit_price_paise(row, v)), "price_text": money.text(unit_price_paise(row, v))} for v in active_variants(row)],
            "mrp": money.to_rupees(row.mrp_paise), "is_active": row.is_active,
        })
    return d


# ---------------------------------------------------------------- admin mutations
def record_price(s: Session, row: Product, source: str):
    if row.price_paise is not None:
        s.add(PriceObservation(product_id=row.id, price_paise=row.price_paise, source=source, observed_at=utcnow()))


def price_history(s: Session, pid: str) -> dict:
    obs = s.scalars(select(PriceObservation).where(PriceObservation.product_id == pid).order_by(PriceObservation.observed_at, PriceObservation.id)).all()
    real = [o for o in obs if o.source != "simulated-demo"]
    pts = [{"at": o.observed_at.isoformat(), "price": o.price_paise / 100, "price_text": money.text(o.price_paise), "source": o.source, "simulated": o.source == "simulated-demo"} for o in obs]
    return {"points": pts, "has_simulated": any(p["simulated"] for p in pts), "recorded_count": len(real),
            "enough_recorded": len({o.price_paise for o in real}) >= 2 and len(real) >= 2}
