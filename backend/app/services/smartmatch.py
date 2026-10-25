"""Verity SmartMatch — turn a plain-language need into explainable, evidence-based product matches.

Everything here is deterministic and uses only catalogue facts:
  1. parse   : budget, product type ("head" words found in subcategory/category/title), use-cases, features, colours/materials
  2. filter  : product type, budget, stock (excluded products are listed with the real reason)
  3. score   : score = sum(weight_i * fit_i) / sum(weight_i) * 100 over the criteria the shopper cares about
               fit_i is 0..1 from catalogue data; if the data is missing the criterion is *unverified* and scores 0 (never assumed)
  4. explain : per-product breakdown, missing specs, data coverage (share of weight that could actually be verified)
No language model is involved, so the score is reproducible and not a guess.
"""
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .. import money, specs as specs_mod
from ..assistant import COLOURS, parse_budget, strip_budget
from ..retrieval import STOP, tokenize

FORMULA = "score = Σ(weight × fit) ÷ Σ(weight) × 100. Fit is 0–1 from catalogue facts; unverified criteria count as 0."

USE_CASES = {
    "study": r"\b(study\w*|student|exam\w*|homework|focus\w*|college|campus)\b",
    "commute": r"\bcommut\w*\b",
    "travel": r"\b(travel\w*|trip|flight|holiday|vacation)\b",
    "gym": r"\b(gym|workout|work out|fitness|exercise|training)\b",
    "running": r"\b(running|jogging|marathon)\b",
    "office": r"\b(office|desk|wfh|work from home)\b",
    "home": r"\b(at home|home|household)\b",
    "cooking": r"\b(cook\w*|kitchen)\b",
    "gifting": r"\bgift\w*\b",
    "yoga": r"\b(yoga|meditat\w*|stretch\w*)\b",
    "outdoor": r"\b(outdoor\w*|hiking|trek\w*|camping)\b",
    "casual": r"\b(casual|everyday|daily wear)\b",
    "formal": r"\b(formal|interview|meetings?)\b",
    "monsoon": r"\b(monsoon|rainy|rain)\b",
    "daily": r"\b(daily|every ?day use)\b",
}
UNVERIFIABLE = re.compile(r"\b(comfort\w*|sound quality|good sound|great sound|bass|stylish|trendy|durable|sturdy|premium|best quality|looks? good|fashionable)\b", re.I)

# (id, phrase regex, spec keys tried in order, direction, label, optional threshold regex + conversion)
FEATURES = [
    ("battery", r"long[- ]lasting battery|long battery(?: life)?|battery(?: life| backup)?|backup|lasts? long|long[- ]lasting", ["battery_hours", "runtime_min", "capacity_mah"], "higher", "Battery",
     r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)\b"),
    ("lightweight", r"light[- ]?weight|\blight\b|portable|compact", ["weight_g"], "lower", "Light weight", r"(?:under|below|less than|max)\s*(\d+)\s*(?:g|grams?)\b"),
    ("anc", r"noise[- ]?cancel\w*|\banc\b|noise isolation", ["noise_cancellation"], "present", "Noise cancelling", None),
    ("waterproof", r"water[- ]?proof|water[- ]?resistan\w*|sweat[- ]?proof|splash[- ]?proof|rain[- ]?proof", ["water_resistance", "water_resistant"], "present", "Water resistance", None),
    ("fastcharge", r"fast[- ]?charg\w*|quick[- ]?charg\w*", ["output_w"], "higher", "Charging power", r"(\d+)\s*w\b"),
    ("insulated", r"insulat\w*|keeps? (?:drinks )?(?:cold|hot)|stays? (?:cold|hot)", ["insulation_hours"], "higher", "Insulation", None),
    ("capacity", r"large capacity|big capacity|high capacity|spacious|roomy", ["volume_l", "capacity_mah", "capacity_ml"], "higher", "Capacity", None),
    ("laptop", r"laptops?", ["laptop_max_inch"], "present", "Fits a laptop", r"(\d{2}(?:\.\d)?)\s*(?:inch|in\b|\")"),
    ("bright", r"bright\w*", ["brightness_lumens"], "higher", "Brightness", None),
    ("wireless", r"wireless|bluetooth|cordless", ["wireless", "bluetooth", "runtime_min"], "present", "Wireless", None),
    ("spf", r"\bspf\b|sun ?protection", ["spf"], "higher", "Sun protection", r"spf\s*(\d+)"),
    ("nonslip", r"non[- ]?slip|\bgrip\w*", ["non_slip"], "present", "Non-slip", None),
    ("washable", r"machine[- ]?wash\w*|easy care", ["machine_washable"], "present", "Machine washable", None),
    ("cushion", r"cushion\w*", ["cushioning"], "present", "Cushioning", None),
]
DEFAULT_WEIGHT = {"feature": 4, "use": 4, "needle": 3, "colour": 3, "rating": 1, "headroom": 1, "pref": 1}


