"""Signed-in customer data: profile, addresses, wishlist, recently viewed, saved comparisons/chats, preferences, price watches, dashboard, export, deletion.
Every query is filtered by the current user's id; nothing here accepts a user id from the client."""
import re

from flask import Blueprint, jsonify, request
from sqlalchemy import delete, func, select

from .. import money, security, store
from ..http import assistant, body, db, error
from ..models import (Address, Order, PriceWatch, Preference, Product, RecentView, SavedChat, SavedComparison, User, WishlistItem, utcnow)
from ..security import current_user, login_required
from ..services import analytics, orders as orders_svc, recommend
from .auth import user_dict
from .catalog import card_list, rows_for

bp = Blueprint("account", __name__)
need_login = login_required


def _ser(ids):
    return [store.serialize(r) for r in rows_for(ids)]


@bp.patch("/api/account/profile")
@login_required
def profile():
    b, u = body(), current_user()
    name = " ".join(str(b.get("name", u.name)).split())
    phone = re.sub(r"[\s\-]", "", str(b.get("phone", u.phone) or ""))
    errs = {}
    if not 2 <= len(name) <= 80:
        errs["name"] = "Enter your name (2–80 characters)."
    if phone and not re.fullmatch(r"[6-9]\d{9}", phone):
        errs["phone"] = "Enter a 10-digit Indian mobile number, or leave it blank."
    if errs:
        return error(422, "validation_failed", "Check the highlighted fields.", fields=errs)
    u.name, u.phone = name, phone
    db().commit()
    return jsonify({"user": user_dict(u)})


@bp.get("/api/account/export")
@login_required
def export():
    u, s = current_user(), db()
    data = {"profile": user_dict(u), "addresses": [_addr(a) for a in s.scalars(select(Address).where(Address.user_id == u.id))],
            "orders": [orders_svc.serialize(o) for o in s.scalars(select(Order).where(Order.user_id == u.id).order_by(Order.created_at))],
            "wishlist": [w.product_id for w in s.scalars(select(WishlistItem).where(WishlistItem.user_id == u.id))],
            "preferences": _pref(s.get(Preference, u.id)), "saved_comparisons": [_cmp(c) for c in s.scalars(select(SavedComparison).where(SavedComparison.user_id == u.id))],
            "saved_chats": [_chat(c, True) for c in s.scalars(select(SavedChat).where(SavedChat.user_id == u.id))], "exported_at": utcnow().isoformat()}
    resp = jsonify(data)
    resp.headers["Content-Disposition"] = "attachment; filename=verity-my-data.json"
    return resp


@bp.delete("/api/account")
@login_required
def delete_account():
    u, s = current_user(), db()
    if not security.verify_password(u, body().get("password", "")):
        return error(403, "wrong_password", "Password is incorrect.", fields={"password": "Incorrect."})
    if u.role == "admin" and (s.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0) <= 1:
        return error(409, "last_admin", "You are the only administrator. Create another admin before deleting this account.")
    for o in s.scalars(select(Order).where(Order.user_id == u.id)):      # keep order records for accounting but remove personal details
        o.user_id, o.contact_email, o.ship_name, o.ship_phone, o.ship_line1, o.ship_line2 = None, "", "Deleted account", "", "", ""
    s.flush()
    security.end_session()
    s.delete(u)
    s.commit()
    return jsonify({"ok": True, "message": "Your account and personal data were deleted. Order records were kept without your name, contact or address."})


# ------------------------------------------------------------ addresses
def _addr(a: Address) -> dict:
    return {"id": a.id, "label": a.label, "full_name": a.full_name, "phone": a.phone, "line1": a.line1, "line2": a.line2, "city": a.city, "state": a.state, "pincode": a.pincode, "is_default": a.is_default}


@bp.get("/api/account/addresses")
@login_required
def addresses():
    return jsonify({"items": [_addr(a) for a in db().scalars(select(Address).where(Address.user_id == current_user().id).order_by(Address.is_default.desc(), Address.id))]})


