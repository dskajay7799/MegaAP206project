"""Smart Budget Basket — explore a set of products for a purpose within a total budget, using only catalogue data.

Slots are product types (subcategories) that the catalogue itself associates with the stated use (via each product's `use_cases`),
or product types the shopper names. For each slot the top few candidates are scored with the same explainable SmartMatch criteria;
the optimiser then picks at most one product per slot to fill as many slots as the budget allows, then maximise total fit."""
import itertools
from collections import Counter

from .. import money
from . import smartmatch

M = lambda v: money.text(money.to_paise(v))
PER_SLOT = 4


def _slots(a, intent, text):
    """Returns (slots: list[(name, pool)], notes)."""
    vocab = smartmatch._vocab(a)
    out, notes, seen = [], [], set()
    parts = [s for s in __import__("re").split(r"\s*(?:,|&|\+|\band\b|\bplus\b)\s*", text) if s.strip()]
    explicit = []
    for seg in parts:
        it = smartmatch.parse_need(a, seg)
        if it["heads"]:
            pool, _ = smartmatch.candidates(a, it)
            if pool:
                sub = Counter(p.subcategory or p.category for p in pool).most_common(1)[0][0]
                if sub not in seen:
                    seen.add(sub)
                    explicit.append((sub, [p for p in a.products if (p.subcategory or p.category) == sub]))
    if explicit:
        return explicit, notes
    tags = intent["use"]
    if intent["unknown_use"]:
        notes.append("No product lists these uses: " + ", ".join(intent["unknown_use"]) + ".")
    tagged = [p for p in a.products if any(t in p.use_cases for t in tags)]
    by_sub = {}
    for p in tagged:
        by_sub.setdefault(p.subcategory or p.category, []).append(p)
    ranked = sorted(by_sub.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return [(k, v) for k, v in ranked], notes


def build(a, budget: float, text: str, in_stock_only: bool = True, max_slots: int = 6) -> dict:
    out = {"budget": budget, "budget_text": M(budget), "purpose": text.strip()[:200], "status": "ok", "baskets": [], "slots": [], "over_budget": [], "notes": [], "clarify": None}
    intent = smartmatch.parse_need(a, text)
    slots, notes = _slots(a, intent, text)
    out["notes"] += notes
    if not slots:
        tags = Counter(t for p in a.products for t in p.use_cases)
        out.update(status="clarify", clarify={"question": "What is the basket for?", "reason": "I build baskets from the uses the catalogue lists. Pick one, or name the products you want.",
                                              "options": [{"label": f"{t} ({n})", "append": t} for t, n in tags.most_common(10)]})
        return out
    if len(slots) > max_slots:
        out["notes"].append(f"{len(slots)} product types suit this; showing the {max_slots} with the most choice.")
        slots = slots[:max_slots]
    criteria = list(intent["criteria"])
    criteria.append(smartmatch.Criterion("rating", "Catalogue rating", "rating", 1))
    per_slot = []
    for name, pool in slots:
        use_pool = [p for p in pool if any(t in p.use_cases for t in intent["use"])] if intent["use"] else pool
        use_pool = use_pool or pool
        ok = [p for p in use_pool if p.price is not None and (p.stock == "in_stock" or not in_stock_only)]
        info = {"slot": name, "available": len(ok), "candidates": [], "skipped": None}
        if not ok:
            info["skipped"] = "No in-stock product with a listed price for this type." if use_pool else "No products."
            per_slot.append(info)
            continue
        ctx = smartmatch._context(criteria, ok, budget)
        scored = [(p, smartmatch.score_product(p, criteria, ctx)) for p in ok]
        scored.sort(key=lambda x: (-(x[1]["score"] or 0), x[0].price, x[0].id))
        info["candidates"] = [(p, r) for p, r in scored[:PER_SLOT]]
        per_slot.append(info)
    fillable = [s for s in per_slot if s["candidates"]]
    if not fillable:
        out.update(status="no_match", notes=out["notes"] + ["None of the matching product types has an in-stock, priced product."])
        return out

    cap = round(budget * 100)
    best = []   # (filled, score, total, combo)
    choices = [[None] + [(p, round(p.price * 100), r["score"] or 0) for p, r in s["candidates"]] for s in fillable]
    for combo in itertools.product(*choices):
        total = sum(c[1] for c in combo if c)
        if total > cap:
            continue
        best.append((sum(1 for c in combo if c), sum(c[2] for c in combo if c), total, combo))
    if not best or max(b[0] for b in best) == 0:
        lows = sorted((min(p.price for p, _ in s["candidates"]), s["slot"]) for s in fillable)
        out.update(status="no_match", notes=out["notes"] + [f"Nothing fits {M(budget)}: the cheapest single item here is {M(lows[0][0])} ({lows[0][1].lower()})."])
        return out
    top_filled = max(b[0] for b in best)
    pool_best = [b for b in best if b[0] == top_filled]
    picks = {"Best fit within budget": max(pool_best, key=lambda b: (b[1], -b[2])),
             "Lowest total cost": min(pool_best, key=lambda b: (b[2], -b[1])),
             "Uses more of your budget": max(pool_best, key=lambda b: (b[2], b[1]))}
    seen, baskets = set(), []
    score_map = {s["slot"]: {p.id: r for p, r in s["candidates"]} for s in fillable}
    for label, (filled, score, total, combo) in picks.items():
        key = tuple(c[0].id if c else None for c in combo)
        if key in seen:
            continue
        seen.add(key)
        items = []
        for s, c in zip(fillable, combo):
            if not c:
                continue
            p = c[0]
            r = score_map[s["slot"]][p.id]
            good = sorted((x for x in r["breakdown"] if x["verdict"] in ("met", "partial") and x["points"] > 0), key=lambda x: -x["points"])[:2]
            left = cap - total
            alts = [{"id": q.id, "title": q.title, "price_text": M(q.price), "delta_text": ("+" if q.price >= p.price else "−") + M(abs(q.price - p.price)), "score": rr["score"]}
                    for q, rr in s["candidates"] if q.id != p.id and round(q.price * 100) - c[1] <= left][:3]
            items.append({"slot": s["slot"], "product": a._card(p) | {"brand": p.brand}, "price_text": M(p.price), "fit": r["score"],
                          "why": [f"{x['label']}: {x['detail']}" for x in good] or ["Best available match for this type under the budget"], "missing": r["missing"][:2], "alternatives": alts})
        baskets.append({"label": label, "items": items, "total": total / 100, "total_text": money.text(total), "remaining": (cap - total) / 100, "remaining_text": money.text(cap - total),
                        "slots_filled": len(items), "slots_total": len(fillable), "avg_fit": round(score / max(1, len(items)), 1)})
    out["baskets"] = baskets
    main = baskets[0]
    chosen = {i["product"]["id"] for i in main["items"]}
    filled_slots = {i["slot"] for i in main["items"]}
    for s in per_slot:
        if s["skipped"]:
            out["slots"].append({"slot": s["slot"], "status": "unavailable", "reason": s["skipped"]})
        elif s["slot"] in filled_slots:
            out["slots"].append({"slot": s["slot"], "status": "filled", "reason": "Included"})
        else:
            low = min(p.price for p, _ in s["candidates"])
            out["slots"].append({"slot": s["slot"], "status": "skipped", "reason": f"Left out: the cheapest option ({M(low)}) doesn't fit the remaining {main['remaining_text']} once the other items are chosen."})
    for s in fillable:
        for p, r in s["candidates"]:
            if p.id in chosen:
                continue
            slot_item = next((i for i in main["items"] if i["slot"] == s["slot"]), None)
            swapped_out = float(slot_item["price_text"].replace("₹", "").replace(",", "")) if slot_item else 0.0     # swapping frees the price of the item it replaces
            room = main["remaining"] + swapped_out
            if p.price > room + 1e-9:
                out["over_budget"].append({"id": p.id, "title": p.title, "slot": s["slot"], "price_text": M(p.price), "over_by_text": M(p.price - room),
                                           "reason": f"Would exceed the budget by {M(p.price - room)} with the other items in the basket."})
    out["over_budget"] = out["over_budget"][:6]
    if main["slots_filled"] < len(per_slot):
        out["notes"].append(f"Filled {main['slots_filled']} of {len(per_slot)} product types that suit this purpose; see the list below for why the rest were left out.")
    return out