@dataclass
class Criterion:
    id: str
    label: str
    kind: str                       # spec | present | tag | needle | colour | rating | headroom | pref_category
    weight: float = 3
    spec_keys: list = field(default_factory=list)
    direction: str = "higher"
    threshold: float | None = None
    needle: str = ""
    tag: str = ""
    source: str = "need"            # need | preference | default

    def public(self, default_weight=None) -> dict:
        return {"id": self.id, "label": self.label, "kind": self.kind, "weight": self.weight, "default_weight": default_weight if default_weight is not None else self.weight,
                "source": self.source, "threshold": self.threshold}


# ------------------------------------------------------------------ catalogue vocabulary (cached per Assistant instance)
def _vocab(a):
    v = getattr(a, "_sm_vocab", None)
    if v is not None:
        return v
    head = defaultdict(set)
    for i, p in enumerate(a.products):
        for t in tokenize(f"{p.subcategory} {p.category}"):
            head[t].add(i)
    tags = Counter(t for p in a.products for t in p.use_cases)
    sub_names = sorted({p.subcategory for p in a.products if p.subcategory})
    a._sm_vocab = v = {"head": head, "tags": tags, "subs": sub_names}
    return v


def _text_of(p) -> str:
    return " ".join([p.title, p.subcategory, p.category, p.description, " ".join(p.highlights), " ".join(map(str, p.attributes.values()))]).lower()


# ------------------------------------------------------------------ parsing
def parse_need(a, text: str, budget_override=None) -> dict:
    vocab = _vocab(a)
    raw = " ".join(str(text).split())[:500]
    low = strip_budget(raw).lower()
    budget = budget_override if budget_override not in (None, "") else parse_budget(raw)
    criteria: list[Criterion] = []
    notes, unverifiable = [], []

    use, unknown_use = [], []
    for tag, rx in USE_CASES.items():
        if re.search(rx, low):
            low = re.sub(rx, " ", low)
            (use if vocab["tags"].get(tag) else unknown_use).append(tag)
    for w in re.findall(r"[a-z]+", low):                         # a catalogue tag typed directly
        if w in vocab["tags"] and w not in use and w not in STOP:
            use.append(w)
    for tag in use:
        criteria.append(Criterion(f"use:{tag}", f"Suits {tag}", "tag", DEFAULT_WEIGHT["use"], tag=tag))

    for fid, rx, keys, direction, label, thr_rx in FEATURES:
        m = re.search(rx, low)
        if not m:
            continue
        thr = None
        if thr_rx:
            tm = re.search(thr_rx, low)
            if tm:
                thr = float(tm.group(1).replace(",", ""))
        low = re.sub(rx, " ", low)
        if thr is not None:
            low = re.sub(thr_rx, " ", low)
        lab = f"{label} ≥ {thr:g}" if thr is not None and direction == "higher" else f"{label} ≤ {thr:g}" if thr is not None else label
        criteria.append(Criterion(f"feat:{fid}", lab, "spec" if direction in ("higher", "lower") else "present", DEFAULT_WEIGHT["feature"],
                                  spec_keys=keys, direction=direction, threshold=thr))
    for m in UNVERIFIABLE.finditer(low):
        unverifiable.append(m.group(0).lower())
    low = UNVERIFIABLE.sub(" ", low)

    toks = list(dict.fromkeys(a.tok(low)))
    heads, colour_t, needles, unrecognised = [], [], [], []
    for t in toks:
        if t in vocab["head"]:
            heads.append(t)
        elif t in COLOURS:
            colour_t.append(t)
        elif t in a.index.vocab:
            needles.append(t)
        else:
            unrecognised.append(t)
    for t in colour_t:
        criteria.append(Criterion(f"colour:{t}", f"Colour: {t}", "colour", DEFAULT_WEIGHT["colour"], needle=t))
    for t in needles:
        criteria.append(Criterion(f"needle:{t}", f"Mentions “{t}”", "needle", DEFAULT_WEIGHT["needle"], needle=t))
    return {"text": raw, "budget": budget, "heads": heads, "use": use, "unknown_use": unknown_use, "criteria": criteria, "unverifiable": sorted(set(unverifiable)),
            "unrecognised": unrecognised, "notes": notes}