def _save_address(a: Address | None):
    u, s, b = current_user(), db(), body()
    clean, errs = orders_svc.validate_address(b)
    label = " ".join(str(b.get("label", "Home")).split())[:40] or "Home"
    if errs:
        return error(422, "validation_failed", "Check the highlighted fields.", fields=errs)
    if a is None:
        if (s.scalar(select(func.count()).select_from(Address).where(Address.user_id == u.id)) or 0) >= 10:
            return error(409, "limit", "You can save up to 10 addresses.")
        a = Address(user_id=u.id)
        s.add(a)
    for k, v in clean.items():
        setattr(a, k, v)
    a.label = label
    s.flush()
    if b.get("is_default") or not s.scalar(select(Address.id).where(Address.user_id == u.id, Address.is_default.is_(True), Address.id != a.id)):
        for o in s.scalars(select(Address).where(Address.user_id == u.id)):
            o.is_default = o.id == a.id
    s.commit()
    return jsonify(_addr(a))


@bp.post("/api/account/addresses")
@login_required
def add_address():
    r = _save_address(None)
    if hasattr(r, "status_code"):
        return r
    return r, 201


@bp.put("/api/account/addresses/<int:aid>")
@login_required
def edit_address(aid):
    a = db().scalar(select(Address).where(Address.id == aid, Address.user_id == current_user().id))
    return error(404, "not_found", "Address not found.") if a is None else _save_address(a)


@bp.delete("/api/account/addresses/<int:aid>")
@login_required
def del_address(aid):
    a = db().scalar(select(Address).where(Address.id == aid, Address.user_id == current_user().id))
    if a is None:
        return error(404, "not_found", "Address not found.")
    db().delete(a)
    db().commit()
    return "", 204


# ------------------------------------------------------------ wishlist / recent
@bp.get("/api/account/wishlist")
@login_required
def wishlist():
    ids = [w.product_id for w in db().scalars(select(WishlistItem).where(WishlistItem.user_id == current_user().id).order_by(WishlistItem.created_at.desc()))]
    return jsonify({"items": _ser(ids), "ids": ids})


@bp.post("/api/account/wishlist")
@login_required
def wishlist_add():
    pid, s, u = str(body().get("product_id", "")), db(), current_user()
    if s.get(Product, pid) is None:
        return error(404, "not_found", "That product isn't in the catalogue.")
    if not s.scalar(select(WishlistItem.id).where(WishlistItem.user_id == u.id, WishlistItem.product_id == pid)):
        s.add(WishlistItem(user_id=u.id, product_id=pid))
        s.commit()
    return jsonify({"ok": True, "product_id": pid}), 201


@bp.delete("/api/account/wishlist/<pid>")
@login_required
def wishlist_remove(pid):
    db().execute(delete(WishlistItem).where(WishlistItem.user_id == current_user().id, WishlistItem.product_id == pid))
    db().commit()
    return "", 204


@bp.post("/api/account/recent")
@login_required
def recent_add():
    pid, s, u = str(body().get("product_id", "")), db(), current_user()
    if s.get(Product, pid) is None:
        return error(404, "not_found", "That product isn't in the catalogue.")
    r = s.scalar(select(RecentView).where(RecentView.user_id == u.id, RecentView.product_id == pid))
    if r:
        r.viewed_at = utcnow()
    else:
        s.add(RecentView(user_id=u.id, product_id=pid))
    s.flush()
    old = s.scalars(select(RecentView).where(RecentView.user_id == u.id).order_by(RecentView.viewed_at.desc()).offset(20)).all()
    for o in old:
        s.delete(o)
    s.commit()
    return "", 204


@bp.get("/api/account/recent")
@login_required
def recent():
    ids = [r.product_id for r in db().scalars(select(RecentView).where(RecentView.user_id == current_user().id).order_by(RecentView.viewed_at.desc()).limit(12))]
    return jsonify({"items": _ser(ids)})


@bp.delete("/api/account/recent")
@login_required
def recent_clear():
    db().execute(delete(RecentView).where(RecentView.user_id == current_user().id))
    db().commit()
    return "", 204


# ------------------------------------------------------------ saved comparisons
def _cmp(c: SavedComparison) -> dict:
    return {"id": c.id, "name": c.name, "product_ids": c.product_ids, "created_at": c.created_at.isoformat()}


@bp.get("/api/account/comparisons")
@login_required
def comparisons():
    return jsonify({"items": [_cmp(c) for c in db().scalars(select(SavedComparison).where(SavedComparison.user_id == current_user().id).order_by(SavedComparison.id.desc()))]})


