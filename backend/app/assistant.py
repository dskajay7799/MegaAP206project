"""Grounded answer pipeline (retrieval + evidence selection + answer construction). No free-text generation here.

Every sentence is composed from catalogue / policy fields and carries an [ID] citation. Decision order:
unsupported request -> compare / product ID -> policy -> follow-up about shown products -> catalogue search.

Multi-turn: the client sends earlier *user* messages; they are replayed through the same router to rebuild a small
structured `Ctx` (topic terms, budget, attribute constraints, in-stock flag, last shown product IDs). Nothing is stored
server-side, so a page refresh starts a fresh conversation.
"""
import re
from dataclasses import dataclass, field

from urllib.parse import quote

from . import money as money_mod
from . import nlu
from . import specs as specs_mod
from .catalogue import Product, Section
from .retrieval import BM25, COLOURS, STOP, SYNONYMS, correct, tokenize

MIN_COVERAGE = 0.6   # share of topic terms a product must match before it is even considered "close"
NA = "Not available in catalogue"
ATTR_KEYS = {"colour", "color", "material", "size"}
MAX_COMPARE = 4

I = re.I
# Lookups the assistant has no evidence for. "my order" alone is soft: with a policy word ("can I cancel my order") it is a policy question.
UNSUPPORTED = re.compile(r"\b(my orders?|order status|track\w*|where(?:'s| is) my|payments?|pay(?:ing)? (?:by|with|using|via)|upi|(?:credit|debit) card|account|log ?in|sign ?in|password|"
                         r"coupon\w*|discount\w*|promo\w*|offers|any offers?|special offers?|deals?|change my (?:\w+ )?address)\b", I)
# \"noise cancelling\" is a product feature, not the cancellation policy.
POLICY = re.compile(r"\b(returns?|refunds?|exchange|replacement|shipping|ship|delivery|deliver|warranty|guarantee|(?<!noise )(?<!noise-)cancel\w*)\b", I)
POLICY_WORDS = frozenset("return returns refund refunds exchange replacement shipping delivery warranty guarantee cancel cancellation cancellations".split())
# Which policy wording covers which catalogue category (the policy text names classes of goods, not products).
POLICY_CLASS = {"Electronics": ("electronics", "electronic"), "Fashion": ("apparel", "clothing"), "Footwear": ("footwear",)}
COMPARE = re.compile(r"\b(compare|comparison|versus|vs|difference)\b", I)
PRICE = re.compile(r"\b(price|cost|kitna|kimat|dam|rate|how much)\b", I)
STOCK = re.compile(r"\b(stock|available|availability)\b", I)
RATING = re.compile(r"\b(rating|ratings|rated)\b", I)
SPEC = re.compile(r"\b(spec|specs|specification|details?|features?|material|size|colou?r)\b", I)
LISTING = re.compile(r"\b(show|list|find|suggest|recommend|options?|any|best|cheap|cheapest|dikhao|chahiye|looking|under|below|something|anything|everything|stuff|items?|products?|ideas?|gift|need|want)\b", I)
INSTOCK = re.compile(r"\b(in[ -]stock|available now|currently available|only available)\b", I)
FOLLOW = re.compile(r"\b(only|also|those|these|ones?|instead|already|same|too|bhi|aur)\b", I)
CHEAP = re.compile(r"\b(cheapest|cheaper|cheap|inexpensive|affordable|lowest price|least expensive|sasta|sabse sasta)\b", I)
TOPRATED = re.compile(r"\b(highest rated|best rated|top rated|best reviewed|highest rating)\b", I)
BETTER = re.compile(r"\b(which|konsa|kaun sa)\b.*\b(better|best|accha|achha)\b|\b(better one|which one)\b", I)
_AMT = r"([\d][\d,]*(?:\.\d+)?)"
BUDGET = re.compile(
    rf"(?:under|below|less than|upto|up to|within|max(?:imum)?|budget(?: of)?)\s*(?:rs\.?|inr|₹)?\s*{_AMT}"
    rf"|(?:rs\.?|inr|₹)\s*{_AMT}\s*(?:se kam|ke andar|or less|tak)?|{_AMT}\s*(?:rs|inr)?\s*(?:se kam|ke andar|tak)", I)

# Words that carry no policy meaning; anything else not found in the policy text means "the policy doesn't cover that".
POLICY_FILLER = frozenset("""policy polici send sent give giving taking back money long take work cover day time free after before during over from if when where who why whether been being delivered received arrived bought purchased ordered placed opened used worn unused still ago since pay paying paid fee fees charge charges cost costs rupee rupees will would should could
were will shall must should might may because then there here other another each every some all just very not nor
return refund exchange replacement shipping ship delivery deliver warranty guarantee cancel cancellation cancelled order
kitne kitna kitni din milega milegi milta hoga hogi kab kaise wapas paisa paise""".split())


def parse_budget(text: str):
    """Upper price limit in rupees ("under 3000", "under 2k", "between 500 and 1000" -> 1000), or None."""
    lo, hi = nlu.parse_range(text)
    if hi is not None:
        return hi
    m = BUDGET.search(text)
    return float(next(g for g in m.groups() if g).replace(",", "")) if m else None


def price_bounds(text: str):
    """(low, high) limits stated in the text; either may be None."""
    lo, hi = nlu.parse_range(text)
    return lo, (hi if hi is not None else parse_budget(text))


def strip_budget(text: str) -> str:
    return BUDGET.sub(" ", nlu.strip_price(text))


def _norm_options(items, prefix: str, default_type: str) -> list[dict]:
    """The single Option shape used for both `options` (choices) and `followups` (next steps). Every key is always present.
       {id, type: choice|suggestion|action, label, detail, query, action: view_product|compare|add_to_cart|null, product_ids[]}"""
    out = []
    for i, o in enumerate(items, 1):
        t = o.get("type") or ("action" if o.get("action") else default_type)
        out.append({"id": f"{prefix}-{i}", "type": t, "label": str(o["label"]), "detail": o.get("detail"), "query": o.get("query"),
                    "action": o.get("action"), "product_ids": list(o.get("product_ids") or [])})
    return out


def money(v: float) -> str:
    return money_mod.text(money_mod.to_paise(v))


@dataclass
class Ctx:
    terms: list = field(default_factory=list)
    attrs: set = field(default_factory=set)
    budget: float | None = None
    min_budget: float | None = None
    in_stock: bool = False
    shown: list = field(default_factory=list)
    concepts: list = field(default_factory=list)      # [(label, frozenset(tokens))] needs expressed in the shopper's words
    audience: list = field(default_factory=list)       # "men", "dad", ... the catalogue does not record these
    focus: str | None = None                           # the one product the conversation is currently about

    def reset_search(self):
        self.terms, self.attrs, self.budget, self.min_budget, self.in_stock = [], set(), None, None, False
        self.concepts, self.audience = [], []

    def public(self) -> dict:
        return {"terms": list(self.terms), "attributes": sorted(self.attrs), "max_price": self.budget, "min_price": self.min_budget,
                "in_stock": self.in_stock, "needs": [c[0] for c in self.concepts], "focus": self.focus}


# Words that are units / packaging, not the noun that names a product ("Pack of 2", "24 cm").
UNIT_TOKENS = frozenset("cm mm ml l g kg w mah set pack pair of".split())
NEGATIVE = frozenset({"no", "false", "none", "not available"})
NEGATED = re.compile(r"^(?:no|not|without|never|does not|doesn't|cannot|can't)\b", I)
GLOBAL = re.compile(r"\b(you (?:sell|have|stock|carry)|in the store|in your store|overall|entire|whole|catalogue|catalog|anything|everything|thing|product)\b", I)
EXISTENCE = re.compile(r"\b(do you|have you|are there|is there|got any|any)\b", I)
COLOUR_Q = nlu.COLOUR_ASK
# Phrases that start a NEW product request, so a follow-up about the focused product must not swallow them.
NEW_REQUEST = re.compile(r"\b(?:do|does|did) (?:you|u|this store|the store|they) (?:sell|have|stock|carry|offer)\b|\b(?:have you got|got any|are there any|is there any|looking for|show me|i(?:'m| am)? looking)\b", I)
PROTECTED = frozenset("cart basket track order orders where which first second third fourth last these those them both".split())
NUMUNIT = frozenset("inch inches cm mm kg g hour hours min".split())
GENDER = frozenset("men mens man male women womens woman female ladies lady boys boy girls girl kids kid children child baby toddler unisex".split())