# ------------------------------------------------------------------ candidate selection
def candidates(a, intent: dict) -> tuple[list, list]:
    """Returns (candidates, near) — near is used only to explain a miss."""
    vocab, heads = _vocab(a), intent["heads"]
    if not heads:
        return [], []
    sets = [vocab["head"][h] for h in heads]
    full = set.intersection(*sets)
    titled = {i for i, p in enumerate(a.products) if all(h in a.title_toks[i] or h in set(tokenize(f"{p.subcategory} {p.category}")) for h in heads)}
    idx = sorted(full | titled)
    near = sorted(set().union(*sets) - set(idx))
    return [a.products[i] for i in idx], [a.products[i] for i in near][:4]


# ------------------------------------------------------------------ scoring
def _pool_key(c: Criterion, pool) -> str | None:
    best, n = None, 0
    for k in c.spec_keys:
        cnt = sum(1 for p in pool if specs_mod.is_number(p.specs.get(k)))
        if cnt > n:
            best, n = k, cnt
    return best


def _fit(c: Criterion, p, ctx: dict):
    """Returns (fit 0..1 or None, human detail). None = the catalogue doesn't say."""
    if c.kind == "tag":
        if not p.use_cases:
            return None, "Use-cases not listed"
        ok = c.tag in p.use_cases
        return (1.0 if ok else 0.0), (f"Listed as suited to {c.tag}" if ok else f"Not listed as suited to {c.tag}")
    if c.kind == "spec":
        key = ctx["keys"].get(c.id)
        v = p.specs.get(key) if key else None
        if not specs_mod.is_number(v):
            return None, f"{specs_mod.label(c.spec_keys[0])} not listed"
        disp = f"{specs_mod.label(key)}: {specs_mod.fmt(key, v)}"
        if c.threshold is not None:
            ok = v >= c.threshold if c.direction == "higher" else v <= c.threshold
            return (1.0 if ok else 0.0), f"{disp} ({'meets' if ok else 'misses'} {specs_mod.fmt(key, c.threshold)})"
        lo, hi, vals = ctx["ranges"][c.id]
        fit = 1.0 if hi == lo else ((v - lo) / (hi - lo) if c.direction == "higher" else (hi - v) / (hi - lo))
        rank = 1 + sum(1 for x in vals if (x > v if c.direction == "higher" else x < v))
        return fit, f"{disp} — {'best' if rank == 1 else f'#{rank}'} of {len(vals)} with data"
    if c.kind == "present":
        seen = False
        for k in c.spec_keys:
            v = p.specs.get(k)
            if v in (None, ""):
                continue
            seen = True
            if v is True or (specs_mod.is_number(v) and v > 0) or (isinstance(v, str) and v.strip()):
                return 1.0, f"{specs_mod.label(k)}: {specs_mod.fmt(k, v)}"
        return (0.0, f"{specs_mod.label(c.spec_keys[0])}: no") if seen else (None, f"{specs_mod.label(c.spec_keys[0])} not listed")
    if c.kind == "colour":
        colours = " ".join(str(v) for k, v in p.attributes.items() if k.lower() in ("colour", "color")).lower()
        if not colours:
            return None, "Colour not listed"
        return (1.0, f"Available in {c.needle}") if c.needle in colours else (0.0, f"Not listed in {c.needle}")
    if c.kind == "needle":
        txt = _text_of(p)
        if re.search(rf"\b{re.escape(c.needle)}s?\b", txt):
            return 1.0, f"Product text mentions “{c.needle}”"
        has_material = any(k.lower() in ("material", "fabric") for k in p.attributes)
        return (0.0, f"Doesn't mention “{c.needle}”") if has_material or p.description else (None, "No description to check")
    if c.kind == "rating":
        if p.rating is None:
            return None, "No catalogue rating"
        tag = " (demo data, not customer reviews)" if p.data_origin == "demo" else ""
        return max(0.0, min(1.0, (p.rating - 3) / 2)), f"Catalogue rating {p.rating:g}/5{tag}"
    if c.kind == "headroom":
        b = ctx["budget"]
        if not b or p.price is None:
            return None, "No budget set"
        return max(0.0, min(1.0, 1 - p.price / b)), f"{money.text(money.to_paise(b - p.price))} under budget" if p.price <= b else "Over budget"
    if c.kind == "pref_category":
        return (1.0, "In a category you prefer") if p.category in ctx["pref_categories"] else (0.0, "Not in a preferred category")
    return None, ""


def _context(criteria, pool, budget, pref_categories=()):
    keys, ranges = {}, {}
    for c in criteria:
        if c.kind == "spec":
            k = _pool_key(c, pool)
            keys[c.id] = k
            vals = [p.specs[k] for p in pool if k and specs_mod.is_number(p.specs.get(k))]
            if vals:
                ranges[c.id] = (min(vals), max(vals), vals)
    return {"keys": keys, "ranges": ranges, "budget": budget, "pref_categories": set(pref_categories)}


