"""Public catalogue API: health, meta, browse, product detail, compare, home sections, policies, price history, value lens."""
import datetime as dt
from collections import Counter, defaultdict

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from .. import config, money, store
from ..http import assistant, cfg, db, error, ext, pagination
from ..models import Order, OrderItem, Product, utcnow
from ..services import compare as compare_svc
from ..services import valuelens

bp = Blueprint("catalog", __name__)
MAX_COMPARE = compare_svc.MAX_COMPARE
COLLECTION_TITLES = {"study": "Study essentials", "commute": "Commute carry", "travel": "Travel light", "gym": "Gym ready", "running": "Run day", "office": "Desk and office",
                     "home": "Around the house", "cooking": "In the kitchen", "gifting": "Gift ideas", "yoga": "Yoga and stretch", "outdoor": "Outdoors",
                     "casual": "Everyday casual", "formal": "Work formal", "monsoon": "Monsoon ready", "daily": "Daily care"}


def _opt(p, key):
    v = p.attributes.get(key.capitalize()) or p.attributes.get(key) or ""
    return [x.strip() for x in v.split(",") if x.strip()] if v else []


def facets(a):
    f = getattr(a, "_facets", None)
    if f:
        return f
    cats, subs = Counter(), defaultdict(Counter)
    for p in a.products:
        if p.category:
            cats[p.category] += 1
            if p.subcategory:
                subs[p.category][p.subcategory] += 1
    prices = [p.price for p in a.products if p.price is not None]
    tags = Counter(t for p in a.products for t in p.use_cases)
    a._facets = f = {
        "categories": [{"name": c, "count": n, "subcategories": [{"name": s, "count": k} for s, k in sorted(subs[c].items())]} for c, n in sorted(cats.items())],
        "brands": sorted({p.brand for p in a.products if p.brand}),
        "colours": sorted({c for p in a.products for c in _opt(p, "colour")}),
        "sizes": sorted({c for p in a.products for c in _opt(p, "size")}, key=lambda x: (len(x), x)),
        "price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
        "collections": [{"tag": t, "title": COLLECTION_TITLES.get(t, t.title()), "count": n} for t, n in tags.most_common() if n >= 3]}
    return f


def rows_for(ids: list[str]) -> list[Product]:
    if not ids:
        return []
    got = {r.id: r for r in db().scalars(select(Product).where(Product.id.in_(ids))).unique()}
    return [got[i] for i in ids if i in got]


def card_list(prods) -> list[dict]:
    return [store.serialize(r) for r in rows_for([p.id for p in prods])]


@bp.get("/api/health")
def health():
    rt = ext().runtime
    a = rt.assistant()
    return {"status": "ok", "data_source": rt.source, "synthetic_data": rt.source in store.SYNTHETIC_SOURCES, "products": len(a.products), "policy_sections": len(rt.sections),
            "llm": bool(config.GROQ_API_KEY), "database": ext().db.ping(), "database_kind": ext().db.kind, "environment": cfg("APP_ENV"), "version": "2.0"}


@bp.get("/api/meta")
def meta():
    rt = ext().runtime
    a = rt.assistant()
    f = facets(a)
    return {"data_source": rt.source, "synthetic_data": rt.source in store.SYNTHETIC_SOURCES, "products": len(a.products), "llm": bool(config.GROQ_API_KEY), "logging": cfg("LOG_CHATS"),
            "categories": [{"name": c["name"], "count": c["count"], "subcategories": c["subcategories"]} for c in f["categories"]],
            "brands": f["brands"], "colours": f["colours"], "sizes": f["sizes"], "collections": f["collections"],
            "price_min": f["price_min"], "price_max": f["price_max"], "policy_sections": [{"id": s.id, "title": s.title} for s in rt.sections], "max_compare": MAX_COMPARE,
            "max_message_chars": cfg("MAX_MESSAGE_CHARS"),
            "commerce": {"currency": "INR", "shipping_fee": cfg("SHIPPING_FEE_RUPEES"), "free_shipping_above": cfg("FREE_SHIPPING_ABOVE_RUPEES"), "max_qty": cfg("MAX_QTY_PER_LINE"),
                         "checkout_enabled": bool(cfg("CHECKOUT_ENABLED")), "checkout": "demo" if cfg("CHECKOUT_ENABLED") else "disabled",
                         "checkout_note": "Checkout is disabled in this demo. Nothing is purchased and no payment details are requested."}}


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _multi(name):
    return {x.strip().lower() for v in request.args.getlist(name) for x in v.split(",") if x.strip()}