@bp.post("/api/account/comparisons")
@login_required
def comparison_add():
    b, a, u, s = body(), assistant(), current_user(), db()
    ids = list(dict.fromkeys(str(i) for i in b.get("product_ids", []) if isinstance(i, str)))
    if not 2 <= len(ids) <= 4 or any(i not in a.by_id for i in ids):
        return error(400, "invalid_request", "Choose 2 to 4 products from the catalogue.")
    if (s.scalar(select(func.count()).select_from(SavedComparison).where(SavedComparison.user_id == u.id)) or 0) >= 20:
        return error(409, "limit", "You can save up to 20 comparisons. Delete one first.")
    name = " ".join(str(b.get("name") or " vs ".join(a.by_id[i].title.split()[0] for i in ids)).split())[:80]
    c = SavedComparison(user_id=u.id, name=name, product_ids=ids)
    s.add(c)
    s.commit()
    return jsonify(_cmp(c)), 201


@bp.delete("/api/account/comparisons/<int:cid>")
@login_required
def comparison_del(cid):
    r = db().execute(delete(SavedComparison).where(SavedComparison.id == cid, SavedComparison.user_id == current_user().id))
    db().commit()
    return ("", 204) if r.rowcount else error(404, "not_found", "Saved comparison not found.")


# ------------------------------------------------------------ preferences (opt-in, editable, deletable)
def _pref(p: Preference | None) -> dict:
    return {"categories": list(p.categories or []), "requirements": list(p.requirements or []),
            "budget_min": p.budget_min_paise / 100 if p and p.budget_min_paise else None, "budget_max": p.budget_max_paise / 100 if p and p.budget_max_paise else None,
            "saved": p is not None} if p else {"categories": [], "requirements": [], "budget_min": None, "budget_max": None, "saved": False}


@bp.get("/api/account/preferences")
@login_required
def prefs_get():
    a = assistant()
    from .catalog import facets
    f = facets(a)
    return jsonify({**_pref(db().get(Preference, current_user().id)), "options": {"categories": [c["name"] for c in f["categories"]], "requirements": [c["tag"] for c in f["collections"]]},
                    "note": "Optional. Used only to set search defaults and SmartMatch suggestions. You can edit or delete it any time."})


@bp.put("/api/account/preferences")
@login_required
def prefs_put():
    b, a, u, s = body(), assistant(), current_user(), db()
    from .catalog import facets
    f = facets(a)
    cats = [c for c in dict.fromkeys(b.get("categories", [])) if c in {x["name"] for x in f["categories"]}]
    reqs = [r for r in dict.fromkeys(b.get("requirements", [])) if r in {x["tag"] for x in f["collections"]}]
    try:
        lo = money.to_paise(b["budget_min"]) if b.get("budget_min") not in (None, "") else None
        hi = money.to_paise(b["budget_max"]) if b.get("budget_max") not in (None, "") else None
    except Exception:
        return error(422, "validation_failed", "Budget must be a number.")
    if (lo is not None and lo < 0) or (hi is not None and hi < 0) or (lo is not None and hi is not None and lo > hi):
        return error(422, "validation_failed", "Check your budget range: the minimum can't exceed the maximum.")
    p = s.get(Preference, u.id) or Preference(user_id=u.id)
    p.categories, p.requirements, p.budget_min_paise, p.budget_max_paise = cats, reqs, lo, hi
    s.add(p)
    s.commit()
    return jsonify(_pref(p))


@bp.delete("/api/account/preferences")
@login_required
def prefs_del():
    db().execute(delete(Preference).where(Preference.user_id == current_user().id))
    db().commit()
    return "", 204


# ------------------------------------------------------------ saved conversations / shortlists
def _chat(c: SavedChat, full=False) -> dict:
    d = {"id": c.id, "title": c.title, "kind": c.payload.get("kind", "conversation"), "product_ids": c.payload.get("product_ids", []), "created_at": c.created_at.isoformat()}
    if full:
        d["messages"] = c.payload.get("messages", [])
    return d


@bp.get("/api/account/chats")
@login_required
def chats():
    return jsonify({"items": [_chat(c, True) for c in db().scalars(select(SavedChat).where(SavedChat.user_id == current_user().id).order_by(SavedChat.id.desc()))]})