def score_product(p, criteria: list[Criterion], ctx: dict) -> dict:
    rows, total_w, got, known_w = [], sum(c.weight for c in criteria if c.weight > 0), 0.0, 0.0
    for c in criteria:
        if c.weight <= 0:
            continue
        fit, detail = _fit(c, p, ctx)
        pts = (c.weight * (fit or 0.0) / total_w * 100) if total_w else 0.0
        got += c.weight * (fit or 0.0)
        known_w += c.weight if fit is not None else 0
        verdict = "unknown" if fit is None else ("met" if fit >= 0.99 else "unmet" if fit <= 0.01 else "partial")
        rows.append({"id": c.id, "label": c.label, "weight": c.weight, "fit": None if fit is None else round(fit, 3), "points": round(pts, 1), "max_points": round(c.weight / total_w * 100, 1) if total_w else 0,
                     "verdict": verdict, "detail": detail})
    score = round(got / total_w * 100, 1) if total_w else None
    return {"score": score, "coverage": round(known_w / total_w, 2) if total_w else None, "breakdown": rows,
            "missing": [r["detail"] for r in rows if r["verdict"] == "unknown"]}


def _card(a, p) -> dict:
    return a._card(p) | {"brand": p.brand, "subcategory": p.subcategory, "stock_qty": p.stock_qty, "images": p.images[:1]}


