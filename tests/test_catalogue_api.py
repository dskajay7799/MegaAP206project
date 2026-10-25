"""Storefront catalogue: demo-store integrity, filters, detail pages, variants, compare studio, price history, home sections."""
from pathlib import Path

from tests.helpers import ROOT


def test_demo_store_is_coherent(demo_app, api):
    d = api.get("/api/products?page_size=48").get_json()
    assert d["total"] >= 35
    health = api.get("/api/health").get_json()
    assert health["data_source"] == "demo-store" and health["synthetic_data"] is True
    ids = set()
    for p in api.get("/api/products?page_size=48&page=1").get_json()["items"] + api.get("/api/products?page_size=48&page=2").get_json()["items"]:
        assert p["id"] not in ids
        ids.add(p["id"])
        assert p["price"] and p["category"] and p["brand"] and p["images"] and p["rating_is_demo"] is True
        for img in p["images"]:
            assert (ROOT / "frontend" / img.lstrip("/")).exists(), f"missing image {img}"
    assert len(ids) >= 35
    assert len({c["name"] for c in api.get("/api/meta").get_json()["categories"]}) >= 8


def test_products_without_options_have_no_phantom_variants(api):
    d = api.get("/api/products/VRT-1009").get_json()          # charger: no options, tracked stock 40
    assert d["variants"] == [] and d["stock_qty"] == 40 and d["stock"] == "in_stock"
    assert api.get("/api/products/VRT-1005").get_json()["stock"] == "out_of_stock"      # explicit stock 0 stays out of stock
    assert api.get("/api/products/VRT-3003").get_json()["stock"] == "out_of_stock"      # all variants at 0


def test_filters_compose_and_actually_filter(api):
    g = lambda q: api.get("/api/products?page_size=48&" + q).get_json()
    assert {p["category"] for p in g("category=Footwear")["items"]} == {"Footwear"}
    assert all(p["price"] <= 1000 for p in g("max_price=1000")["items"]) and g("max_price=1000")["total"] > 0
    assert all(p["price"] >= 3000 for p in g("min_price=3000")["items"])
    assert all(p["stock"] == "in_stock" for p in g("in_stock=1")["items"]) and g("in_stock=1")["total"] < g("")["total"]
    assert {p["brand"] for p in g("brand=Stridewell")["items"]} == {"Stridewell"}
    maroon = {p["id"] for p in g("colour=Maroon")["items"]}
    assert len(maroon) >= 2 and all("Maroon" in api.get(f"/api/products/{i}").get_json()["options"]["colour"] for i in maroon)
    assert g("size=XL")["total"] > 0 and g("size=XL")["total"] < g("")["total"]
    assert all(p["rating"] >= 4.4 for p in g("min_rating=4.4")["items"])
    items = g("sort=price_asc")["items"]
    assert [p["price"] for p in items] == sorted(p["price"] for p in items)
    items = g("sort=price_desc&category=Electronics")["items"]
    assert [p["price"] for p in items] == sorted((p["price"] for p in items), reverse=True)
    assert g("category=Footwear&max_price=2000&in_stock=1")["total"] < g("category=Footwear")["total"]
    assert g("q=headphones")["total"] == 3 and g("q=zzzz")["total"] == 0
    assert g("use=study")["total"] >= 5 and g("featured=1")["total"] >= 5


def test_pagination_is_consistent(api):
    p1, p2 = api.get("/api/products?page_size=20&page=1").get_json(), api.get("/api/products?page_size=20&page=2").get_json()
    assert p1["pages"] == 3 and len(p1["items"]) == 20 and not ({i["id"] for i in p1["items"]} & {i["id"] for i in p2["items"]})
    assert api.get("/api/products?page=999&page_size=20").get_json()["page"] == p1["pages"]


def test_product_detail_variants_related_policies(api):
    d = api.get("/api/products/VRT-2003").get_json()                       # t-shirt: 4 colours x 4 sizes
    assert len(d["variants"]) == 16 and set(d["options"]) == {"colour", "size"} and d["specs"] and d["highlights"]
    assert d["related"] and all(r["id"] != "VRT-2003" and r["related_reason"] for r in d["related"])
    assert {p["title"] for p in d["policies"]} >= {"Returns", "Shipping", "Warranty"}
    assert api.get("/api/products/NOPE").status_code == 404


def test_compare_studio_rules(api):
    d = api.get("/api/compare?ids=VRT-1001,VRT-1002").get_json()["studio"]
    assert d["radar"] and len(d["radar"]["axes"]) >= 3 and "relative" in d["radar"]["note"]
    assert all(0 <= v <= 1 for ax in d["radar"]["axes"] for v in ax["scaled"])
    d3 = api.get("/api/compare?ids=VRT-1001,VRT-1002,VRT-1003").get_json()["studio"]          # the wired model lists no battery -> no radar, honest reason
    assert d3["radar"] is None and "radar" in d3["radar_reason"].lower()
    assert any("isn't listed" in x for x in d3["limits"]["VRT-1003"])
    w = api.get("/api/compare?ids=VRT-1001,VRT-1002&weights=price:5,battery_hours:0,noise_cancellation:0,charge_time_min:0,weight_g:0,rating:0").get_json()["studio"]
    assert w["recommendation"]["text"].count("Pulse Lite") >= 1 and w["scores"][1]["score"] > w["scores"][0]["score"]     # price-only weighting flips the winner
    mixed = api.get("/api/compare?ids=VRT-1001,VRT-2001").get_json()["studio"]
    assert any("different categories" in w for w in mixed["warnings"])
    assert mixed["rows"] and all(r["listed_for"] == 1 for r in mixed["rows"])          # no spec is shared, so nothing is pretended to be comparable
    assert mixed["radar"] is None and {c["id"] for c in mixed["criteria"]} <= {"price", "rating"}
    assert api.get("/api/compare?ids=VRT-1001").status_code == 400


def test_price_history_marks_simulated_and_never_calls_it_real(api, admin):
    h = api.get("/api/products/VRT-1001/price-history").get_json()
    assert h["has_simulated"] and h["recorded_count"] == 1 and h["enough_recorded"] is False and any(p["simulated"] for p in h["points"])
    admin.patch("/api/admin/products/VRT-1009/price", {"price": 999})
    admin.patch("/api/admin/products/VRT-1009/price", {"price": 1049})
    h2 = api.get("/api/products/VRT-1009/price-history").get_json()
    assert h2["enough_recorded"] is True and not h2["has_simulated"] and [p["price"] for p in h2["points"]][-2:] == [999, 1049]


def test_home_sections_only_show_what_data_supports(demo_app):
    from tests.helpers import Api, make_app
    fresh = Api(make_app())
    h = fresh.get("/api/home").get_json()
    assert h["featured"] and h["new_arrivals"] and h["collections"] and h["trending"] == [] and h["trending_basis"] == ""     # no orders yet -> no "trending"
    assert all(p["stock"] != "out_of_stock" for p in h["featured"])


def test_meta_and_policies(api):
    m = api.get("/api/meta").get_json()
    assert m["commerce"]["shipping_fee"] == 59 and m["commerce"]["free_shipping_above"] == 999
    txt = " ".join(s["text"] for s in api.get("/api/policies").get_json()["sections"])
    assert "Rs 999" in txt and "Rs 59" in txt           # the policy text the assistant cites matches the fees the server charges