@bp.get("/api/products")
def browse():
    a, args = assistant(), request.args
    items = a.products
    ids = [i for i in args.get("ids", "").split(",") if i][:24]
    if ids:
        items = [a.by_id[i] for i in dict.fromkeys(ids) if i in a.by_id]
    q = args.get("q", "").strip()[:100]
    toks = a.tok(q) if q else []
    if toks:                                   # a query made only of filler words is ignored rather than matching nothing
        items = [a.products[i] for i, _, cov in a.index.search(toks, 2000) if cov >= 0.6 and (not ids or a.products[i] in items)]
    if args.get("category"):
        items = [p for p in items if p.category == args["category"]]
    if args.get("subcategory"):
        items = [p for p in items if p.subcategory == args["subcategory"]]
    brands, colours, sizes = _multi("brand"), _multi("colour"), _multi("size")
    if brands:
        items = [p for p in items if p.brand.lower() in brands]
    if colours:
        items = [p for p in items if colours & {c.lower() for c in _opt(p, "colour")}]
    if sizes:
        items = [p for p in items if sizes & {c.lower() for c in _opt(p, "size")}]
    if args.get("use"):
        items = [p for p in items if args["use"].lower() in p.use_cases]
    if args.get("featured") == "1":
        items = [p for p in items if p.featured]
    if args.get("in_stock") == "1":
        items = [p for p in items if p.stock == "in_stock"]
    mx, mn, mr = _num(args.get("max_price")), _num(args.get("min_price")), _num(args.get("min_rating"))
    if mx is not None:
        items = [p for p in items if p.price is not None and p.price <= mx]
    if mn is not None:
        items = [p for p in items if p.price is not None and p.price >= mn]
    if mr is not None:
        items = [p for p in items if p.rating is not None and p.rating >= mr]
    sort = args.get("sort", "")
    if sort == "price_asc":
        items = sorted(items, key=lambda p: (p.price is None, p.price or 0))
    elif sort == "price_desc":
        items = sorted(items, key=lambda p: (p.price is None, -(p.price or 0)))
    elif sort == "rating":
        items = sorted(items, key=lambda p: (p.rating is None, -(p.rating or 0)))
    elif sort == "newest":
        items = sorted(items, key=lambda p: p.created_at or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    elif sort == "name":
        items = sorted(items, key=lambda p: p.title.lower())
    page, size = pagination(12, 48)
    pages = max(1, -(-len(items) // size))
    page = min(page, pages)
    chunk = items[(page - 1) * size: page * size]
    return {"total": len(items), "page": page, "pages": pages, "page_size": size, "categories": [c["name"] for c in facets(a)["categories"]], "items": card_list(chunk)}


def related(a, p, limit=6):
    scored = []
    for q in a.products:
        if q.id == p.id or q.stock == "out_of_stock":
            continue
        shared = set(p.use_cases) & set(q.use_cases)
        s = (3 if p.subcategory and q.subcategory == p.subcategory else 0) + 1.5 * len(shared) + (1 if q.category == p.category else 0) + (.5 if p.brand and q.brand == p.brand else 0)
        if s >= 1.5:
            why = "Same type" if p.subcategory and q.subcategory == p.subcategory else ("Suits " + ", ".join(sorted(shared)[:2]) if shared else "Same category")
            scored.append((s, q, why))
    scored.sort(key=lambda x: (-x[0], x[1].id))
    return scored[:limit]


@bp.get("/api/products/<pid>")
def product(pid):
    a = assistant()
    row = db().get(Product, pid)
    if row is None or not row.is_active:
        return error(404, "not_found", "That product ID is not in the catalogue.")
    d = store.serialize(row, detail=True)
    p = a.by_id.get(pid)
    rel = related(a, p) if p else []
    rows = {r.id: r for r in rows_for([q.id for _, q, _ in rel])}
    d["related"] = [store.serialize(rows[q.id]) | {"related_reason": why} for _, q, why in rel if q.id in rows]
    pol = [{"id": s.id, "title": s.title, "text": s.text} for s in ext().runtime.sections if any(w in s.title.lower() for w in ("return", "shipping", "warranty", "cancel"))]
    d["policies"] = pol
    return d


@bp.get("/api/products/<pid>/price-history")
def price_history(pid):
    if db().get(Product, pid) is None:
        return error(404, "not_found", "That product ID is not in the catalogue.")
    return store.price_history(db(), pid)


@bp.get("/api/products/<pid>/value-lens")
def value_lens(pid):
    a = assistant()
    p = a.by_id.get(pid)
    if not p:
        return error(404, "not_found", "That product ID is not in the catalogue.")
    return valuelens.lens(a, p, store.price_history(db(), pid), _num(request.args.get("budget")), request.args.get("need", "")[:300])


@bp.get("/api/policies")
def policies():
    return {"sections": [{"id": s.id, "title": s.title, "text": s.text} for s in ext().runtime.sections], "source": ext().runtime.source}


def _weights(raw: str) -> dict:
    out = {}
    for part in raw.split(","):
        k, _, v = part.partition(":")
        if k.strip() and v.strip():
            out[k.strip()] = v.strip()
    return out


@bp.get("/api/compare")
def compare():
    a = assistant()
    ids = list(dict.fromkeys(i for i in request.args.get("ids", "").split(",") if i))
    if len(ids) < 2 or len(ids) > MAX_COMPARE:
        return error(400, "invalid_request", f"Choose between 2 and {MAX_COMPARE} products to compare.")
    missing = [i for i in ids if i not in a.by_id]
    if missing:
        return error(404, "not_found", f"Not in the catalogue: {', '.join(missing[:5])}")
    prods = [a.by_id[i] for i in ids]
    rows = {r.id: r for r in rows_for(ids)}
    return {"products": [a.full_record(p) | {"brand": p.brand, "images": p.images} for p in prods], "comparison": a.comparison_table(prods),
            "cards": [store.serialize(rows[i]) for i in ids if i in rows],
            "studio": compare_svc.studio(a, prods, _weights(request.args.get("weights", "")), request.args.get("use_case", ""))}


@bp.get("/api/home")
def home():
    a = assistant()
    s = db()
    feats = [p for p in a.products if p.featured and p.stock != "out_of_stock"][:8]
    now = utcnow()
    new = sorted((p for p in a.products if p.created_at and (now - p.created_at).days <= 30 and p.data_origin != "catalogue"), key=lambda p: p.created_at, reverse=True)[:8]
    since = now - dt.timedelta(days=30)
    qty, demo_seen = Counter(), False
    for oi, o in s.execute(select(OrderItem, Order).join(Order, Order.id == OrderItem.order_id).where(Order.status != "cancelled", Order.created_at >= since)):
        if oi.product_id in a.by_id:
            qty[oi.product_id] += oi.quantity
            demo_seen = demo_seen or o.is_demo
    trending = [a.by_id[i] for i, _ in qty.most_common(8)] if len(qty) >= 3 else []
    f = facets(a)
    cols = []
    for c in f["collections"][:6]:
        prods = [p for p in a.products if c["tag"] in p.use_cases and p.stock != "out_of_stock"][:4]
        cols.append({**c, "products": card_list(prods)})
    return {"featured": card_list(feats), "new_arrivals": card_list(new), "trending": card_list(trending),
            "trending_basis": "Most-ordered items in the last 30 days, from recorded orders" + (" (includes demo-seeded orders)." if demo_seen else ".") if trending else "",
            "collections": cols, "categories": [{"name": c["name"], "count": c["count"], "image": next((p.image for p in a.products if p.category == c["name"] and p.image and p.stock == "in_stock"), None)}
                                                 for c in f["categories"]]}