class Assistant:
    def __init__(self, products: list[Product], sections: list[Section]):
        self.products = products
        self.sections = sections
        self.by_id = {p.id: p for p in products}
        self.id_lower = {p.id.lower(): p.id for p in products}
        self.sec_by_id = {s.id: s for s in sections}

        def positive(p: Product):
            """Attribute text that is positive evidence. "Wireless: No" must not make a wired product match "wireless"."""
            keys, vals = [], []
            for k, v in p.attributes.items():
                if str(v).strip().lower() in NEGATIVE:
                    continue
                keys.append(k)
                vals.append(str(v))
            return " ".join(keys), " ".join(vals)

        # Stop-word-free vocabulary first (no typo correction while indexing), then tokenise with it.
        docs = []
        for p in products:
            ks, vs = positive(p)
            pos_text = lambda t: " ".join(x for x in re.split(r"(?<=[.!?])\s+", t) if not NEGATED.match(x.strip()))
            docs.append(tokenize(f"{p.title} {p.title} {p.brand} {p.category} {p.subcategory} {ks} {vs} "
                                 f"{' '.join(p.use_cases)} {' '.join(pos_text(h) for h in p.highlights)} {pos_text(p.description)}"))
        self.index = BM25(docs)
        self.ptoks = [set(d) for d in docs]
        self.title_toks = [set(tokenize(p.title)) for p in products]
        self.heads = [self._head(p) for p in products]
        self.head_vocab = set().union(*self.heads) if products else set()
        self.pol_index = BM25([tokenize(f"{s.title} {s.title} {s.text}") for s in sections])
        self.attr_vocab = {t for p in products for k, v in p.attributes.items() if k.lower() in ATTR_KEYS for t in tokenize(v)} | set(COLOURS)
        self.colour_vocab = {t for p in products for k, v in p.attributes.items() if k.lower() in ("colour", "color") for x in str(v).split(",") for t in tokenize(x)} | set(COLOURS)
        self.use_vocab = {t for p in products for u in p.use_cases for t in tokenize(u)}
        self.key_vocab = {t for p in products for k in p.attributes for t in tokenize(k)}
        self.pos = {p.id: i for i, p in enumerate(products)}
        self.categories = sorted({p.category for p in products if p.category})
        self.categories_tokens = {t for c in self.categories for t in tokenize(c)}
        self.fix_vocab = frozenset(self.index.vocab) | frozenset(tokenize(" ".join(POLICY_WORDS)))
        self.head_index: dict[str, list[int]] = {}
        for i, hs in enumerate(self.heads):
            for t in hs:
                self.head_index.setdefault(t, []).append(i)

    @staticmethod
    def _head(p: Product) -> set:
        """Tokens naming WHAT the product is: its subcategory, category and the last real word of its title ("Metro Laptop Backpack 25 L" -> backpack)."""
        alpha = [t for t in tokenize(re.sub(r"\(.*?\)", " ", p.title)) if t.isalpha() and t not in UNIT_TOKENS]
        return set(tokenize(p.subcategory)) | set(tokenize(p.category)) | set(alpha[-1:])

    # ---------- public ----------
    def tok(self, text: str) -> list[str]:
        out = []
        for t in tokenize(text, self.index.vocab):
            if t not in self.index.vocab and t.isalpha() and len(t) > 5 and t.endswith("ing"):      # "studying" -> study, "travelling" -> travel
                t = next((c for c in (t[:-3], t[:-3] + "e", t[:-4]) if c in self.index.vocab), t)
            out.append(t)
        return out

    def fix_typos(self, text: str) -> str:
        """Repair misspellings of catalogue / policy words before routing ("noice cancelling headfones", "retrun policy").
        Same safety rule as retrieval.correct(): only when exactly one close known word exists, same first letter."""
        def fix(m):
            w = m.group(0)
            lw = w.lower()
            if len(lw) < 5 or lw in PROTECTED or lw in STOP or lw in COLOURS or lw in SYNONYMS or lw in nlu.AUDIENCE or lw in POLICY_WORDS or nlu.extract_concepts(lw)[1]:
                return w
            st = lw[:-1] if len(lw) > 3 and lw.endswith("s") and not lw.endswith("ss") else lw
            if st in self.fix_vocab or st in self.pol_index.vocab:
                return w
            c = correct(st, self.fix_vocab)
            if c == st:
                c = correct(lw, self.fix_vocab)            # "wireles": the trailing s is part of the typo, not a plural
            return c if c not in (st, lw) else w
        return re.sub(r"[A-Za-z]{4,}", fix, text)

    def respond(self, message: str, history: list[str] | None = None) -> dict:
        ctx = Ctx()
        for h in (history or [])[-6:]:        # replay earlier user turns to rebuild constraints deterministically
            self._route(" ".join(str(h).split())[:500], ctx)
        return self._route(" ".join(message.split()), ctx)

    # ---------- routing ----------
    def _route(self, text: str, ctx: Ctx) -> dict:
        low = self.fix_typos(text)
        kind = nlu.smalltalk_kind(low)
        if kind:
            return self._smalltalk(kind, ctx)
        low = nlu.LEADING_GREETING.sub("", low) or low
        policyish = bool(POLICY.search(low) or nlu.DAMAGE.search(low) or nlu.SEND_BACK.search(low))
        hard = [m.group(0).lower() for m in UNSUPPORTED.finditer(low)]
        if hard and not (policyish and all(h in ("my order", "my orders") for h in hard)):
            return self._reply(ctx, "refused", "I can't look up orders, payments, accounts, discounts or offers — I only answer from the product catalogue and the store policy, "
                               "so I have no record to cite for those. Your orders and account details are under Account in the menu.")
        ids = self._find_ids(strip_budget(low))
        refs, rest = nlu.parse_refs(low)
        shown_prods = self._ref_products(refs, ctx)
        if shown_prods and any(t in self.head_vocab for t in self.tok(strip_budget(rest))):
            shown_prods = []                    # "a bottle that keeps water cold": "that" is not a reference when a new product type is named
        if COMPARE.search(low) or len(ids) >= 2:
            if len(ids) < 2 and len(shown_prods) >= 2:          # "compare the first two", "compare these"
                return self._compare_products(shown_prods[:MAX_COMPARE], ctx)
            return self._compare(low, ids, ctx)
        subject = self.by_id[ids[0]] if ids else (shown_prods[0] if len(shown_prods) == 1 else None)
        if policyish:
            return self._policy(low, ctx, subject)
        if nlu.CART.search(low):
            return self._cart(subject or (self.by_id.get(ctx.focus) if ctx.focus else None) or (self.by_id[ctx.shown[0]] if len(ctx.shown) == 1 else None), ctx)
        if subject:
            return self._about(subject, rest if shown_prods else low, ctx)
        rk = self._rank_intent(low, ctx)
        if rk:
            return self._rank(low, ctx, rk)
        if BETTER.search(low) and not (CHEAP.search(low) or TOPRATED.search(low)):
            parsed = self._parse(low)
            if not parsed["topic"]:
                return self._better(ctx)
        parsed = self._parse(low)
        if (CHEAP.search(low) or TOPRATED.search(low)) and ctx.shown and not parsed["topic"] and not parsed["attr"] and not parsed["concepts"]:
            return self._superlative(low, ctx)
        if BETTER.search(low) and not parsed["topic"]:
            return self._better(ctx)
        # A follow-up question about the one product we are discussing ("and how long is the battery?", "is it good for the gym?")
        if (ctx.focus in self.by_id and not any(t in self.head_vocab for t in parsed["topic"]) and parsed["budget"] is None and parsed["min_budget"] is None
                and not LISTING.search(low) and not NEW_REQUEST.search(low) and (parsed["topic"] or parsed["size"] or parsed["concepts"] or COLOUR_Q.search(low)) and not (parsed["attr"] and not nlu.QUESTION.search(low))):
            return self._feature(self.by_id[ctx.focus], low, ctx)
        return self._search(low, ctx, parsed)

    def _parse(self, text: str) -> dict:
        low = strip_budget(text)
        size = nlu.SIZE_Q.search(low)
        if size:
            low = nlu.SIZE_Q.sub(" ", low)
        low, concepts = nlu.extract_concepts(low)
        toks = self.tok(low)
        lo, hi = price_bounds(text)
        gender = [t for t in toks if t in GENDER]
        recipient = [t for t in toks if t in nlu.AUDIENCE and t not in GENDER]
        toks = [t for t in toks if t not in nlu.AUDIENCE]
        if concepts or any(t in self.head_vocab for t in toks if t not in nlu.SOFT):
            toks = [t for t in toks if t not in nlu.SOFT]          # "phone charger": phone is context, charger is the product
        return {"budget": hi, "min_budget": lo, "toks": toks, "concepts": concepts, "gender": gender, "recipient": recipient,
                "size": (size.group(1) or size.group(2)).upper() if size else None,
                "attr": [t for t in toks if t in self.attr_vocab], "topic": [t for t in toks if t not in self.attr_vocab]}

    def _find_ids(self, text: str) -> list[str]:
        found = []
        for t in re.findall(r"[a-z0-9][a-z0-9_\-]*", text.lower()):
            pid = self.id_lower.get(t)
            if pid and pid not in found and (len(t) >= 4 or not t.isdigit()):
                found.append(pid)
        return found

    def _ref_products(self, refs: dict, ctx: Ctx) -> list[Product]:
        """The earlier result(s) a message points at: "the first one", "the first two", "these", "it"."""
        shown = [self.by_id[i] for i in ctx.shown if i in self.by_id]
        if refs["n"]:
            return shown[:refs["n"]]
        if refs["indexes"]:
            out = []
            for ix in refs["indexes"]:
                try:
                    out.append(shown[ix])
                except IndexError:
                    pass
            return out
        if refs["plural"]:
            return shown[:MAX_COMPARE]
        if refs["single"]:
            if ctx.focus in self.by_id:
                return [self.by_id[ctx.focus]]
            if len(shown) == 1:
                return shown
        return []

    # ---------- building blocks ----------
    def _card(self, p: Product, matched=None) -> dict:
        c = {"id": p.id, "title": p.title, "category": p.category, "price": p.price,
             "price_text": money(p.price) if p.price is not None else "Price not listed",
             "stock": p.stock, "stock_text": {"in_stock": "In stock", "out_of_stock": "Out of stock"}.get(p.stock, "Stock not listed"),
             "rating": p.rating, "attributes": dict(list(p.attributes.items())[:4]), "image": p.image,
             "description": p.description[:300], "brand": p.brand, "subcategory": p.subcategory}
        if matched:
            c["matched_on"] = matched
        return c

    def full_record(self, p: Product) -> dict:
        return {**self._card(p), "attributes": dict(p.attributes), "description": p.description}

    def _citation(self, cid: str) -> dict:
        if cid in self.by_id:
            p = self.by_id[cid]
            c = self._card(p)
            return {"id": cid, "kind": "product", "label": p.title, "snippet": f"{p.category or 'Product'} · {c['price_text']} · {c['stock_text']}",
                    "source": "Product catalogue", "url": "#/product/" + quote(cid, safe=""), "fields": [], "record": self.full_record(p)}
        s = self.sec_by_id[cid]
        return {"id": cid, "kind": "policy", "label": f"Policy: {s.title}", "snippet": s.text[:400], "source": "Store policy", "url": "#/policies",
                "fields": [], "record": {"title": s.title, "text": s.text}}

    def _fields_used(self, message: str, cites) -> dict:
        """Which record fields the answer text actually states (for the evidence explorer)."""
        out = {}
        low = message.lower()
        for cid in dict.fromkeys(cites):
            p = self.by_id.get(cid)
            if not p:
                continue
            used = []
            if p.price is not None and money(p.price) in message:
                used.append("price")
            if "stock" in low:
                used.append("stock")
            if "rated" in low or "rating" in low or "/5" in message:
                used.append("rating")
            used += [k for k, v in p.attributes.items() if f"{k}: {v}" in message or (v and v in message and len(v) > 3)]
            out[cid] = list(dict.fromkeys(used))
        return out

    def _reply(self, ctx, status, message, *, products=(), comparison=None, options=(), cites=(), matched=None, followups=None, evidence=None):
        if products:
            ctx.shown = [p.id for p in products]
            ctx.focus = products[0].id if len(products) == 1 else None
        matched = matched or {}
        used = self._fields_used(message, cites)
        res = {"status": status, "message": message, "products": [self._card(p, matched.get(p.id)) for p in products],
               "comparison": comparison, "options": _norm_options(options, "opt", "choice"),
               "citations": [self._citation(c) | {"fields": used.get(c, [])} for c in dict.fromkeys(cites)], "context": ctx.public(),
               "evidence": {"fields_used": used, "excluded": [], "missing": [], "reason": "", **(evidence or {})}}
        res["followups"] = _norm_options(followups if followups is not None else self._followups(res, ctx), "fu", "suggestion")
        return res

    def _followups(self, res: dict, ctx: Ctx) -> list[dict]:
        out, prods = [], [self.by_id[p["id"]] for p in res["products"]]
        if res["status"] == "answer" and len(prods) >= 2:
            out.append({"label": f"Compare {prods[0].id} and {prods[1].id}", "query": f"compare {prods[0].id} and {prods[1].id}"})
            out.append({"type": "action", "action": "compare", "label": f"Open compare studio ({min(len(prods), 4)})", "product_ids": [p.id for p in prods[:4]]})
        if res["status"] == "answer" and len(prods) >= 2 and ctx.terms:
            for key in ATTR_KEYS - {"color"}:
                vals = list(dict.fromkeys(x.strip() for p in prods for k, v in p.attributes.items() if k.lower() == key and v for x in v.split(",") if x.strip()))
                if len(vals) >= 2:
                    out += [{"label": f"Only {v}", "query": f"only {v}"} for v in vals[:2]]
                    break
            if not ctx.in_stock and any(p.stock == "out_of_stock" for p in prods):
                out.append({"label": "Only in stock", "query": "only in stock ones"})
        if res["status"] == "answer" and len(prods) == 1:
            out.append({"type": "action", "action": "view_product", "label": "View product page", "product_ids": [prods[0].id]})
            if prods[0].stock == "in_stock":
                out.append({"type": "action", "action": "add_to_cart", "label": "Add to cart", "product_ids": [prods[0].id]})
            out.append({"label": "Returns policy", "query": "What is your returns policy?"})
        if res["status"] in ("no_match", "refused", "clarify") and not res["options"]:
            cats = sorted({p.category for p in self.products if p.category})[:3]
            out += [{"label": f"Show {c}", "query": f"show {c}"} for c in cats]
        if res["status"] == "answer" and not prods and res["citations"]:
            out += [{"label": q, "query": q} for q in ("How long does shipping take?", "What does the warranty cover?", "What is your returns policy?")
                    if q.split()[-2].lower() not in res["message"].lower()][:2]
        return out[:5]

    def _summary(self, p: Product, text: str) -> str:
        parts = [money(p.price) if p.price is not None else "price not listed",
                 {"in_stock": "in stock", "out_of_stock": "out of stock"}.get(p.stock, "stock status not listed")]
        if p.rating is not None:
            parts.append(f"rated {p.rating:g}/5")
        out = f"{p.title}: {', '.join(parts)} [{p.id}]."
        asked = [k for k in p.attributes if set(tokenize(k)) & set(tokenize(text))]
        if asked and not SPEC.search(text):
            out += " " + "; ".join(f"{k}: {p.attributes[k]}" for k in asked) + f" [{p.id}]."
        have = {t for k in p.attributes for t in tokenize(k)} | set(tokenize(p.title))
        missing = [t for t in dict.fromkeys(tokenize(text)) if t in self.key_vocab and t not in have and not SPEC.search(text)]
        if missing:
            out += " " + " ".join(f"{t.capitalize()} isn't listed in the catalogue for this product [{p.id}]." for t in missing[:2])
        if SPEC.search(text):
            out += (" Specs: " + "; ".join(f"{k}: {v}" for k, v in p.attributes.items()) + f" [{p.id}].") if p.attributes else f" No specifications are listed [{p.id}]."
        return out

    def _options(self, cands: list[Product], text: str) -> list[dict]:
        verb = "stock of" if STOCK.search(text) else "price of"
        return [{"type": "choice", "label": p.title, "detail": f"{money(p.price) if p.price is not None else 'No price'} · {p.id}", "query": f"{verb} {p.id}", "product_ids": [p.id]}
                for p in cands[:4]]

    # ---------- paths ----------
    def _detail(self, p: Product, text: str, ctx: Ctx) -> dict:
        msg = self._summary(p, text)
        miss = re.findall(r"(\w+) isn't listed", msg)
        return self._reply(ctx, "answer", msg, products=[p], cites=[p.id], evidence={"missing": [f"{m} is not in the record for {p.id}" for m in miss]})

    def _subject_category(self, toks, subject: Product | None):
        """The category a policy question is about: the named product's, or the one every product called "shirt"/"shoe"/... shares."""
        if subject is not None:
            return subject.category
        cats = {self.products[i].category for t in toks for i in self.head_index.get(t, [])
                if t not in self.categories_tokens}
        return next(iter(cats)) if len(cats) == 1 else None

    def _policy_numbers(self, sec: Section, low: str):
        """Derived answers the policy text supports exactly: the return window and the shipping fee. None when the text has no such rule."""
        t, title = sec.text, sec.title.lower()
        w = re.search(r"within (\d+) days?", t, I)
        if title.startswith("return") and w:
            n = re.search(r"\b(\d+)\s*(?:days?|din)\b", low)
            if n:
                window, days = int(w.group(1)), int(n.group(1))
                inside = days < window if re.search(r"\bafter\s+\d+", low) else days <= window
                sent = next((x for x in re.split(r"(?<=[.!?])\s+", t) if "within" in x.lower()), t)
                return f"{'Yes' if inside else 'No'} — {days} days is {'within' if inside else 'outside'} the {window}-day return window [{sec.id}]. {sent} [{sec.id}]"
        thr = re.search(r"free on orders above rs\.?\s*(\d[\d,]*)", t, I)
        fee = re.search(r"flat (?:shipping )?fee of rs\.?\s*(\d[\d,]*)", t, I)
        if title.startswith("ship") and thr and fee:
            m = re.search(r"(?:₹|rs\.?\s*|inr\s*)(\d[\d,]*)|(\d[\d,]*)\s*(?:rs|rupees?|inr)?\s*(?:order|purchase|cart|basket)|(\d[\d,]*)\s*(?:rs|rupees?|inr)\b", low, I)
            if m:
                amt = float(next(g for g in m.groups() if g).replace(",", ""))
                limit, flat = float(thr.group(1).replace(",", "")), fee.group(1)
                cost = "free" if amt > limit else f"a flat Rs {flat}"
                return (f"Shipping is free on orders above Rs {thr.group(1)}; smaller orders pay a flat fee of Rs {flat} [{sec.id}]. "
                        f"For an order of {money(amt)}, shipping would be {cost} [{sec.id}].")
        return None

    def _policy(self, text: str, ctx: Ctx, subject: Product | None = None) -> dict:
        topics = {m.group(1).lower()[:4] for m in POLICY.finditer(text)}
        if not topics and nlu.SEND_BACK.search(text):
            topics = {"retu"}                                  # "send it back", "get my money back"
        if not topics and nlu.DAMAGE.search(text):
            topics = {"retu", "warr"}                          # "arrived damaged": look at returns and warranty
        q = tokenize(text)
        if {"retu", "ship"} <= topics and re.search(r"\b(pay|pays|paying|who|cost|charge|fee)\b", text, I):
            ret = next((x for x in self.sections if x.title.lower().startswith("return")), None)
            return self._reply(ctx, "refused", "The policy lists returns and shipping separately and doesn't say who pays to send an item back, so I can't confirm that."
                               + (f" For reference, the Returns policy says: {ret.text.split('. ')[0].rstrip('.')}. [{ret.id}]" if ret else ""), cites=[ret.id] if ret else [])
        cat = self._subject_category(q, subject)
        ranked = [i for i, _, _ in self.pol_index.search(q)]
        # "delivery" is the Shipping section, "refund"/"exchange" the Returns section, ...: prefer the section whose TITLE owns the topic
        owner = {"deli": "ship", "ship": "ship", "retu": "retu", "refu": "retu", "exch": "retu", "repl": "retu", "warr": "warr", "guar": "warr", "canc": "canc"}
        titles = {owner[t] for t in topics if t in owner}
        order = ranked + [j for j in range(len(self.sections)) if j not in ranked]
        order.sort(key=lambda j: 0 if self.sections[j].title.lower()[:4] in titles else 1)
        for i in order:
            sec = self.sections[i]
            hay = f"{sec.title} {sec.text}".lower()
            if sec.title.lower()[:4] not in titles and not any(t in hay for t in topics):
                continue
            sents = re.split(r"(?<=[.!?])\s+", sec.text)
            qs = set(q)
            pick = " ".join([x for x in sents if qs & set(tokenize(x))][:3] or sents[:2])
            known = lambda t: (t in self.pol_index.vocab or t in self.index.vocab or t in POLICY_FILLER
                               or (len(t) >= 5 and any(v.startswith(t[:5]) for v in self.pol_index.vocab | POLICY_FILLER)))
            unknown = [t for t in q if len(t) >= 4 and t.isalpha() and not known(t)]
            classes = {w for ws in POLICY_CLASS.values() for w in ws if w in hay}
            if classes:                                        # a class-specific policy (warranty): does it name this product's category?
                mine = [w for w in POLICY_CLASS.get(cat, ()) if w in hay]
                if mine:
                    pick = " ".join([x for x in sents if any(w in x.lower() for w in mine)][:2]) or pick
                elif cat or subject:
                    names = sorted({ws[0] for ws in POLICY_CLASS.values() if any(w in hay for w in ws)})
                    return self._reply(ctx, "refused", f"The {sec.title} policy only mentions {', '.join(names)}; it says nothing about "
                                       f"{(cat or 'this kind of product').lower()}, so I can't confirm any {sec.title.lower()} for it. For reference: {pick} [{sec.id}]", cites=[sec.id])
            if unknown:
                return self._reply(ctx, "refused", f"The policy document doesn't mention “{unknown[0]}”, so I can't confirm that. "
                                   f"For reference, the {sec.title} policy says: {pick} [{sec.id}]", cites=[sec.id])
            derived = self._policy_numbers(sec, text)
            if derived:
                return self._reply(ctx, "answer", derived, cites=[sec.id])
            return self._reply(ctx, "answer", f"From the {sec.title} policy: {pick} [{sec.id}]", cites=[sec.id])
        return self._reply(ctx, "refused", "The policy document doesn't cover that, so I can't answer it. "
                           "I can tell you what it says about returns, shipping and warranty.")

    def _better(self, ctx: Ctx) -> dict:
        shown = [self.by_id[i] for i in ctx.shown if i in self.by_id][:MAX_COMPARE]
        if len(shown) < 2:
            return self._reply(ctx, "clarify", "Better in what way, and compared to what? Tell me two products (names or IDs), or search first and then ask which one.")
        return self._compare_products(shown, ctx, "“Better” depends on what matters to you, so here is how the options differ.")

    def _superlative(self, text: str, ctx: Ctx) -> dict:
        shown = [self.by_id[i] for i in ctx.shown if i in self.by_id]
        if TOPRATED.search(text):
            pool = [p for p in shown if p.rating is not None]
            best = max((p.rating for p in pool), default=None)
            win = [p for p in pool if p.rating == best]
            what = lambda p: f"the highest listed rating ({p.rating:g}/5)"
        else:
            pool = [p for p in shown if p.price is not None]
            best = min((p.price for p in pool), default=None)
            win = [p for p in pool if p.price == best]
            what = lambda p: f"the lowest listed price ({money(p.price)})"
        if not win:
            return self._reply(ctx, "refused", "The products above don't have that information in the catalogue, so I can't rank them.", products=shown, cites=[p.id for p in shown])
        msg = " ".join(f"Among the products shown, {p.title} has {what(p)} [{p.id}]." for p in win)
        return self._reply(ctx, "answer", msg, products=win, cites=[p.id for p in win])

    # ---------- matching ----------
    def _match(self, terms, attrs, concepts):
        """[(product index, bm25 score, coverage)] for every product that holds all `attrs`; coverage = share of terms + needs it satisfies."""
        n = len(terms) + len(concepts)
        qtoks = list(dict.fromkeys([*terms, *sorted(attrs), *(t for _, ts in concepts for t in sorted(ts))]))
        out = []
        for i, score, _ in self.index.search(qtoks, 500):
            have = self.ptoks[i]
            if not all(a in have for a in attrs):
                continue
            ok = sum(t in have for t in terms) + sum(bool(ts & have) for _, ts in concepts)
            out.append((i, score, ok / n if n else 1.0))
        return out

    def _leader(self, terms):
        """The one product whose title / type words cover the most of the shopper's words (None when two tie)."""
        best, hits = 0, []
        for i in range(len(self.products)):
            n = sum(t in (self.title_toks[i] | self.heads[i]) for t in terms)
            if n < 2 and not any(t in self.heads[i] for t in terms):
                continue                       # one stray title word ("stretch" in "Stretch Slim Fit Jeans") does not name a product
            if n > best:
                best, hits = n, [i]
            elif n == best and n:
                hits.append(i)
        return hits[0] if best >= 1 and len(hits) == 1 else None

    def _asked_concepts(self, p: Product, parsed: dict):
        own = self.title_toks[self.pos[p.id]] | self.heads[self.pos[p.id]]
        return [(lbl, ts) for lbl, ts in parsed["concepts"] if not ts & own]       # "Rain Jacket": "rain" names the product, it is not a feature

    def _feature_terms(self, p: Product, parsed: dict) -> list[str]:
        own = self.title_toks[self.pos[p.id]] | self.heads[self.pos[p.id]] | set(tokenize(p.id)) | set(tokenize(p.brand))
        return [t for t in dict.fromkeys(parsed["toks"]) if t not in own and t not in self.colour_vocab and not t.isdigit() and t not in NUMUNIT]

    def _wants_feature(self, p: Product, text: str, parsed: dict) -> bool:
        own = self.title_toks[self.pos[p.id]] | self.heads[self.pos[p.id]]
        asked_colour = any(t in self.colour_vocab and t not in own for t in parsed["toks"])
        return bool(self._feature_terms(p, parsed) or self._asked_concepts(p, parsed) or parsed["size"] or asked_colour or COLOUR_Q.search(text) or nlu.SIZES_ASK.search(text))

    def _unknown(self, ctx: Ctx, words) -> dict:
        q = " ".join(words) or "that"
        return self._reply(ctx, "no_match", f"I couldn't find “{q}” in our catalogue. We stock {', '.join(self.categories)}. "
                           "Try a product name or category, or tell me what you need it for.")

    # ---------- search ----------
    def _search(self, text: str, ctx: Ctx, parsed: dict) -> dict:
        topic, attr, concepts = parsed["topic"], parsed["attr"], parsed["concepts"]
        if (topic or concepts) and not FOLLOW.search(text):      # a new request: drop old constraints so topics never mix
            ctx.reset_search()
            ctx.terms, ctx.attrs, ctx.concepts = list(dict.fromkeys(topic)), set(attr), list(concepts)
        else:                                                    # refinement: keep terms, add constraints
            if topic:
                ctx.terms = list(dict.fromkeys(topic))
            if concepts:
                ctx.concepts = list(concepts)
            ctx.attrs |= set(attr)
        if parsed["gender"] or parsed["recipient"]:
            ctx.audience = list(dict.fromkeys(parsed["gender"] + parsed["recipient"]))
        if parsed["budget"] is not None:
            ctx.budget = parsed["budget"]
        if parsed["min_budget"] is not None:
            ctx.min_budget = parsed["min_budget"]
        if INSTOCK.search(text):
            ctx.in_stock = True
        # A question about ONE named product ("does the kettle have auto shut-off?") is answered from that product's record.
        if ctx.terms and (nlu.QUESTION.search(text) or parsed["size"]) and parsed["budget"] is None and parsed["min_budget"] is None:
            lead = self._leader(ctx.terms)
            if lead is not None and self._wants_feature(self.products[lead], text, parsed):
                return self._feature(self.products[lead], text, ctx)
        price_only = not ctx.terms and not ctx.attrs and not ctx.concepts
        if price_only and not ((ctx.budget is not None or ctx.min_budget is not None) and re.search(r"\b(anything|everything|all|items?|products?|things?|stuff|something)\b", text, I)):
            if ctx.audience and not ctx.terms:
                return self._reply(ctx, "clarify", "The catalogue doesn't record whether a product is for men, women, kids or a particular person, so I can't filter by that. What kind of product are you after?")
            return self._reply(ctx, "clarify", "What would you like to know? Name a product or category, or ask about returns, shipping or warranty.")
        terms = list(ctx.terms) or (sorted(ctx.attrs) if not ctx.concepts else [])
        if price_only:
            scored = sorted(range(len(self.products)), key=lambda i: (-(self.products[i].rating or 0), self.products[i].price or 0))
            scored_all = [(i, 0.0, 1.0) for i in scored]
        else:
            scored_all = self._match(terms, ctx.attrs, ctx.concepts)
        full = [h for h in scored_all if h[2] == 1.0]
        anchored = lambda i: any(t in self.heads[i] for t in terms) or any(ts & self.ptoks[i] for _, ts in ctx.concepts)
        near = [h for h in scored_all if h[2] >= 0.5 and (price_only or anchored(h[0]))]
        if not full:
            if not near:
                base = [h for h in self._match(list(ctx.terms), set(), ctx.concepts) if h[2] == 1.0] if (ctx.terms or ctx.concepts) else []
                if base and ctx.attrs:
                    alts = [self.products[i] for i, _, _ in base[:3]]
                    return self._reply(ctx, "no_match", f"Nothing in the catalogue matches “{' '.join(ctx.terms)}” together with {', '.join(sorted(ctx.attrs))}. "
                                       f"Without that constraint, the closest products are: " + " ".join(f"[{p.id}]" for p in alts), products=alts, cites=[p.id for p in alts])
                return self._unknown(ctx, [*ctx.terms, *[c[0] for c in ctx.concepts], *sorted(ctx.attrs)])
            cands = [self.products[i] for i, _, _ in near[:4]]
            top = near[0][0]
            miss = [t for t in terms if t not in self.ptoks[top]] + [lbl for lbl, ts in ctx.concepts if not ts & self.ptoks[top]]
            return self._reply(ctx, "clarify", f"I couldn't find a product matching every word ({', '.join(miss) or 'some words'}). Is one of these close to what you want?",
                               options=self._options(cands, text), products=cands, cites=[p.id for p in cands],
                               evidence={"reason": "No product matches every word, only some of them, so I won't present a partial match as the answer."})
        in_titles = lambda t: any(t in self.title_toks[i] for i, _, _ in full)
        plural_nouns = [t for t in terms if re.search(rf"\b{re.escape(t)}s\b", text, I) and not any(t in self.heads[i] for i, _, _ in full)]
        if EXISTENCE.search(text) and plural_nouns and not ctx.concepts and len(terms) == 1 and not price_only:
            pool, what = [self.products[i] for i, _, _ in full], plural_nouns[0] + "s"
            return self._reply(ctx, "clarify", f"We don't sell {what} as a product, but {len(pool)} products are described as being for {what}. Is one of these what you meant?",
                               options=self._options(pool, text), products=pool[:4], cites=[p.id for p in pool[:4]],
                               evidence={"reason": f"“{what}” appears in these records only as a feature of a different kind of product."})
        asks_attr = (any(r.search(text) for r in (PRICE, STOCK, RATING, SPEC)) or any(t in self.key_vocab and not in_titles(t) for t in parsed["toks"])) and not INSTOCK.search(text) and not (CHEAP.search(text) or TOPRATED.search(text))
        if (asks_attr and not (LISTING.search(text) or parsed["budget"] is not None or parsed["min_budget"] is not None or ctx.concepts)) and not price_only:
            pool = [self.products[i] for i, _, _ in full]
            exact = [self.products[i] for i, _, _ in full if self.title_toks[i] == set(terms)]
            if len(pool) == 1 or len(exact) == 1:
                return self._detail((exact or pool)[0], text, ctx)
            return self._reply(ctx, "clarify", f"{len(pool)} products could match that, and they differ. Which one do you mean?",
                               options=self._options(pool, text), products=pool[:4], cites=[p.id for p in pool[:4]],
                               evidence={"reason": f"{len(pool)} products match “{' '.join(terms)}” equally well, so answering would mean guessing which one you meant."})
        found_idx = [i for i, _, _ in full]
        if CHEAP.search(text):
            found_idx.sort(key=lambda i: (self.products[i].price is None, self.products[i].price or 0))
        elif TOPRATED.search(text):
            found_idx.sort(key=lambda i: -(self.products[i].rating or 0))
        found = [self.products[i] for i in found_idx]
        excluded = []
        lo, hi = ctx.min_budget, ctx.budget
        bound = (f" between {money(lo)} and {money(hi)}" if lo is not None and hi is not None else f" at or under {money(hi)}" if hi is not None
                 else f" at or above {money(lo)}" if lo is not None else "")
        if bound:
            ok = lambda p: p.price is not None and (hi is None or p.price <= hi) and (lo is None or p.price >= lo)
            within = [p for p in found if ok(p)]
            within_ids = {p.id for p in within}
            excluded += [{"id": p.id, "title": p.title, "reason": ("No listed price" if p.price is None else f"Over budget: {money(p.price)} is above {money(hi)}" if hi is not None and p.price > hi
                                                                else f"Below the minimum: {money(p.price)} is under {money(lo)}")} for p in found if p.id not in within_ids][:6]
            if not within:
                priced = [p for p in found if p.price is not None]
                if priced and hi is not None and lo is None:
                    low = min(priced, key=lambda p: p.price)
                    return self._reply(ctx, "no_match", f"Nothing matching that is{bound}. The lowest-priced match is {low.title} at {money(low.price)} [{low.id}].", products=[low], cites=[low.id])
                if priced and lo is not None and hi is None:
                    high = max(priced, key=lambda p: p.price)
                    return self._reply(ctx, "no_match", f"Nothing matching that is{bound}. The highest-priced match is {high.title} at {money(high.price)} [{high.id}].", products=[high], cites=[high.id])
                if priced:
                    return self._reply(ctx, "no_match", f"Nothing matching that is{bound}. The matches are priced from {money(min(p.price for p in priced))} to {money(max(p.price for p in priced))} "
                                       + " ".join(f"[{p.id}]" for p in priced[:3]), products=priced[:3], cites=[p.id for p in priced[:3]])
                return self._reply(ctx, "no_match", f"No matching product has a listed price, so I can't confirm any are{bound}.")
            found = within
        if ctx.in_stock:
            avail = [p for p in found if p.stock == "in_stock"]
            avail_ids = {p.id for p in avail}
            excluded += [{"id": p.id, "title": p.title, "reason": "Out of stock" if p.stock == "out_of_stock" else "Stock status not listed"} for p in found if p.id not in avail_ids][:6]
            if not avail:
                return self._reply(ctx, "no_match", "Every matching product is currently out of stock or has no stock status: " + " ".join(f"[{p.id}]" for p in found[:5]),
                                   products=found[:5], cites=[p.id for p in found[:5]])
            found = avail
        shown = found[:5]
        cons = bound + (" and in stock" if ctx.in_stock and bound else " in stock" if ctx.in_stock else "")
        order = " (lowest price first)" if CHEAP.search(text) else " (highest rating first)" if TOPRATED.search(text) else ""
        msg = f"Found {len(found)} match{'es' if len(found) != 1 else ''}{cons}{order}; showing {len(shown)}: " + " ".join(f"[{p.id}]" for p in shown)
        reason = f"Matched on: {', '.join(dict.fromkeys([*terms, *sorted(ctx.attrs)]))}." if terms else "Matched on the price range only."
        for label, ts in ctx.concepts:
            reason += f" Need “{label}” matched to: {', '.join(sorted(ts))}."
            if ts != {label} and label not in ts:
                msg += f". I read “{label}” as {'/'.join(sorted(ts))}"
        if cons.strip():
            reason += " Constraints applied: " + cons.strip() + "."
        approx = [lbl for lbl, _ in ctx.concepts if lbl in nlu.APPROX]
        if approx:
            return self._reply(ctx, "clarify", f"Nothing is listed as “{approx[0]}”, but these are listed with related wording (water resistance): " + " ".join(f"[{p.id}]" for p in shown)
                               + ". Is that close enough?", products=shown, cites=[p.id for p in shown], options=self._options(shown, text),
                               evidence={"reason": reason + f" The catalogue says “resistant”, not “{approx[0]}”."})
        genders = [g for g in ctx.audience if g in GENDER]
        matched = {p.id: [t for t in dict.fromkeys([*terms, *sorted(ctx.attrs)]) if t in self.ptoks[self.pos[p.id]]] for p in shown}
        if genders:
            return self._reply(ctx, "clarify", f"The catalogue doesn't record whether a product is for men, women or kids, so I can't filter by “{genders[0]}”. "
                               f"These are the closest matches by product type: " + " ".join(f"[{p.id}]" for p in shown), products=shown, cites=[p.id for p in shown], matched=matched,
                               options=self._options(shown, text), evidence={"excluded": excluded[:8], "reason": reason + " No gender or age field exists in the catalogue."})
        if ctx.audience:
            msg += ". The catalogue doesn't record who a product is for, so I haven't filtered by recipient"
        return self._reply(ctx, "answer", msg + ("." if msg[-1] != "." else ""), products=shown, cites=[p.id for p in shown], matched=matched,
                           evidence={"excluded": excluded[:8], "reason": reason})

    # ---------- questions about one product ----------
    def _about(self, p: Product, text: str, ctx: Ctx) -> dict:
        """A message that names (or points at) one product: a feature question is answered from its record, anything else gets the summary."""
        parsed = self._parse(text)
        if self._wants_feature(p, text, parsed) and (nlu.QUESTION.search(text) or parsed["size"] or self._asked_concepts(p, parsed)):
            return self._feature(p, text, ctx)
        return self._detail(p, text, ctx)

    @staticmethod
    def _opts(p: Product, key: str) -> list[str]:
        for k, v in p.attributes.items():
            if k.lower() in (key, "color" if key == "colour" else key) and v:
                return [x.strip() for x in str(v).split(",") if x.strip()]
        return []

    def _facts(self, p: Product):
        out = [f"{k}: {v}" for k, v in p.attributes.items() if v]
        out += [h for h in p.highlights if h]
        out += [x.strip() for x in re.split(r"(?<=[.!?])\s+", p.description) if x.strip()]
        if p.use_cases:
            out.append("Listed uses: " + ", ".join(p.use_cases))
        return [(f, set(tokenize(f))) for f in out]

    def _feature(self, p: Product, text: str, ctx: Ctx) -> dict:
        """Answer a question about ONE product strictly from its own record: laptop fit, sizes, colours, or any listed feature/spec."""
        parsed = self._parse(text)
        low = text.lower()
        own = self.title_toks[self.pos[p.id]] | self.heads[self.pos[p.id]]
        cite = f"[{p.id}]"

        def say(status, msg, **kw):
            return self._reply(ctx, status, msg, products=[p], cites=[p.id], **kw)
        lap = (p.specs or {}).get("laptop_max_inch") if isinstance(p.specs, dict) else None
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:inch(?:es)?|in\b|\")", low)
        if m and lap is not None and "laptop" in low and "fit" in low:
            want, yes = float(m.group(1)), float(m.group(1)) <= float(lap)
            return say("answer", f"{'Yes' if yes else 'No'} — {p.title} fits laptops up to {lap:g} inch, so a {want:g} inch laptop {'fits' if yes else 'is too large for it'} {cite}.")
        sizes = self._opts(p, "size")
        if parsed["size"] or nlu.SIZES_ASK.search(low):
            if not sizes:
                hit = next((f for f, _ in self._facts(p) if re.search(r"\bsize\b", f, I)), None) or (f"{p.title}" if re.search(r"\bsize\s+\w+$", p.title, I) else None)
                if hit:
                    return say("answer", f"{p.title}: {hit.rstrip('.')} {cite}." if hit != p.title else f"The listing names it as {p.title} {cite}.")
                return say("refused", f"No sizes are listed for {p.title} {cite}.")
            if parsed["size"]:
                yes = parsed["size"] in {x.upper() for x in sizes}
                return say("answer", (f"Yes — {p.title} is listed in size {parsed['size']}. Listed sizes: {', '.join(sizes)} {cite}." if yes else
                                      f"No — size {parsed['size']} isn't among the sizes listed for {p.title}: {', '.join(sizes)} {cite}."))
            return say("answer", f"{p.title} is listed in sizes {', '.join(sizes)} {cite}.")
        colours = self._opts(p, "colour")
        asked = [t for t in parsed["toks"] if t in self.colour_vocab and t not in own]
        if asked or COLOUR_Q.search(low):
            if not colours:
                return say("refused", f"No colours are listed for {p.title} {cite}.")
            have = {t for c in colours for t in tokenize(c)}
            if asked:
                yes = all(t in have for t in asked)
                return say("answer", (f"Yes — {p.title} is listed in {', '.join(asked)}. Listed colours: {', '.join(colours)} {cite}." if yes else
                                      f"No — {p.title} isn't listed in {', '.join(asked)}. Listed colours: {', '.join(colours)} {cite}."))
            return say("answer", f"{p.title} is listed in {', '.join(colours)} {cite}.")
        concepts = self._asked_concepts(p, parsed)
        need, groups = self._feature_terms(p, parsed), [ts for _, ts in concepts]
        if not need and not groups:
            return self._detail(p, text, ctx)
        facts = self._facts(p)
        direct = [f for f, ft in facts if all(t in ft for t in need) and all(g & ft for g in groups)]
        if not direct and all(any(t in ft for _, ft in facts) for t in need) and all(any(g & ft for _, ft in facts) for g in groups):
            direct = [f for f, ft in facts if any(t in ft for t in need) or any(g & ft for g in groups)][:2]
        if direct:
            top = direct[:1]
            asked_q = bool(nlu.QUESTION.search(text))
            lead = "No — " if asked_q and (re.search(r":\s*no$", top[0], I) or NEGATED.match(top[0])) else "Yes — " if asked_q and re.search(r":\s*yes$", top[0], I) else ""
            msg = f"{lead}{p.title}: {'; '.join(x.rstrip('.') for x in top)} {cite}."
            seen = set().union(*(ft for f, ft in facts if f in top))
            for label, _ in concepts:
                if not set(tokenize(label)) <= seen:
                    msg += f" The catalogue doesn't use the word “{label}”; this is the closest listed wording."
            return say("answer", msg, evidence={"reason": f"Found in the record of {p.id}: " + "; ".join(top)})
        phrase = " ".join(need or [lbl for lbl, _ in concepts])
        listed = "; ".join(f"{k}: {v}" for k, v in list(p.attributes.items())[:3])
        uses = f" Its listed uses are: {', '.join(p.use_cases)}." if p.use_cases and any(t in self.use_vocab for t in need) else ""
        return say("refused", f"The catalogue doesn't list “{phrase}” for {p.title} {cite}.{uses}" + (f" It does list: {listed} {cite}." if listed else ""),
                   evidence={"missing": [f"“{phrase}” is not in the record for {p.id}"]})

    def _cart(self, p: Product | None, ctx: Ctx) -> dict:
        if p is None:
            return self._reply(ctx, "clarify", "Which product should I add? Search for it first, or give me its product ID.")
        price = money(p.price) if p.price is not None else "price not listed"
        stock = {"in_stock": "in stock", "out_of_stock": "out of stock"}.get(p.stock, "stock not listed")
        return self._reply(ctx, "answer", f"I can't change your cart from chat, but {p.title} is {price} and {stock} [{p.id}]. Use the button below to add it yourself.", products=[p], cites=[p.id])

    # ---------- ranking ("longest battery", "most expensive", "cheapest thing you sell") ----------
    def _rank_intent(self, low: str, ctx: Ctx):
        spec = nlu.parse_rank(low)
        if spec:
            return {"kind": "spec", **spec}
        if nlu.PRICEY.search(low):
            return {"kind": "price", "dir": "max", "label": "price", "rest": nlu.PRICEY.sub(" ", low)}
        for rx, kind, d in ((CHEAP, "price", "min"), (TOPRATED, "rating", "max")):
            if rx.search(low):
                rest = rx.sub(" ", low)
                parsed = self._parse(rest)
                if not (parsed["topic"] or parsed["concepts"] or parsed["attr"]) and (not ctx.shown or GLOBAL.search(low)):
                    return {"kind": kind, "dir": d, "label": kind, "rest": rest}
        return None

    def _rank(self, low: str, ctx: Ctx, rk: dict) -> dict:
        parsed = self._parse(rk["rest"])
        topic, attrs, concepts = parsed["topic"], parsed["attr"], parsed["concepts"]
        scope = "Among the products shown"
        if topic or attrs or concepts:
            terms = list(dict.fromkeys(topic)) or sorted(attrs)
            hits = [h for h in self._match(terms, set(attrs) if topic else set(), concepts) if h[2] == 1.0]
            pool = [self.products[i] for i, _, _ in hits]
            if not pool:
                return self._unknown(ctx, [*terms, *[c[0] for c in concepts]])
            ctx.terms, ctx.concepts = list(terms), list(concepts)
            scope = f"Among the {len(pool)} matching product{'s' if len(pool) != 1 else ''}"
        elif ctx.shown and not GLOBAL.search(low):
            pool = [self.products[i] for i in (self.pos[x] for x in ctx.shown if x in self.pos)]
        else:
            pool, scope = list(self.products), "Across the whole catalogue"
        lo, hi = parsed["min_budget"], parsed["budget"]
        if lo is not None or hi is not None:
            pool = [p for p in pool if p.price is not None and (hi is None or p.price <= hi) and (lo is None or p.price >= lo)]
        kind, direction = rk["kind"], rk["dir"]
        if kind == "price":
            val, fmt, label = (lambda p: p.price), (lambda v: money(v)), "price"
        elif kind == "rating":
            val, fmt, label = (lambda p: p.rating), (lambda v: f"{v:g}/5"), "rating"
        else:
            counts = {k: sum(specs_mod.is_number((p.specs or {}).get(k)) for p in pool) for k in rk["keys"]}
            key = max(counts, key=counts.get) if counts and max(counts.values()) > 0 else None
            if key is None:
                return self._reply(ctx, "refused", f"The catalogue doesn't list {rk['label']} for these products, so I can't rank them.", products=pool[:3], cites=[p.id for p in pool[:3]])
            val, fmt, label = (lambda p, k=key: (p.specs or {}).get(k) if specs_mod.is_number((p.specs or {}).get(k)) else None), (lambda v, k=key: specs_mod.fmt(k, v)), specs_mod.label(key).lower()
        valued = [p for p in pool if val(p) is not None]
        if not valued:
            return self._reply(ctx, "refused", f"None of those products has a listed {label}, so I can't rank them.", products=pool[:3], cites=[p.id for p in pool[:3]])
        ranked = sorted(valued, key=lambda p: (val(p), p.id), reverse=(direction == "max"))
        best = val(ranked[0])
        winners = [p for p in ranked if val(p) == best]
        adj = {"max": {"battery life": "longest", "keeps cold/hot": "longest", "weight": "heaviest", "size": "largest", "volume": "largest", "capacity": "largest"},
               "min": {"weight": "lightest", "charging time": "shortest", "battery life": "shortest"}}[direction].get(label, "highest" if direction == "max" else "lowest")
        msg = f"{scope}, " + " ".join(f"{p.title} has the {adj} listed {label} ({fmt(val(p))}) [{p.id}]." for p in winners[:3])
        rest = [p for p in ranked if val(p) != best][:2]
        if rest:
            msg += " Next: " + "; ".join(f"{p.title} ({fmt(val(p))}) [{p.id}]" for p in rest) + "."
        missing = [p for p in pool if val(p) is None]
        if missing and kind == "spec":
            msg += f" {len(missing)} other matching product{'s' if len(missing) != 1 else ''} {'don' if len(missing) != 1 else 'doesn'}'t list {label}."
        shown = (winners + rest)[:4]
        return self._reply(ctx, "answer", msg, products=shown, cites=[p.id for p in shown],
                           evidence={"missing": [f"{p.id} has no {label} listed" for p in missing[:6]], "reason": f"Ranked {len(valued)} products by listed {label} ({'highest' if direction == 'max' else 'lowest'} first)."})

    # ---------- small talk ----------
    def _smalltalk(self, kind: str, ctx: Ctx) -> dict:
        cats = ", ".join(self.categories)
        scope = ("I can find and compare products, check specs, sizes and stock, and answer questions about returns, shipping, warranty and cancellations — "
                 "always from the catalogue and the store policy.")
        if kind == "greeting":
            return self._reply(ctx, "clarify", f"Hi! I'm Verity, this store's shopping assistant. {scope} What are you looking for today?")
        if kind == "thanks":
            return self._reply(ctx, "clarify", "You're welcome! Is there anything else you'd like to find or check?")
        if kind == "bye":
            return self._reply(ctx, "clarify", "Goodbye! Come back any time you need help finding something.")
        if kind == "identity":
            return self._reply(ctx, "clarify", f"I'm Verity, an automated shopping assistant for this store — not a person. {scope}")
        if kind == "help":
            return self._reply(ctx, "clarify", f"We stock {cats}. {scope} Tell me what you need — for example “headphones under 3000” or “something to carry my laptop”.")
        return self._reply(ctx, "refused", "That's outside what I can help with — I'm a shopping assistant, so I only answer questions about this store's products and policies. "
                           "Want to browse a category, or ask about returns, shipping or warranty?")

    # ---------- compare ----------
    def _compare(self, text: str, ids: list[str], ctx: Ctx) -> dict:
        if len(ids) >= 2:
            return self._compare_products([self.by_id[i] for i in ids[:MAX_COMPARE]], ctx)
        body = re.sub(r"\b(compare|comparison|difference|between)\b", " ", text, flags=I)
        parts = [p for p in re.split(r"\bvs\.?\b|\bversus\b", body, flags=I) if self.tok(p)]
        if len(parts) < 2:
            parts = [p for p in re.split(r"\band\b|,", body, flags=I) if self.tok(p)]
        if len(parts) < 2:
            return self._reply(ctx, "clarify", "Which products should I compare? Give two or more names or product IDs.")
        prods = []
        for part in parts[:MAX_COMPARE]:
            toks = self.tok(part)
            hits = [h for h in self.index.search(toks, 200) if h[2] >= MIN_COVERAGE]
            full = [h for h in hits if h[2] == 1.0]
            if not hits:
                return self._reply(ctx, "no_match", f"I don't have “{part.strip()}” in our catalogue, so I can't compare it.")
            pool = full or hits
            exact = [h for h in pool if self.title_toks[h[0]] == set(toks)]
            if len(pool) > 1 and len(exact) != 1:
                cands = [self.products[h[0]] for h in pool]
                prev = prods[0].id if prods else None
                opts = [{**o, "query": f"compare {o['detail'].split(' · ')[-1]} and {prev}" if prev else o["detail"].split(" · ")[-1]} for o in self._options(cands, "")]
                return self._reply(ctx, "clarify", f"“{part.strip()}” matches {len(pool)} products. Which one do you mean?", options=opts, products=cands[:4], cites=[p.id for p in cands[:4]])
            prods.append(self.products[(exact or pool)[0][0]])
        if len({p.id for p in prods}) < len(prods):
            return self._reply(ctx, "clarify", "Those look like the same product. Which different products should I compare?")
        return self._compare_products(prods, ctx)

    def comparison_table(self, prods: list[Product]) -> dict:
        """Comparison schema (also returned by /api/compare):
           {columns: [{id, title, brand, price_text, stock_text, image, url}],
            rows:    [{key, label, group: overview|features|details, values: [str per column], differs: bool}]}
           Missing data is the literal "Not listed", never a guess."""
        def row(key, label, vals, group):
            return {"key": key, "label": label, "group": group, "values": vals, "differs": len(set(vals)) > 1}
        keys = list(dict.fromkeys(k for p in prods for k in p.attributes))[:8]
        rows = [row("price", "Price", [money(p.price) if p.price is not None else NA for p in prods], "overview"),
                row("availability", "Availability", [self._card(p)["stock_text"] if p.stock != "unknown" else NA for p in prods], "overview"),
                row("rating", "Rating", [f"{p.rating:g}/5" if p.rating is not None else NA for p in prods], "overview"),
                row("category", "Category", [p.category or NA for p in prods], "overview"),
                *[row("attr-" + re.sub(r"[^a-z0-9]+", "-", k.lower()).strip("-"), k, [p.attributes.get(k, NA) for p in prods], "features") for k in keys]]
        if any(p.highlights for p in prods):
            rows.append(row("highlights", "Highlights", ["; ".join(p.highlights) if p.highlights else NA for p in prods], "features"))
        rows.append(row("description", "Description", [p.description or NA for p in prods], "details"))
        cols = [{"id": p.id, "title": p.title, "brand": p.brand, "price_text": money(p.price) if p.price is not None else NA, "stock_text": self._card(p)["stock_text"],
                 "image": p.image, "url": "#/product/" + quote(p.id, safe="")} for p in prods]
        return {"columns": cols, "rows": rows}

    def _compare_products(self, prods: list[Product], ctx: Ctx, preface: str = "") -> dict:
        names = " and ".join(f"{p.title} [{p.id}]" for p in prods) if len(prods) == 2 else ", ".join(f"{p.title} [{p.id}]" for p in prods)
        msg = (preface + " " if preface else "") + f"Comparing {names}."
        priced = [p for p in prods if p.price is not None]
        if len(priced) >= 2 and len({p.price for p in priced}) > 1:
            lo, hi = min(priced, key=lambda p: p.price), max(priced, key=lambda p: p.price)
            msg += (f" {lo.title} is {money(hi.price - lo.price)} cheaper [{lo.id}] [{hi.id}]." if len(prods) == 2
                    else f" Lowest listed price: {lo.title} at {money(lo.price)} [{lo.id}]. Highest: {hi.title} at {money(hi.price)} [{hi.id}].")
        rated = [p for p in prods if p.rating is not None]
        if len(rated) >= 2 and len({p.rating for p in rated}) > 1:
            top = max(rated, key=lambda p: p.rating)
            msg += f" Highest listed rating: {top.title} at {top.rating:g}/5 [{top.id}]."
        return self._reply(ctx, "answer", msg, products=prods, comparison=self.comparison_table(prods), cites=[p.id for p in prods])
