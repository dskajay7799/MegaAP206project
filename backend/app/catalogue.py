"""Loads and normalises the catalogue and policy document. Tolerant to common field names."""
import itertools
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config, specs as specs_mod

log = logging.getLogger("catalogue")
IMG_LOCAL = re.compile(r"^/assets/[A-Za-z0-9_./-]+$")

ALIASES = {
    "id": ("id", "product_id", "sku"),
    "title": ("title", "name"),
    "description": ("description", "desc"),
    "price": ("price", "price_inr", "mrp"),
    "stock": ("stock", "stock_status", "in_stock", "availability"),
    "category": ("category",),
    "rating": ("rating", "ratings", "avg_rating"),
    "attributes": ("attributes", "specs"),
    "image": ("image_url", "image"),
}


@dataclass
class Product:
    id: str
    title: str
    description: str = ""
    price: float | None = None
    stock: str = "unknown"  # in_stock | out_of_stock | unknown
    category: str = ""
    rating: float | None = None
    attributes: dict = field(default_factory=dict)
    image: str | None = None
    # --- storefront fields (all optional, so official R3 records keep loading unchanged) ---
    brand: str = ""
    subcategory: str = ""
    sku: str = ""
    specs: dict = field(default_factory=dict)          # typed values; see specs.py
    highlights: list = field(default_factory=list)
    use_cases: list = field(default_factory=list)
    images: list = field(default_factory=list)
    variants: list = field(default_factory=list)       # [{"sku","options":{...},"stock_qty":int}]
    options: dict = field(default_factory=dict)        # shorthand {"size":[...],"colour":[...]} expanded to variants on import
    stock_qty: int | None = None
    mrp: float | None = None
    featured: bool = False
    data_origin: str = "catalogue"
    added_days_ago: int | None = None
    option_stock: int | None = None
    unavailable: list = field(default_factory=list)
    created_at: object = None
    raw_attributes: dict = field(default_factory=dict)  # attributes exactly as supplied (before specs/options are merged in)
    price_history: list = field(default_factory=list)   # simulated demo observations: [{"days_ago": 40, "price": 4499}]


@dataclass
class Section:
    id: str
    title: str
    text: str


def expand_options(p: "Product") -> list[dict]:
    if p.variants:
        return [{"sku": v.get("sku") or f"{p.sku or p.id}-{i + 1}", "options": dict(v.get("options") or {}), "stock_qty": int(v.get("stock_qty", 0))}
                for i, v in enumerate(p.variants)]
    names = [n for n, vals in p.options.items() if isinstance(vals, list) and vals]
    if not names:                       # itertools.product() of nothing yields one empty combination: never invent a phantom variant
        return []
    out = []
    for combo in itertools.product(*[p.options[n] for n in names]):
        opts = dict(zip(names, combo))
        out_of_stock = any(all(opts.get(k) == v for k, v in u.items()) for u in p.unavailable)
        code = "-".join(re.sub(r"[^A-Za-z0-9]", "", str(v)).upper()[:6] for v in combo)
        out.append({"sku": f"{p.sku or p.id}-{code}", "options": opts, "stock_qty": 0 if out_of_stock else (p.option_stock if p.option_stock is not None else 5)})
    return out


def safe_image(url) -> bool:
    """Only https URLs or bundled /assets/ paths are accepted as images (no data:, javascript:, protocol-relative)."""
    return isinstance(url, str) and len(url) <= 500 and (url.startswith("https://") or bool(IMG_LOCAL.match(url))) and ".." not in url


def _pick(rec: dict, key: str):
    for name in ALIASES[key]:
        if name in rec and rec[name] not in (None, ""):
            return rec[name]
    return None


def _num(v):
    try:
        if isinstance(v, dict):
            v = next(iter(v.values()))
        return float(str(v).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError, StopIteration):
        return None


def _stock(v) -> str:
    if isinstance(v, bool):
        return "in_stock" if v else "out_of_stock"
    if isinstance(v, (int, float)):
        return "in_stock" if v > 0 else "out_of_stock"
    s = str(v or "").lower()
    if "out" in s or s in ("no", "false", "0", "unavailable"):
        return "out_of_stock"
    if "in" in s or s in ("yes", "true", "available"):
        return "in_stock"
    return "unknown"


