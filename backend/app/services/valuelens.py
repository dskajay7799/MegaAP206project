"""Verity Value Lens — a transparent breakdown of why a product is (or isn't) good value for *this* shopper.

Every factor is a statement about catalogue facts, with a verdict (good / neutral / concern / unknown). There is deliberately no hidden
composite "value score" and the cheapest product is never presented as automatically best."""
import statistics

from .. import money, specs as specs_mod
from . import smartmatch

M = lambda v: money.text(money.to_paise(v))


def lens(a, p, history: dict | None = None, budget=None, need: str = "") -> dict:
    peers = [q for q in a.products if q.id != p.id and q.price is not None and (q.subcategory and q.subcategory == p.subcategory)]
    if len(peers) < 2:
        peers = [q for q in a.products if q.id != p.id and q.price is not None and q.category == p.category]
    f, notes = [], []
    if budget:
        if p.price is None:
            f.append({"id": "budget", "label": "Budget", "verdict": "unknown", "detail": "No listed price, so it can't be checked against your budget."})
        elif p.price <= budget:
            f.append({"id": "budget", "label": "Budget", "verdict": "good", "detail": f"{M(p.price)} is {M(budget - p.price)} under your {M(budget)} budget."})
        else:
            f.append({"id": "budget", "label": "Budget", "verdict": "concern", "detail": f"{M(p.price)} is {M(p.price - budget)} over your {M(budget)} budget."})
    if p.price is not None and peers:
        prices = sorted(q.price for q in peers)
        cheaper_than = sum(1 for x in prices if x > p.price)
        f.append({"id": "price_position", "label": "Price among similar products", "verdict": "neutral",
                  "detail": f"{M(p.price)} is lower than {cheaper_than} of {len(prices)} similar {p.subcategory.lower() or p.category.lower()} (range {M(prices[0])}–{M(prices[-1])}, median {M(statistics.median(prices))})."})
    # requested needs
    if need.strip():
        intent = smartmatch.parse_need(a, need, budget)
        crit = [c for c in intent["criteria"]]
        if crit:
            pool = [p] + [q for q in peers if q.stock == "in_stock"]
            ctx = smartmatch._context(crit, pool, budget)
            for c in crit:
                fit, detail = smartmatch._fit(c, p, ctx)
                relative = c.kind == "spec" and c.threshold is None          # ranking among peers is not a pass/fail test, so it is never a "concern"
                verdict = "unknown" if fit is None else ("good" if fit >= (.66 if relative else .99) else "neutral" if relative or fit > .01 else "concern")
                f.append({"id": c.id, "label": c.label, "verdict": verdict, "detail": detail})
        for w in intent["unverifiable"]:
            notes.append(f"“{w}” can't be verified from catalogue data, so it isn't counted.")
    # spec standing among peers (only specs with a direction, only when at least 2 peers list them)
    shown = 0
    for k, v in p.specs.items():
        if shown >= 4 or not specs_mod.is_number(v) or specs_mod.better(k) not in ("higher", "lower"):
            continue
        vals = [q.specs[k] for q in peers if specs_mod.is_number(q.specs.get(k))]
        if len(vals) < 2:
            continue
        med = statistics.median(vals)
        hi = specs_mod.better(k) == "higher"
        better_than = sum(1 for x in vals if (v > x if hi else v < x))
        verdict = "good" if (v > med if hi else v < med) else "neutral"          # below the median is a fact about standing, not a defect
        f.append({"id": f"spec:{k}", "label": specs_mod.label(k), "verdict": verdict,
                  "detail": f"{specs_mod.fmt(k, v)} — better than {better_than} of {len(vals)} similar products (median {specs_mod.fmt(k, med)})."})
        shown += 1
    if p.rating is not None:
        tag = " This is demo data, not customer reviews." if p.data_origin == "demo" else ""
        f.append({"id": "rating", "label": "Catalogue rating", "verdict": "good" if p.rating >= 4.2 else "neutral" if p.rating >= 3.6 else "concern", "detail": f"{p.rating:g}/5.{tag}"})
    else:
        f.append({"id": "rating", "label": "Catalogue rating", "verdict": "unknown", "detail": "No rating in the catalogue."})
    h = history or {}
    pts = h.get("points", [])
    if h.get("enough_recorded"):
        real = [x for x in pts if not x["simulated"]]
        low = min(real, key=lambda x: x["price"])
        diff = p.price - low["price"] if p.price is not None else 0
        f.append({"id": "history", "label": "Recorded price history", "verdict": "good" if diff <= 0 else "neutral",
                  "detail": f"Lowest recorded price {M(low['price'])}; today's price is {'the lowest recorded' if diff <= 0 else M(diff) + ' above it'} ({len(real)} observations)."})
    elif h.get("has_simulated"):
        f.append({"id": "history", "label": "Price history", "verdict": "unknown", "detail": "Only simulated demo history exists, which is not real market data, so no price-trend claim is made."})
    else:
        f.append({"id": "history", "label": "Price history", "verdict": "unknown", "detail": "Not enough recorded price observations to say anything about price trends."})
    f.append({"id": "stock", "label": "Availability", "verdict": "good" if p.stock == "in_stock" else "concern" if p.stock == "out_of_stock" else "unknown",
              "detail": {"in_stock": "In stock.", "out_of_stock": "Out of stock right now.", "unknown": "Stock isn't listed."}[p.stock]
              + (f" Only {p.stock_qty} left." if p.stock == "in_stock" and p.stock_qty is not None and p.stock_qty <= 5 else "")})
    good = sum(x["verdict"] == "good" for x in f)
    bad = [x["label"].lower() for x in f if x["verdict"] == "concern"]
    unk = sum(x["verdict"] == "unknown" for x in f)
    summary = f"{good} of {len(f)} factors favour this product" + (f"; watch out for {', '.join(bad)}" if bad else "") + (f"; {unk} couldn't be checked from the data." if unk else ".")
    return {"product_id": p.id, "title": p.title, "factors": f, "summary": summary, "peer_count": len(peers), "notes": notes,
            "peer_basis": p.subcategory or p.category, "disclaimer": "Built only from catalogue facts. Verity doesn't invent discounts, competitor prices or price histories."}
