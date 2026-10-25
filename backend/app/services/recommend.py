"""Personal recommendations from data the shopper actually created: saved preferences, wishlist, recently viewed and past orders.
With no such data it returns nothing (the UI then invites the shopper to set preferences) rather than inventing "picks for you"."""
from sqlalchemy import select

from .. import money
from ..models import OrderItem, Order, Preference, RecentView, WishlistItem


def signals(s, user) -> dict:
    pref = s.get(Preference, user.id)
    wish = [r.product_id for r in s.scalars(select(WishlistItem).where(WishlistItem.user_id == user.id))]
    recent = [r.product_id for r in s.scalars(select(RecentView).where(RecentView.user_id == user.id).order_by(RecentView.viewed_at.desc()).limit(12))]
    bought = [r[0] for r in s.execute(select(OrderItem.product_id).join(Order, Order.id == OrderItem.order_id).where(Order.user_id == user.id, Order.status != "cancelled")) if r[0]]
    return {"pref": pref, "wishlist": wish, "recent": recent, "bought": bought}


def for_user(a, s, user, limit: int = 8) -> dict:
    sig = signals(s, user)
    pref = sig["pref"]
    has_pref = bool(pref and (pref.categories or pref.requirements or pref.budget_max_paise))
    seeds = [a.by_id[i] for i in dict.fromkeys(sig["bought"] + sig["wishlist"] + sig["recent"]) if i in a.by_id]
    if not has_pref and not seeds:
        return {"items": [], "enough_data": False, "basis": [], "reason": "Save a few preferences, or save, view or buy something, and Verity will suggest products here."}
    cats = set(pref.categories) if pref else set()
    reqs = set(pref.requirements) if pref else set()
    bmax = pref.budget_max_paise / 100 if pref and pref.budget_max_paise else None
    bmin = pref.budget_min_paise / 100 if pref and pref.budget_min_paise else None
    seed_sub = {p.subcategory for p in seeds if p.subcategory}
    seed_tags = {t for p in seeds for t in p.use_cases}
    owned = set(sig["bought"]) | set(sig["wishlist"])
    out = []
    for p in a.products:
        if p.id in owned or p.stock != "in_stock" or p.price is None:
            continue
        if bmax is not None and p.price > bmax or bmin is not None and p.price < bmin:
            continue
        score, why = 0.0, []
        if p.category in cats:
            score += 3
            why.append(f"In {p.category}, a category you chose")
        if p.subcategory in seed_sub:
            score += 2
            why.append(f"Similar to {p.subcategory.lower()} you've saved, viewed or bought")
        shared = (set(p.use_cases) & reqs)
        if shared:
            score += 2 * len(shared)
            why.append("Suits " + ", ".join(sorted(shared)) + " (your saved needs)")
        elif set(p.use_cases) & seed_tags:
            score += 0.7
            why.append("Shares uses with products you've looked at")
        if bmax is not None and score:
            why.append(f"Within your {money.text(money.to_paise(bmax))} budget")
        if score > 0 and p.rating:
            score += max(0, (p.rating - 3.5)) * .4
        if score > 0:
            out.append((score, p, why))
    out.sort(key=lambda x: (-x[0], x[1].price, x[1].id))
    basis = [b for b, ok in (("your saved preferences", has_pref), ("items you saved, viewed or bought", bool(seeds))) if ok]
    return {"items": [{"id": p.id, "reasons": why} for _, p, why in out[:limit]], "enough_data": True, "basis": basis,
            "reason": "" if out else "Nothing in stock matches your saved preferences right now."}