def _product(rec: dict) -> Product | None:
    pid, title = _pick(rec, "id"), _pick(rec, "title")
    if pid is None or title is None:
        return None
    # Storefront records carry typed `specs`; official/legacy records may use `specs` as a plain attribute dict (an alias of `attributes`).
    storefront = any(k in rec for k in ("brand", "subcategory", "use_cases", "options", "variants", "stock_qty", "images"))
    attrs = rec.get("attributes") if storefront else _pick(rec, "attributes")
    attrs = {str(k): str(v) for k, v in attrs.items()} if isinstance(attrs, dict) else {}
    img = _pick(rec, "image")
    imgs = [i for i in ([img] if isinstance(img, str) else []) + list(rec.get("images") or []) if safe_image(i)]
    sp = rec.get("specs") if storefront and isinstance(rec.get("specs"), dict) else {}
    qty = rec.get("stock_qty")
    stock = _stock(_pick(rec, "stock"))
    if isinstance(qty, int) and not isinstance(qty, bool):
        stock = "in_stock" if qty > 0 else "out_of_stock"
    p = Product(
        id=str(pid), title=str(title), description=str(_pick(rec, "description") or ""),
        price=_num(_pick(rec, "price")), stock=stock,
        category=str(_pick(rec, "category") or ""), rating=_num(_pick(rec, "rating")),
        attributes=attrs, image=imgs[0] if imgs else None,
        brand=str(rec.get("brand") or ""), subcategory=str(rec.get("subcategory") or ""), sku=str(rec.get("sku") or ""),
        specs=dict(sp), highlights=[str(h) for h in rec.get("highlights") or []][:8], use_cases=[str(u).lower() for u in rec.get("use_cases") or []],
        images=imgs[:8], variants=list(rec.get("variants") or []), options=dict(rec.get("options") or {}),
        stock_qty=qty if isinstance(qty, int) and not isinstance(qty, bool) else None, mrp=_num(rec.get("mrp")),
        featured=bool(rec.get("featured")), added_days_ago=rec.get("added_days_ago") if isinstance(rec.get("added_days_ago"), int) else None,
        option_stock=rec.get("stock_per_variant") if isinstance(rec.get("stock_per_variant"), int) else None,
        unavailable=list(rec.get("unavailable") or []), raw_attributes=dict(attrs),
        price_history=[h for h in rec.get("price_history") or [] if isinstance(h, dict)],
    )
    variants = expand_options(p)
    if variants and _pick(rec, "stock") is None:     # stock lives in the variants: derive it exactly as the database path does
        p.stock_qty = None
        p.stock = "in_stock" if any(v["stock_qty"] > 0 for v in variants) else "out_of_stock"
    if p.specs or p.options:                      # storefront records: show specs and option lists as readable attributes
        opt_attrs = {k.capitalize(): ", ".join(map(str, v)) for k, v in p.options.items() if isinstance(v, list) and v}
        p.attributes = {**specs_mod.display_attributes(p.specs, opt_attrs), **p.attributes}
    return p


def load_catalogue(path: Path) -> list[Product]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        data = json.loads(raw)
        records = data.get("products", []) if isinstance(data, dict) else data
    products, skipped = [], 0
    for rec in records:
        p = _product(rec) if isinstance(rec, dict) else None
        if p:
            products.append(p)
        else:
            skipped += 1
    if skipped:
        log.warning("Skipped %d malformed catalogue records", skipped)
    return products


def load_policy(path: Path) -> list[Section]:
    sections = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        head = lines[0].lstrip("#").strip()
        if len(lines) > 1 and len(head) <= 60 and not head.endswith("."):
            title, body = head.rstrip(":"), " ".join(lines[1:])
        else:
            title, body = f"Section {len(sections) + 1}", " ".join(lines)
        sections.append(Section(f"POL-{len(sections) + 1}", title, body))
    return sections


def resolve_data(data_dir=None, dev_dir=None, allow_dev=None):
    """Returns (products, sections, source). Falls back to the synthetic store only when explicitly allowed.

    A data folder may contain manifest.json {"source": "demo-store"} to name itself; the default label is "dev-sample".
    Products from a non-challenge folder are tagged data_origin="demo"."""
    data_dir = config.DATA_DIR if data_dir is None else Path(data_dir)
    dev_dir = config.DEV_DATA_DIR if dev_dir is None else Path(dev_dir)
    allow_dev = config.ALLOW_DEV_DATA if allow_dev is None else allow_dev
    for folder, kind in ((data_dir, "challenge"), (dev_dir, "dev")):
        if kind == "dev" and not allow_dev:
            break
        cat = next((folder / n for n in ("catalogue.json", "catalogue.jsonl") if (folder / n).exists()), None)
        pol = folder / "policy.txt"
        if cat and pol.exists():
            source = "challenge"
            if kind == "dev":
                source = "dev-sample"
                man = folder / "manifest.json"
                if man.exists():
                    try:
                        source = str(json.loads(man.read_text(encoding="utf-8")).get("source") or source)
                    except (ValueError, OSError):
                        pass
            products = load_catalogue(cat)
            if kind == "dev":
                for p in products:
                    p.data_origin = "demo"
            return products, load_policy(pol), source
    raise RuntimeError(
        f"Catalogue/policy not found in {data_dir}. Add catalogue.json and policy.txt there, "
        "or set ALLOW_DEV_DATA=1 to use the clearly-labelled development sample."
    )
