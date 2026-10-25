"""Dashboard numbers computed from stored rows only. Empty database -> zeros and empty series, never invented growth."""
import datetime as dt
from collections import Counter, defaultdict

from sqlalchemy import func, select

from .. import money, store
from ..models import ChatLog, Feedback, Order, OrderItem, Product, User, Variant, utcnow
from . import orders as orders_svc


def customer_spending(s, user) -> dict:
    rows = s.scalars(select(Order).where(Order.user_id == user.id, Order.status != "cancelled").order_by(Order.created_at)).all()
    by_month, by_cat = defaultdict(int), defaultdict(int)
    for o in rows:
        by_month[o.created_at.strftime("%Y-%m")] += o.total_paise
        for it in o.items:
            by_cat[it.category or "Other"] += it.line_total_paise
    total = sum(by_month.values())
    return {"order_count": len(rows), "total": total / 100, "total_text": money.text(total), "average_text": money.text(total // len(rows)) if rows else money.text(0),
            "by_month": [{"label": k, "value": v / 100, "text": money.text(v)} for k, v in sorted(by_month.items())],
            "by_category": [{"label": k, "value": v / 100, "text": money.text(v)} for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])],
            "note": "Computed from your own non-cancelled orders."}


def admin_summary(s, include_demo: bool = True) -> dict:
    oq = select(Order)
    if not include_demo:
        oq = oq.where(Order.is_demo.is_(False))
    orders = s.scalars(oq).all()
    live = [o for o in orders if o.status != "cancelled"]
    delivered = [o for o in orders if o.status == "delivered"]
    uq = select(func.count()).select_from(User).where(User.role == "customer")
    if not include_demo:
        uq = uq.where(User.is_demo.is_(False))
    products = s.scalars(select(Product)).unique().all()
    active = [p for p in products if p.is_active]
    low, out, untracked = [], 0, 0
    for p in active:
        status, qty = store.stock_info(p)
        if status == "out_of_stock":
            out += 1
        elif qty is None:
            untracked += 1
        elif qty <= store.LOW_STOCK:
            low.append({"id": p.id, "title": p.title, "stock_qty": qty})
    demo_orders = sum(1 for o in orders if o.is_demo)
    return {
        "orders": {"total": len(orders), "active": len(live), "cancelled": len(orders) - len(live)},
        "order_value": {"value": sum(o.total_paise for o in live) / 100, "text": money.text(sum(o.total_paise for o in live)),
                        "rule": "Sum of order totals for all orders that are not cancelled."},
        "revenue": {"value": sum(o.total_paise for o in delivered) / 100, "text": money.text(sum(o.total_paise for o in delivered)),
                    "rule": "Sum of order totals for delivered orders only."},
        "customers": s.scalar(uq) or 0, "products": {"active": len(active), "inactive": len(products) - len(active)},
        "inventory": {"out_of_stock": out, "low_stock": len(low), "untracked": untracked, "low_items": sorted(low, key=lambda x: x["stock_qty"])[:10]},
        "demo": {"orders": demo_orders, "included": include_demo, "note": f"{demo_orders} of these orders were created by the demo seeder." if demo_orders else ""},
    }


def admin_charts(s, include_demo: bool = True, days: int = 30) -> dict:
    now = utcnow()
    start = (now - dt.timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    oq = select(Order)
    if not include_demo:
        oq = oq.where(Order.is_demo.is_(False))
    orders = s.scalars(oq).all()
    daily = {(start + dt.timedelta(days=i)).strftime("%Y-%m-%d"): [0, 0] for i in range(days)}
    for o in orders:
        d = o.created_at.strftime("%Y-%m-%d")
        if o.status != "cancelled" and d in daily:
            daily[d][0] += 1
            daily[d][1] += o.total_paise
    status = Counter(o.status for o in orders)
    cat_rev, prod_qty = defaultdict(int), Counter()
    titles = {}
    for o in orders:
        if o.status == "cancelled":
            continue
        for it in o.items:
            cat_rev[it.category or "Other"] += it.line_total_paise
            prod_qty[it.product_id or it.title] += it.quantity
            titles[it.product_id or it.title] = it.title
    products = s.scalars(select(Product).where(Product.is_active.is_(True))).unique().all()
    cat_count = Counter(p.category.name if p.category else "Uncategorised" for p in products)
    buckets = Counter()
    for p in products:
        st, qty = store.stock_info(p)
        buckets["Out of stock" if st == "out_of_stock" else "Not tracked" if qty is None else "Low (1–5)" if qty <= 5 else "Healthy (6–20)" if qty <= 20 else "High (21+)"] += 1
    weeks = defaultdict(int)
    for u in s.scalars(select(User).where(User.role == "customer", *([] if include_demo else [User.is_demo.is_(False)]))).all():
        weeks[(u.created_at - dt.timedelta(days=u.created_at.weekday())).strftime("%Y-%m-%d")] += 1
    return {
        "sales": [{"date": d, "orders": v[0], "value": v[1] / 100, "text": money.text(v[1])} for d, v in daily.items()],
        "orders_by_status": [{"label": orders_svc.STATUS_LABEL[k], "key": k, "value": status.get(k, 0)} for k in orders_svc.STATUSES],
        "category_distribution": [{"label": k, "value": v} for k, v in cat_count.most_common()],
        "category_revenue": [{"label": k, "value": v / 100, "text": money.text(v)} for k, v in sorted(cat_rev.items(), key=lambda kv: -kv[1])],
        "top_products": [{"id": k, "label": titles[k], "value": q} for k, q in prod_qty.most_common(8)],
        "stock_distribution": [{"label": k, "value": buckets.get(k, 0)} for k in ("Out of stock", "Low (1–5)", "Healthy (6–20)", "High (21+)", "Not tracked")],
        "signups_by_week": [{"label": k, "value": v} for k, v in sorted(weeks.items())][-8:],
        "include_demo": include_demo,
    }


def ai_stats(s) -> dict:
    rows = s.execute(select(ChatLog.status, func.count(), func.avg(ChatLog.latency_ms), func.coalesce(func.sum(ChatLog.tokens), 0)).group_by(ChatLog.status)).all()
    gaps = s.execute(select(ChatLog.message, func.count()).where(ChatLog.status.in_(["no_match", "refused"])).group_by(ChatLog.message).order_by(func.count().desc()).limit(10)).all()
    up = s.scalar(select(func.count()).select_from(Feedback).where(Feedback.helpful.is_(True))) or 0
    total = s.scalar(select(func.count()).select_from(Feedback)) or 0
    return {"by_status": [{"status": a, "count": n, "avg_latency_ms": round(float(l or 0), 1), "tokens": int(t)} for a, n, l, t in rows],
            "top_unanswered": [{"message": m, "count": n} for m, n in gaps], "feedback": {"helpful": up, "total": total}}
