"""Explainable comparison studio.

Only like-for-like numbers are compared: a spec key is the same measurement for every product (same unit by construction, see specs.py).
Bars are zero-based; radar axes are scaled *relative to the compared set* (and labelled so); missing values stay missing."""
from .. import money, specs as specs_mod
from . import smartmatch

MAX_COMPARE = 4


def _p(p):
    return money.text(money.to_paise(p.price)) if p.price is not None else "Not listed"


def _norm(vals: list, better: str):
    """Relative 0..1 with best=1. Returns None for unknown; ties and single values give 1.0."""
    known = [v for v in vals if v is not None]
    if not known:
        return [None] * len(vals)
    lo, hi = min(known), max(known)
    out = []
    for v in vals:
        if v is None:
            out.append(None)
        elif hi == lo:
            out.append(1.0)
        else:
            out.append((v - lo) / (hi - lo) if better == "higher" else (hi - v) / (hi - lo))
    return out


def studio(a, prods: list, weights: dict | None = None, use_case: str = "") -> dict:
    n = len(prods)
    out = {"columns": [], "price": {}, "rows": [], "radar": None, "radar_reason": "", "criteria": [], "scores": [], "pros": {}, "limits": {}, "differences": [],
           "recommendation": None, "warnings": [], "use_case": use_case.strip()[:200]}
    for p in prods:
        out["columns"].append({"id": p.id, "title": p.title, "brand": p.brand, "image": p.image, "price": p.price, "price_text": _p(p), "rating": p.rating,
                               "stock": p.stock, "stock_text": {"in_stock": "In stock", "out_of_stock": "Out of stock"}.get(p.stock, "Stock not listed"),
                               "category": p.category, "subcategory": p.subcategory, "rating_is_demo": p.data_origin == "demo"})
    cats = {p.category for p in prods}
    if len(cats) > 1:
        out["warnings"].append("These products are in different categories, so only the specs they share are compared.")
    elif len({p.subcategory for p in prods}) > 1:
        out["warnings"].append("These are different kinds of product (" + ", ".join(sorted({p.subcategory for p in prods if p.subcategory})) + "). Shared specs are comparable, but they serve different purposes.")

    # price bars (zero-based)
    priced = [p.price for p in prods if p.price is not None]
    if len(priced) >= 2:
        mx = max(priced)
        out["price"] = {"max": mx, "bars": [None if p.price is None else round(p.price / mx, 3) for p in prods],
                        "cheapest": [i for i, p in enumerate(prods) if p.price is not None and p.price == min(priced)]}

    # spec rows
    keys = list(dict.fromkeys(k for p in prods for k, v in p.specs.items() if v not in (None, "")))
    first_seen = {k: i for i, k in enumerate(keys)}
    keys.sort(key=lambda k: (-sum(1 for p in prods if p.specs.get(k) not in (None, "")), 0 if specs_mod.better(k) in ("higher", "lower") else 1, first_seen[k]))
    for k in keys:
        raw = [p.specs.get(k) if p.specs.get(k) not in (None, "") else None for p in prods]
        disp = [None if v is None else specs_mod.fmt(k, v) for v in raw]
        better = specs_mod.better(k)
        row = {"key": k, "label": specs_mod.label(k), "unit": specs_mod.unit(k), "better": better, "values": disp, "raw": raw,
               "listed_for": sum(v is not None for v in raw), "differs": len({d for d in disp if d is not None}) > 1 or (any(d is None for d in disp) and any(d is not None for d in disp)),
               "numeric": all(v is None or specs_mod.is_number(v) for v in raw) and any(v is not None for v in raw), "best": [], "worst": [], "bars": None}
        nums = [v if specs_mod.is_number(v) else None for v in raw]
        if row["numeric"]:
            top = max(v for v in nums if v is not None)
            row["bars"] = [None if v is None else round(v / top, 3) if top else 0 for v in nums]
            if better in ("higher", "lower") and sum(v is not None for v in nums) >= 2 and len({v for v in nums if v is not None}) > 1:
                known = [v for v in nums if v is not None]
                bv, wv = (max(known), min(known)) if better == "higher" else (min(known), max(known))
                row["best"] = [i for i, v in enumerate(nums) if v == bv]
                row["worst"] = [i for i, v in enumerate(nums) if v == wv]
        elif better == "present":
            vals = [v if isinstance(v, bool) else None for v in raw]
            if True in vals and False in vals:
                row["best"] = [i for i, v in enumerate(vals) if v is True]
                row["worst"] = [i for i, v in enumerate(vals) if v is False]
        out["rows"].append(row)
    out["differences"] = [r["label"] for r in out["rows"] if r["differs"]]

    # radar: only axes every product lists, numeric, directional and non-constant
    axes = []
    for r in out["rows"]:
        if r["better"] in ("higher", "lower") and r["numeric"] and r["listed_for"] == n and len({v for v in r["raw"]}) > 1:
            axes.append({"key": r["key"], "label": r["label"], "unit": r["unit"], "better": r["better"], "values": r["raw"], "scaled": _norm(r["raw"], r["better"])})
    if n >= 2 and len(axes) >= 3:
        out["radar"] = {"axes": axes[:6], "note": "Each axis is scaled relative to these products only (1 = best of the group). It is not an absolute rating."}
    else:
        out["radar_reason"] = ("A radar chart needs at least 3 numeric specs that every selected product lists and that differ between them; "
                               f"{len(axes)} qualify here, so the aligned table and bars are shown instead.")

    # criteria + weighted score
    crit = []
    for r in out["rows"]:
        if r["better"] in ("higher", "lower", "present") and r["listed_for"] >= 2 and (r["numeric"] or r["better"] == "present"):
            crit.append({"id": r["key"], "label": r["label"], "better": r["better"], "default_weight": 1})
    if len(priced) >= 2:
        crit.append({"id": "price", "label": "Lower price", "better": "lower", "default_weight": 1})
    if sum(p.rating is not None for p in prods) >= 2:
        crit.append({"id": "rating", "label": "Catalogue rating", "better": "higher", "default_weight": 1})
    stated = {}
    if use_case.strip():
        intent = smartmatch.parse_need(a, use_case)
        for c in intent["criteria"]:
            for k in (c.spec_keys if c.kind in ("spec", "present") else []):
                stated[k] = 4
        if not stated:
            out["warnings"].append("I couldn't map that use case to specs these products list, so default weights are used.")
    for c in crit:
        c["weight"] = c["default_weight"] = stated.get(c["id"], 1)
    for c in crit:
        if weights and c["id"] in weights:
            try:
                c["weight"] = max(0.0, min(5.0, float(weights[c["id"]])))
            except (TypeError, ValueError):
                pass
    out["criteria"] = crit
    rel = {}
    for c in crit:
        if c["id"] == "price":
            vals, better = [p.price for p in prods], "lower"
        elif c["id"] == "rating":
            vals, better = [p.rating for p in prods], "higher"
        else:
            r = next(x for x in out["rows"] if x["key"] == c["id"])
            if r["better"] == "present":
                vals, better = [None if not isinstance(v, bool) else (1.0 if v else 0.0) for v in r["raw"]], "higher"
            else:
                vals, better = [v if specs_mod.is_number(v) else None for v in r["raw"]], r["better"]
        rel[c["id"]] = _norm(vals, better)
    tw = sum(c["weight"] for c in crit)
    for i, p in enumerate(prods):
        parts, got, known = [], 0.0, 0.0
        for c in crit:
            if c["weight"] <= 0:
                continue
            s = rel[c["id"]][i]
            got += c["weight"] * (s or 0)
            known += c["weight"] if s is not None else 0
            parts.append({"id": c["id"], "label": c["label"], "weight": c["weight"], "fit": None if s is None else round(s, 3),
                          "points": round(c["weight"] * (s or 0) / tw * 100, 1) if tw else 0})
        out["scores"].append({"id": p.id, "score": round(got / tw * 100, 1) if tw else None, "coverage": round(known / tw, 2) if tw else None, "parts": parts})

    # pros / limitations from computed facts only
    for i, p in enumerate(prods):
        pros, lim = [], []
        for r in out["rows"]:
            if i in r["best"]:
                pros.append(f"{'Highest' if r['better'] == 'higher' else 'Lowest'} {r['label'].lower()}: {r['values'][i]}" if r["numeric"] else f"{r['label']}: yes")
            if i in r["worst"]:
                lim.append(f"{'Lowest' if r['better'] == 'higher' else 'Highest'} {r['label'].lower()} of the group: {r['values'][i]}" if r["numeric"] else f"{r['label']}: no")
            if r["values"][i] is None and r["listed_for"] > 0 and r["better"] is not None:
                lim.append(f"{r['label']} isn't listed")
        if out["price"] and i in out["price"]["cheapest"] and len(set(priced)) > 1:
            pros.append(f"Lowest price: {_p(p)}")
        elif out["price"] and p.price == max(priced) and len(set(priced)) > 1:
            lim.append(f"Highest price of the group: {_p(p)}")
        if p.stock == "out_of_stock":
            lim.append("Currently out of stock")
        out["pros"][p.id], out["limits"][p.id] = pros[:5], list(dict.fromkeys(lim))[:5]

    # recommendation (only from the numbers above)
    ranked = sorted(zip(prods, out["scores"]), key=lambda x: (-(x[1]["score"] or 0), x[0].price or 0))
    if len(ranked) >= 2 and ranked[0][1]["score"] is not None and crit:
        (top, ts), (second, ss) = ranked[0], ranked[1]
        gap = round(ts["score"] - ss["score"], 1)
        diffs = sorted(((tp["points"] - sp["points"], tp["label"]) for tp, sp in zip(ts["parts"], ss["parts"])), reverse=True)
        lead = [lab for d, lab in diffs if d > 0][:3]
        goal = f"For “{use_case.strip()}”" if use_case.strip() else "On your weighted priorities"
        if gap < 3:
            text = f"{goal}, {top.title} and {second.title} are too close to call ({ts['score']} vs {ss['score']})."
        else:
            text = f"{goal}, {top.title} scores highest ({ts['score']} vs {ss['score']} for {second.title})" + (f", ahead on {', '.join(l.lower() for l in lead)}." if lead else ".")
        if top.price is not None and second.price is not None and top.price != second.price:
            cheaper, dear = (top, second) if top.price < second.price else (second, top)
            text += f" {cheaper.title} costs {money.text(money.to_paise(dear.price - cheaper.price))} less."
        out["recommendation"] = {"winner": top.id if gap >= 3 else None, "text": text, "gap": gap, "basis": "Weighted sum of the criteria below. Change the weights to match what matters to you."}
    return out