# ------------------------------------------------------------------ main entry
def run(a, text: str, *, budget=None, weights: dict | None = None, in_stock_only: bool = True, prefs: dict | None = None, limit: int = 6,
        use_preferences: bool = True) -> dict:
    intent = parse_need(a, text, budget)
    b = intent["budget"]
    criteria: list[Criterion] = list(intent["criteria"])
    applied = []
    if prefs and use_preferences:
        if b is None and prefs.get("budget_max"):
            b = float(prefs["budget_max"])
            applied.append(f"your saved budget of up to {money.text(money.to_paise(b))}")
        have = {c.tag for c in criteria if c.kind == "tag"}
        for tag in prefs.get("requirements", []):
            if tag in _vocab(a)["tags"] and tag not in have:
                criteria.append(Criterion(f"use:{tag}", f"Suits {tag}", "tag", DEFAULT_WEIGHT["pref"] + 1, tag=tag, source="preference"))
                applied.append(f"your saved need “{tag}”")
        if prefs.get("categories"):
            criteria.append(Criterion("pref:category", "In a category you prefer", "pref_category", DEFAULT_WEIGHT["pref"], source="preference"))
            applied.append("your preferred categories")
    out = {"query": intent["text"], "formula": FORMULA, "budget": b, "budget_text": money.text(money.to_paise(b)) if b else None,
           "applied_preferences": applied, "status": "ok", "matches": [], "excluded": [], "criteria": [], "notes": [], "clarify": None, "follow_up": None,
           "intent": {"product_words": intent["heads"], "use_cases": intent["use"], "unknown_use_cases": intent["unknown_use"], "unverifiable_wishes": intent["unverifiable"],
                      "unrecognised_words": intent["unrecognised"]}}
    vocab = _vocab(a)
    pool, near = candidates(a, intent)

    if not intent["heads"]:
        tagged = [p for p in a.products if any(t in p.use_cases for t in intent["use"])]
        if tagged:
            subs = Counter(p.subcategory for p in tagged if p.subcategory)
            out.update(status="clarify", clarify={"question": f"What kind of product do you need for {' and '.join(intent['use'])}?",
                       "reason": "Several kinds of product are listed for that use, and ranking unlike products against each other wouldn't be meaningful.",
                       "options": [{"label": f"{s} ({n})", "append": s.lower()} for s, n in subs.most_common(8)]})
            return out
        if intent["unrecognised"] and not intent["use"] and not intent["unknown_use"]:
            out.update(status="no_match", notes=[f"I couldn't find “{' '.join(intent['unrecognised'])}” anywhere in the catalogue, so I won't guess."])
            return out
        out.update(status="clarify", clarify={"question": "What kind of product are you looking for?", "reason": "I need a product type to filter the catalogue.",
                   "options": [{"label": s, "append": s.lower()} for s in vocab["subs"][:10]]})
        return out
    if not pool:
        msg = f"No product in the catalogue is both “{' '.join(intent['heads'])}”."
        out.update(status="no_match", notes=[msg], excluded=[{"id": p.id, "title": p.title, "reason": "Matches only part of your product words"} for p in near])
        return out
    cats = Counter(p.category for p in pool)
    if len(cats) > 1 and len(intent["heads"]) == 1 and not (intent["use"] or b):
        out.update(status="clarify", clarify={"question": f"“{intent['heads'][0]}” appears in several categories. Which did you mean?", "reason": "The same word is used for unlike products.",
                   "options": [{"label": f"{c} ({n})", "append": c.lower()} for c, n in cats.most_common()]})
        return out

    if b and not any(c.kind == "headroom" for c in criteria):
        criteria.append(Criterion("headroom", "Price headroom under budget", "headroom", DEFAULT_WEIGHT["headroom"], source="default"))
    if any(p.rating is not None for p in pool):
        criteria.append(Criterion("rating", "Catalogue rating", "rating", DEFAULT_WEIGHT["rating"], source="default"))
    default_w = {c.id: c.weight for c in criteria}
    for c in criteria:
        if weights and c.id in weights:
            try:
                c.weight = max(0.0, min(5.0, float(weights[c.id])))
            except (TypeError, ValueError):
                pass

    kept, excluded = [], []
    for p in pool:
        if b is not None and (p.price is None or p.price > b):
            why = "No listed price" if p.price is None else f"Over budget by {money.text(money.to_paise(p.price - b))} ({money.text(money.to_paise(p.price))})"
            excluded.append({"id": p.id, "title": p.title, "reason": why, "kind": "budget", "price_text": money.text(money.to_paise(p.price))})
        elif in_stock_only and p.stock != "in_stock":
            excluded.append({"id": p.id, "title": p.title, "reason": "Out of stock" if p.stock == "out_of_stock" else "Stock not listed", "kind": "stock"})
        else:
            kept.append(p)
    if not kept:
        priced = [p for p in pool if p.price is not None]
        out.update(status="no_match", excluded=excluded[:8])
        if b is not None and priced:
            lo = min(priced, key=lambda p: p.price)
            out["notes"].append(f"Nothing fits {money.text(money.to_paise(b))}. The lowest-priced option is {lo.title} at {money.text(money.to_paise(lo.price))}.")
            out["matches"] = []
        else:
            out["notes"].append("Every matching product is currently unavailable.")
        out["criteria"] = [c.public(default_w[c.id]) for c in criteria]
        return out

    ctx = _context(criteria, kept, b, (prefs or {}).get("categories", []) if use_preferences else [])
    scored = [(p, score_product(p, criteria, ctx)) for p in kept]
    scored.sort(key=lambda x: (-(x[1]["score"] or 0), x[0].price or 0, x[0].id))   # ties: cheaper first, then ID, so order is deterministic
    for i, (p, r) in enumerate(scored[:limit], 1):
        good = sorted((x for x in r["breakdown"] if x["verdict"] in ("met", "partial") and x["points"] > 0), key=lambda x: -x["points"])[:3]
        out["matches"].append({"rank": i, "product": _card(a, p), "score": r["score"], "coverage": r["coverage"], "breakdown": r["breakdown"], "missing": r["missing"],
                               "reasons": [f"{x['label']}: {x['detail']}" for x in good],
                               "price_vs_budget": (f"{money.text(money.to_paise(b - p.price))} under your budget" if b is not None and p.price is not None else None)})
    out["excluded"] = excluded[:10]
    out["criteria"] = [c.public(default_w[c.id]) for c in criteria]
    out["total_candidates"] = len(pool)
    if intent["unknown_use"]:
        out["notes"].append("No product lists these uses, so they couldn't be used: " + ", ".join(intent["unknown_use"]) + ".")
    if intent["unverifiable"]:
        out["notes"].append("The catalogue has no data to verify: " + ", ".join(intent["unverifiable"]) + ". They were not scored.")
    if intent["unrecognised"]:
        out["notes"].append("Not found in the catalogue and ignored: " + ", ".join(intent["unrecognised"]) + ".")
    if b is None:
        out["notes"].append("No budget given, so price isn't used to filter or rank.")
    if len(kept) == 1:
        out["notes"].append("Only one product fits, so scores can't be compared against alternatives.")
    # data-driven follow-up: which scoreable specs exist among the candidates and aren't already criteria
    if not any(c.kind in ("spec", "present", "tag") for c in criteria):
        avail = Counter(k for p in kept for k in specs_mod.numeric_keys(p.specs))
        chips = [{"label": specs_mod.label(k), "append": k} for k, _ in avail.most_common(4)]
        out["follow_up"] = {"question": "What matters most to you? I can rank these on any of the specs they list.", "chips": chips, "needs_budget": b is None}
    return out
