"""Administrator API. Every route is protected on the server by role; hiding buttons in the UI is not what secures this."""
import re

from flask import Blueprint, jsonify, request
from sqlalchemy import func, or_, select, text

from .. import catalogue, config, money, security, store
from ..http import body, cfg, db, error, ext, pagination
from ..models import Category, Feedback, Order, Product, User, Variant, utcnow
from ..security import admin_required
from ..services import analytics, cart as cart_svc, orders as orders_svc

bp = Blueprint("admin", __name__)
ID_RE, KEY_RE, TAG_RE = re.compile(r"^[A-Za-z0-9._-]{2,40}$"), re.compile(r"^[a-z][a-z0-9_]{1,40}$"), re.compile(r"^[a-z][a-z-]{1,19}$")


def _demo_flag():
    return request.args.get("include_demo", "1") != "0"


@bp.get("/api/admin/summary")
@admin_required
def summary():
    return jsonify(analytics.admin_summary(db(), _demo_flag()))


@bp.get("/api/admin/charts")
@admin_required
def charts():
    try:
        days = max(7, min(90, int(request.args.get("days", 30))))
    except ValueError:
        days = 30
    return jsonify(analytics.admin_charts(db(), _demo_flag(), days))


# ------------------------------------------------------------ products
def _admin_product(row: Product) -> dict:
    d = store.serialize(row, detail=True)
    d.update({"raw_attributes": row.attributes or {}, "specs_raw": row.specs or {}, "stock_qty_raw": row.stock_qty, "stock_status": row.stock_status, "is_active": row.is_active, "sku": row.sku,
              "mrp": money.to_rupees(row.mrp_paise), "updated_at": row.updated_at.isoformat() if row.updated_at else None})
    return d