@bp.post("/api/account/chats")
@login_required
def chat_add():
    b, a, u, s = body(), assistant(), current_user(), db()
    msgs = [{"role": "user" if m.get("role") == "user" else "assistant", "text": str(m.get("text", ""))[:1200]} for m in b.get("messages", []) if isinstance(m, dict)][:30]
    ids = [i for i in dict.fromkeys(b.get("product_ids", [])) if isinstance(i, str) and i in a.by_id][:12]
    if not msgs and not ids:
        return error(400, "invalid_request", "There is nothing to save yet.")
    if (s.scalar(select(func.count()).select_from(SavedChat).where(SavedChat.user_id == u.id)) or 0) >= 30:
        return error(409, "limit", "You can keep up to 30 saved items. Delete one first.")
    first = next((m["text"] for m in msgs if m["role"] == "user"), "Shortlist")
    c = SavedChat(user_id=u.id, title=" ".join(str(b.get("title") or first).split())[:120], payload={"messages": msgs, "product_ids": ids, "kind": "shortlist" if ids else "conversation"})
    s.add(c)
    s.commit()
    return jsonify(_chat(c, True)), 201


@bp.delete("/api/account/chats/<int:cid>")
@login_required
def chat_del(cid):
    r = db().execute(delete(SavedChat).where(SavedChat.id == cid, SavedChat.user_id == current_user().id))
    db().commit()
    return ("", 204) if r.rowcount else error(404, "not_found", "Saved item not found.")


@bp.delete("/api/account/chats")
@login_required
def chats_clear():
    db().execute(delete(SavedChat).where(SavedChat.user_id == current_user().id))
    db().commit()
    return "", 204


# ------------------------------------------------------------ price watches (checked when you open the page; no alerts are sent)
@bp.get("/api/account/watches")
@login_required
def watches():
    out = []
    for w in db().scalars(select(PriceWatch).where(PriceWatch.user_id == current_user().id).order_by(PriceWatch.id.desc())):
        p = db().get(Product, w.product_id)
        if p:
            out.append({"product": store.serialize(p), "target_price": w.target_price_paise / 100, "target_text": money.text(w.target_price_paise),
                        "reached": p.price_paise is not None and p.price_paise <= w.target_price_paise})
    return jsonify({"items": out, "note": "Verity checks these when you open this page. It does not send emails or push alerts."})


@bp.put("/api/account/watches/<pid>")
@login_required
def watch_set(pid):
    s, u = db(), current_user()
    p = s.get(Product, pid)
    if p is None or p.price_paise is None:
        return error(404, "not_found", "That product can't be watched.")
    try:
        target = money.to_paise(body().get("target_price"))
    except Exception:
        target = None
    if not target or target <= 0:
        return error(422, "validation_failed", "Enter a target price above zero.")
    w = s.scalar(select(PriceWatch).where(PriceWatch.user_id == u.id, PriceWatch.product_id == pid)) or PriceWatch(user_id=u.id, product_id=pid, target_price_paise=target)
    w.target_price_paise = target
    s.add(w)
    s.commit()
    return jsonify({"ok": True, "target_text": money.text(target)})


@bp.delete("/api/account/watches/<pid>")
@login_required
def watch_del(pid):
    db().execute(delete(PriceWatch).where(PriceWatch.user_id == current_user().id, PriceWatch.product_id == pid))
    db().commit()
    return "", 204


# ------------------------------------------------------------ dashboard / recommendations
@bp.get("/api/recommendations")
@login_required
def recommendations():
    a = assistant()
    r = recommend.for_user(a, db(), current_user(), int(request.args.get("limit", 8) or 8))
    cards = {c["id"]: c for c in _ser([i["id"] for i in r["items"]])}
    r["items"] = [{"product": cards[i["id"]], "reasons": i["reasons"]} for i in r["items"] if i["id"] in cards]
    return jsonify(r)


@bp.get("/api/account/dashboard")
@login_required
def dashboard():
    u, s = current_user(), db()
    orders = s.scalars(select(Order).where(Order.user_id == u.id).order_by(Order.created_at.desc())).all()
    pref = s.get(Preference, u.id)
    wl = s.scalars(select(WishlistItem).where(WishlistItem.user_id == u.id)).all()
    return jsonify({"user": user_dict(u), "orders_count": len(orders), "recent_orders": [orders_svc.serialize(o) for o in orders[:3]], "spending": analytics.customer_spending(s, u),
                    "wishlist_count": len(wl), "has_preferences": bool(pref),
                    "comparisons_count": len(s.scalars(select(SavedComparison).where(SavedComparison.user_id == u.id)).all())})