@bp.get("/api/admin/products")
@admin_required
def products():
    s, args = db(), request.args
    q = select(Product)
    if args.get("q"):
        like = f"%{args['q'].strip()[:80]}%"
        q = q.where(or_(Product.title.ilike(like), Product.id.ilike(like), Product.brand.ilike(like), Product.sku.ilike(like)))
    if args.get("category"):
        q = q.join(Category, Category.id == Product.category_id).where(Category.name == args["category"])
    if args.get("status") == "inactive":
        q = q.where(Product.is_active.is_(False))
    elif args.get("status") == "active":
        q = q.where(Product.is_active.is_(True))
    rows = s.scalars(q.order_by(Product.id)).unique().all()
    if args.get("stock") in ("low", "out"):
        rows = [r for r in rows if (store.stock_info(r)[0] == "out_of_stock" if args["stock"] == "out" else (store.stock_info(r)[1] is not None and 0 < store.stock_info(r)[1] <= store.LOW_STOCK))]
    page, size = pagination(20, 100)
    return jsonify({"items": [_admin_product(r) for r in rows[(page - 1) * size: page * size]], "total": len(rows), "page": page, "pages": max(1, -(-len(rows) // size))})


@bp.get("/api/admin/products/<pid>")
@admin_required
def product_get(pid):
    r = db().get(Product, pid)
    return jsonify(_admin_product(r)) if r else error(404, "not_found", "Product not found.")


def _clean_product(b: dict, creating: bool) -> tuple[dict, dict]:
    err, c = {}, {}
    if creating:
        c["id"] = str(b.get("id", "")).strip()
        if not ID_RE.match(c["id"]):
            err["id"] = "Use 2–40 letters, numbers, dots, dashes or underscores."
    if "title" in b or creating:
        c["title"] = " ".join(str(b.get("title", "")).split())
        if not 2 <= len(c["title"]) <= 200:
            err["title"] = "Enter a title (2–200 characters)."
    for k, n in (("brand", 80), ("subcategory", 80), ("sku", 64)):
        if k in b:
            c[k] = " ".join(str(b[k] or "").split())[:n]
    if "description" in b:
        c["description"] = str(b["description"] or "")[:2000]
    if "category" in b:
        c["category"] = " ".join(str(b["category"] or "").split())[:80]
        if creating and not c["category"]:
            err["category"] = "Choose a category."
    if "price" in b or creating:
        try:
            c["price_paise"] = money.to_paise(b["price"])
            if c["price_paise"] is None or not 0 <= c["price_paise"] <= 10_000_000_00:
                raise ValueError
        except Exception:
            err["price"] = "Enter a price in rupees (0 to 1,00,00,000)."
    if "mrp" in b:
        try:
            c["mrp_paise"] = money.to_paise(b["mrp"]) if b["mrp"] not in (None, "") else None
        except Exception:
            err["mrp"] = "Enter a number or leave blank."
    if "rating" in b:
        try:
            r = float(b["rating"]) if b["rating"] not in (None, "") else None
            if r is not None and not 0 <= r <= 5:
                raise ValueError
            c["rating"] = r
        except (TypeError, ValueError):
            err["rating"] = "Rating must be between 0 and 5, or blank."
    if "stock_qty" in b:
        v = b["stock_qty"]
        if v in (None, ""):
            c["stock_qty"] = None
        elif isinstance(v, bool) or not str(v).lstrip("-").isdigit() or int(v) < 0 or int(v) > 1_000_000:
            err["stock_qty"] = "Stock must be a whole number of 0 or more."
        else:
            c["stock_qty"] = int(v)
    if "specs" in b:
        sp = b["specs"] if isinstance(b["specs"], dict) else {}
        if len(sp) > 30 or any(not KEY_RE.match(str(k)) or not (isinstance(v, (bool, str)) or (isinstance(v, (int, float)))) or (isinstance(v, str) and len(v) > 80) for k, v in sp.items()):
            err["specs"] = "Spec keys must be lowercase_with_underscores; values numbers, yes/no or short text."
        else:
            c["specs"] = sp
    if "attributes" in b:
        at = b["attributes"] if isinstance(b["attributes"], dict) else {}
        c["attributes"] = {str(k)[:40]: str(v)[:120] for k, v in list(at.items())[:20]}
    if "highlights" in b:
        c["highlights"] = [str(x)[:120] for x in (b["highlights"] if isinstance(b["highlights"], list) else [])][:8]
    if "use_cases" in b:
        tags = [str(x).strip().lower() for x in (b["use_cases"] if isinstance(b["use_cases"], list) else [])]
        if any(not TAG_RE.match(t) for t in tags):
            err["use_cases"] = "Use short lowercase words such as study, gym or travel."
        c["use_cases"] = list(dict.fromkeys(tags))[:10]
    if "images" in b:
        imgs = b["images"] if isinstance(b["images"], list) else []
        bad = [i for i in imgs if not catalogue.safe_image(i)]
        if bad or len(imgs) > 8:
            err["images"] = "Images must be https:// URLs or bundled /assets/ paths (max 8)."
        else:
            c["images"] = imgs
    for k in ("featured", "is_active"):
        if k in b:
            c[k] = bool(b[k])
    return c, err


def _apply_variants(s, row: Product, raw):
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) > 60:
        return "Variants must be a list of up to 60 items."
    existing = {v.sku: v for v in row.variants}
    seen = set()
    for v in raw:
        if not isinstance(v, dict) or not isinstance(v.get("options"), dict) or not v["options"]:
            return "Each variant needs options such as {\"size\": \"M\"}."
        sku = str(v.get("sku") or "").strip() or f"{row.sku or row.id}-{len(seen) + 1}"
        if sku in seen:
            return f"Duplicate variant SKU {sku}."
        seen.add(sku)
        try:
            qty = int(v.get("stock_qty", 0))
            delta = money.to_paise(v.get("price_delta", 0)) or 0
        except (TypeError, ValueError):
            return "Variant stock must be a whole number."
        if qty < 0:
            return "Variant stock can't be negative."
        opts = {str(k)[:30]: str(x)[:40] for k, x in v["options"].items()}
        if sku in existing:
            ex = existing[sku]
            ex.options, ex.stock_qty, ex.price_delta_paise, ex.is_active = opts, qty, delta, True
        else:
            if s.scalar(select(Variant.id).where(Variant.sku == sku)):
                return f"Variant SKU {sku} is already used by another product."
            row.variants.append(Variant(sku=sku, options=opts, stock_qty=qty, price_delta_paise=delta))
    for sku, ex in existing.items():
        if sku not in seen:
            row.variants.remove(ex)
            s.delete(ex)
    return None


def _category(s, name: str) -> Category | None:
    if not name:
        return None
    c = s.scalar(select(Category).where(Category.name == name))
    if not c:
        c = Category(name=name, sort_order=(s.scalar(select(func.max(Category.sort_order))) or 0) + 1)
        s.add(c)
        s.flush()
    return c


@bp.post("/api/admin/products")
@admin_required
def product_create():
    b, s = body(), db()
    c, err = _clean_product(b, True)
    if not err and s.get(Product, c["id"]):
        err["id"] = "That product ID already exists."
    if err:
        return error(422, "validation_failed", "Check the highlighted fields.", fields=err)
    cat_name = c.pop("category", "")
    row = Product(**{k: v for k, v in c.items()}, data_origin="admin")
    row.category = _category(s, cat_name)
    row.stock_status = "in_stock" if (c.get("stock_qty") or 0) > 0 else "out_of_stock"
    s.add(row)
    s.flush()
    problem = _apply_variants(s, row, b.get("variants"))
    if problem:
        s.rollback()
        return error(422, "validation_failed", problem, fields={"variants": problem})
    store.record_price(s, row, "admin")
    store.bump_version(s)
    s.commit()
    return jsonify(_admin_product(row)), 201


@bp.put("/api/admin/products/<pid>")
@admin_required
def product_update(pid):
    b, s = body(), db()
    row = s.get(Product, pid)
    if row is None:
        return error(404, "not_found", "Product not found.")
    c, err = _clean_product(b, False)
    if err:
        return error(422, "validation_failed", "Check the highlighted fields.", fields=err)
    old_price = row.price_paise
    if "category" in c:
        row.category = _category(s, c.pop("category"))
    for k, v in c.items():
        setattr(row, k, v)
    if "stock_qty" in c and c["stock_qty"] is not None:
        row.stock_status = "in_stock" if c["stock_qty"] > 0 else "out_of_stock"
    problem = _apply_variants(s, row, b.get("variants"))
    if problem:
        s.rollback()
        return error(422, "validation_failed", problem, fields={"variants": problem})
    if row.price_paise != old_price:
        store.record_price(s, row, "admin")
    row.updated_at = utcnow()
    store.bump_version(s)
    s.commit()
    return jsonify(_admin_product(row))


@bp.patch("/api/admin/products/<pid>/inventory")
@admin_required
def inventory(pid):
    b, s = body(), db()
    row = s.get(Product, pid)
    if row is None:
        return error(404, "not_found", "Product not found.")
    try:
        if store.active_variants(row):
            for v in b.get("variants", []):
                var = next((x for x in row.variants if x.id == int(v["id"])), None)
                if var is None or int(v["stock_qty"]) < 0:
                    raise ValueError
                var.stock_qty = int(v["stock_qty"])
        else:
            q = int(b["stock_qty"])
            if q < 0:
                raise ValueError
            row.stock_qty = q
            row.stock_status = "in_stock" if q > 0 else "out_of_stock"
    except (KeyError, TypeError, ValueError):
        return error(422, "validation_failed", "Stock must be whole numbers of 0 or more for this product's own variants.")
    store.bump_version(s)
    s.commit()
    return jsonify(_admin_product(row))


@bp.patch("/api/admin/products/<pid>/price")
@admin_required
def price(pid):
    s = db()
    row = s.get(Product, pid)
    if row is None:
        return error(404, "not_found", "Product not found.")
    try:
        p = money.to_paise(body().get("price"))
        if p is None or p < 0:
            raise ValueError
    except Exception:
        return error(422, "validation_failed", "Enter a price in rupees.")
    if p != row.price_paise:
        row.price_paise = p
        store.record_price(s, row, "admin")
        store.bump_version(s)
        s.commit()
    return jsonify(_admin_product(row))


@bp.delete("/api/admin/products/<pid>")
@admin_required
def product_delete(pid):
    s = db()
    row = s.get(Product, pid)
    if row is None:
        return error(404, "not_found", "Product not found.")
    s.delete(row)
    store.bump_version(s)
    s.commit()
    return "", 204


# ------------------------------------------------------------ categories
@bp.get("/api/admin/categories")
@admin_required
def categories():
    s = db()
    counts = dict(s.execute(select(Product.category_id, func.count()).group_by(Product.category_id)).all())
    return jsonify({"items": [{"id": c.id, "name": c.name, "description": c.description, "products": counts.get(c.id, 0)} for c in s.scalars(select(Category).order_by(Category.sort_order, Category.name))]})


@bp.post("/api/admin/categories")
@admin_required
def category_create():
    b, s = body(), db()
    name = " ".join(str(b.get("name", "")).split())
    if not 2 <= len(name) <= 80:
        return error(422, "validation_failed", "Enter a category name (2–80 characters).", fields={"name": "Required."})
    if s.scalar(select(Category.id).where(func.lower(Category.name) == name.lower())):
        return error(409, "exists", "That category already exists.", fields={"name": "Already exists."})
    c = Category(name=name, description=str(b.get("description", ""))[:300], sort_order=(s.scalar(select(func.max(Category.sort_order))) or 0) + 1)
    s.add(c)
    s.commit()
    return jsonify({"id": c.id, "name": c.name, "description": c.description, "products": 0}), 201


@bp.put("/api/admin/categories/<int:cid>")
@admin_required
def category_update(cid):
    b, s = body(), db()
    c = s.get(Category, cid)
    if c is None:
        return error(404, "not_found", "Category not found.")
    name = " ".join(str(b.get("name", c.name)).split())
    if not 2 <= len(name) <= 80:
        return error(422, "validation_failed", "Enter a category name (2–80 characters).", fields={"name": "Required."})
    if s.scalar(select(Category.id).where(func.lower(Category.name) == name.lower(), Category.id != cid)):
        return error(409, "exists", "That category already exists.", fields={"name": "Already exists."})
    c.name, c.description = name, str(b.get("description", c.description))[:300]
    store.bump_version(s)
    s.commit()
    return jsonify({"id": c.id, "name": c.name, "description": c.description})


@bp.delete("/api/admin/categories/<int:cid>")
@admin_required
def category_delete(cid):
    s = db()
    c = s.get(Category, cid)
    if c is None:
        return error(404, "not_found", "Category not found.")
    if s.scalar(select(func.count()).select_from(Product).where(Product.category_id == cid)):
        return error(409, "in_use", "Move or delete this category's products first.")
    s.delete(c)
    s.commit()
    return "", 204


# ------------------------------------------------------------ orders / customers
def _admin_order(o: Order) -> dict:
    d = orders_svc.serialize(o, admin=True)
    return d


@bp.get("/api/admin/orders")
@admin_required
def orders():
    s, args = db(), request.args
    q = select(Order)
    if args.get("status") in orders_svc.STATUSES:
        q = q.where(Order.status == args["status"])
    if args.get("q"):
        like = f"%{args['q'].strip()[:60]}%"
        q = q.where(or_(Order.order_number.ilike(like), Order.contact_email.ilike(like), Order.ship_name.ilike(like)))
    if args.get("include_demo") == "0":
        q = q.where(Order.is_demo.is_(False))
    page, size = pagination(20, 100)
    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = s.scalars(q.order_by(Order.created_at.desc(), Order.id.desc()).offset((page - 1) * size).limit(size)).all()
    return jsonify({"items": [_admin_order(o) for o in rows], "total": total, "page": page, "pages": max(1, -(-total // size))})


@bp.get("/api/admin/orders/<number>")
@admin_required
def order_get(number):
    o = db().scalar(select(Order).where(Order.order_number == number))
    return jsonify(_admin_order(o)) if o else error(404, "not_found", "Order not found.")


@bp.patch("/api/admin/orders/<number>/status")
@admin_required
def order_status(number):
    b, s = body(), db()
    o = s.scalar(select(Order).where(Order.order_number == number))
    if o is None:
        return error(404, "not_found", "Order not found.")
    try:
        orders_svc.set_status(s, o, str(b.get("status", "")), "admin", str(b.get("note", ""))[:200])
        s.commit()
    except cart_svc.CartError as e:
        s.rollback()
        return error(e.status, e.code, e.message)
    return jsonify(_admin_order(o))


@bp.get("/api/admin/customers")
@admin_required
def customers():
    s, args = db(), request.args
    q = select(User).where(User.role == "customer")
    if args.get("q"):
        like = f"%{args['q'].strip()[:60]}%"
        q = q.where(or_(User.email.ilike(like), User.name.ilike(like)))
    if args.get("include_demo") == "0":
        q = q.where(User.is_demo.is_(False))
    page, size = pagination(20, 100)
    total = s.scalar(select(func.count()).select_from(q.subquery())) or 0
    users = s.scalars(q.order_by(User.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    stats = {uid: (n, t) for uid, n, t in s.execute(select(Order.user_id, func.count(), func.coalesce(func.sum(Order.total_paise), 0)).where(Order.status != "cancelled").group_by(Order.user_id))}
    return jsonify({"items": [{"id": u.id, "name": u.name, "email": u.email, "joined": u.created_at.isoformat(), "orders": stats.get(u.id, (0, 0))[0],
                               "spent_text": money.text(stats.get(u.id, (0, 0))[1]), "is_demo": u.is_demo} for u in users],
                    "total": total, "page": page, "pages": max(1, -(-total // size)),
                    "note": "Only the details needed to manage orders are shown. Addresses appear on the order itself."})


# ------------------------------------------------------------ service health / AI
@bp.get("/api/admin/health")
@admin_required
def health():
    import time
    s, rt = db(), ext().runtime
    try:
        head = s.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        head = None
    return jsonify({"database": {"ok": ext().db.ping(), "kind": ext().db.kind, "migration": head}, "catalogue": {"source": rt.source, "synthetic": rt.source in store.SYNTHETIC_SOURCES,
                    "products_indexed": len(rt.assistant().products), "version": store.meta_get(s, "catalogue_version")},
                    "ai": {"llm_configured": bool(config.GROQ_API_KEY), "mode": "ai" if config.GROQ_API_KEY else "grounded", "model": config.GROQ_MODEL if config.GROQ_API_KEY else None},
                    "chat_logging": cfg("LOG_CHATS"), "environment": cfg("APP_ENV"), "uptime_seconds": int(time.time() - ext().started),
                    "email_configured": bool(cfg("SMTP_HOST") and cfg("MAIL_FROM"))})


@bp.get("/api/admin/ai")
@admin_required
def ai():
    out = analytics.ai_stats(db())
    out["logging_enabled"] = cfg("LOG_CHATS")
    out["note"] = "" if cfg("LOG_CHATS") else "Question logging is off (LOG_CHATS=0), so there are no usage numbers. Feedback counts need logging too."
    return jsonify(out)
