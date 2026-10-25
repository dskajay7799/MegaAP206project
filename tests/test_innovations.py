"""SmartMatch, Value Lens, Smart Budget Basket, evidence explorer and the evaluator on the demo store."""
import json
import subprocess
import sys

from tests.helpers import ROOT

EXAMPLE = "wireless headphones for studying, commuting and long battery life, under ₹3,000"


def sm(api, text, **kw):
    r = api.post("/api/smartmatch", {"text": text, **kw})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_smartmatch_example_is_explainable_and_evidence_based(api):
    r = sm(api, EXAMPLE)
    assert r["status"] == "ok" and r["budget"] == 3000 and "Σ" in r["formula"]
    assert {"use:study", "use:commute", "feat:battery", "feat:wireless"} <= {c["id"] for c in r["criteria"]}
    top = r["matches"][0]
    assert top["product"]["id"] == "VRT-1002" and top["rank"] == 1 and top["product"]["price_text"] == "₹2,499"
    for m in r["matches"]:
        assert abs(sum(x["points"] for x in m["breakdown"]) - m["score"]) <= 0.2 * len(m["breakdown"])        # the parts add up to the score
        assert all({"label", "weight", "fit", "verdict", "detail"} <= set(x) for x in m["breakdown"])
    over = next(e for e in r["excluded"] if e["id"] == "VRT-1001")
    assert over["reason"] == "Over budget by ₹1,999 (₹4,999)"                        # why a product was left out, from the actual numbers


def test_smartmatch_missing_data_is_flagged_never_assumed(api):
    r = sm(api, EXAMPLE)
    wired = next(m for m in r["matches"] if m["product"]["id"] == "VRT-1003")
    battery = next(x for x in wired["breakdown"] if x["id"] == "feat:battery")
    assert battery["verdict"] == "unknown" and battery["fit"] is None and battery["points"] == 0
    assert "Battery life not listed" in wired["missing"] and wired["coverage"] < 1
    assert r["matches"][0]["coverage"] == 1.0 and wired["score"] < r["matches"][0]["score"]
    wireless = next(x for x in wired["breakdown"] if x["id"] == "feat:wireless")
    assert wireless["verdict"] == "unmet"                                            # the record says wireless: false


def test_smartmatch_weights_recompute_and_are_deterministic(api):
    base = sm(api, EXAMPLE, budget=6000)
    assert [m["product"]["id"] for m in base["matches"]][0] == "VRT-1001"            # with the budget lifted, the 40-hour model leads on battery
    flipped = sm(api, EXAMPLE, budget=6000, weights={"feat:battery": 0, "headroom": 5, "rating": 0, "use:study": 0, "use:commute": 0, "feat:wireless": 0})
    assert flipped["matches"][0]["product"]["id"] == "VRT-1003"                      # only price headroom matters -> cheapest wins
    assert sm(api, EXAMPLE, budget=6000) == base                                     # no randomness anywhere
    assert [c["weight"] for c in flipped["criteria"]] != [c["weight"] for c in base["criteria"]] and all(c["default_weight"] for c in flipped["criteria"])


def test_smartmatch_threshold_features_are_pass_fail(api):
    r = sm(api, "wireless earbuds with at least 25 hours battery")
    orbit = next(m for m in r["matches"] if m["product"]["id"] == "VRT-1004")
    row = next(x for x in orbit["breakdown"] if x["id"] == "feat:battery")
    assert "≥ 25" in row["label"] and row["fit"] == 1.0 and "meets" in row["detail"]
    strict = sm(api, "wireless earbuds with at least 40 hours battery", in_stock_only=False)
    assert all(next(x for x in m["breakdown"] if x["id"] == "feat:battery")["fit"] == 0.0 for m in strict["matches"])


def test_smartmatch_clarifies_instead_of_guessing(api):
    r = sm(api, "something for studying")
    assert r["status"] == "clarify" and r["matches"] == [] and "Headphones" in str(r["clarify"]["options"]) and r["clarify"]["reason"]
    r = sm(api, "I need a gift")
    assert r["status"] == "clarify"
    r = sm(api, "band")                                                               # same word, unlike products in different categories
    assert r["status"] == "clarify" and "categories" in r["clarify"]["question"] and len(r["clarify"]["options"]) == 2


def test_smartmatch_refuses_unknown_things_and_explains_budget_misses(api):
    r = sm(api, "iphone 15 pro")
    assert r["status"] == "no_match" and r["matches"] == [] and "iphone" in " ".join(r["notes"]).lower()
    r = sm(api, "headphones under 500")
    assert r["status"] == "no_match" and "₹1,499" in " ".join(r["notes"]) and len(r["excluded"]) == 3
    assert api.post("/api/smartmatch", {"text": ""}).status_code == 400 and api.post("/api/smartmatch", {"text": "x", "budget": "abc"}).status_code == 400


def test_smartmatch_stock_exclusions_and_unverifiable_wishes(api):
    r = sm(api, "wireless earbuds")
    assert next(e for e in r["excluded"] if e["id"] == "VRT-1005")["reason"] == "Out of stock"
    assert "VRT-1005" in [m["product"]["id"] for m in sm(api, "wireless earbuds", in_stock_only=False)["matches"]]
    r = sm(api, "comfortable headphones with good sound quality gaming")
    notes = " ".join(r["notes"])
    assert "can't verify" in notes.lower() or "no data to verify" in notes.lower()
    assert "gaming" in notes and r["intent"]["unverifiable_wishes"]                  # wishes with no catalogue data are reported, not scored


def test_smartmatch_uses_saved_preferences_only_when_present_and_allowed(demo_app, shopper):
    plain = sm(shopper, "headphones")
    assert plain["applied_preferences"] == [] and plain["budget"] is None
    shopper.put("/api/account/preferences", {"budget_max": 2000, "requirements": ["study"]})
    r = sm(shopper, "headphones")
    assert r["budget"] == 2000 and any("saved budget" in a for a in r["applied_preferences"]) and {m["product"]["id"] for m in r["matches"]} == {"VRT-1003"}
    assert all(m["product"]["id"] != "VRT-1002" for m in r["matches"]) and any(e["id"] == "VRT-1002" for e in r["excluded"])
    off = sm(shopper, "headphones", use_preferences=False)
    assert off["budget"] is None and off["applied_preferences"] == [] and len(off["matches"]) == 3
    assert sm(shopper, "headphones under 3000")["budget"] == 3000                    # an explicit budget in the text always wins


# ------------------------------------------------------------ Smart Budget Basket
def basket(api, budget, purpose, **kw):
    r = api.post("/api/basket", {"budget": budget, "purpose": purpose, **kw})
    return r.status_code, r.get_json()


def test_basket_stays_within_budget_and_explains_every_item(api):
    code, b = basket(api, 5000, "study setup")
    assert code == 200 and b["status"] == "ok"
    best = b["baskets"][0]
    assert best["total"] <= 5000 and abs(best["total"] + best["remaining"] - 5000) < 0.01
    prices = [float(i["price_text"].replace("₹", "").replace(",", "")) for i in best["items"]]
    assert abs(sum(prices) - best["total"]) < 0.01 and len(best["items"]) == best["slots_filled"] >= 3
    assert len({i["slot"] for i in best["items"]}) == len(best["items"])             # at most one product per slot
    for i in best["items"]:
        assert i["why"] and i["fit"] is not None
        assert "study" in api.get(f"/api/products/{i['product']['id']}").get_json()["use_cases"]       # only products the catalogue lists for studying
    assert len(b["baskets"]) >= 2 and len({tuple(i["product"]["id"] for i in x["items"]) for x in b["baskets"]}) == len(b["baskets"])
    assert all(x["total"] <= 5000 for x in b["baskets"])


def test_basket_reports_what_does_not_fit(api):
    _, b = basket(api, 1000, "study setup")
    best = b["baskets"][0]
    assert best["total"] <= 1000 and best["slots_filled"] < best["slots_total"]
    assert any(s["status"] == "skipped" and "doesn't fit" in s["reason"] for s in b["slots"]) or b["over_budget"]
    assert all(o["over_by_text"].startswith("₹") and "exceed the budget" in o["reason"] for o in b["over_budget"])
    code, none = basket(api, 100, "study setup")
    assert none["status"] == "no_match" and "cheapest" in " ".join(none["notes"]) and none["baskets"] == []


def test_basket_named_products_and_clarification(api):
    _, b = basket(api, 5000, "headphones and a backpack")
    assert {i["slot"] for i in b["baskets"][0]["items"]} == {"Headphones", "Backpacks"} and b["baskets"][0]["total"] <= 5000
    _, c = basket(api, 3000, "quantum chromodynamics")
    assert c["status"] == "clarify" and c["clarify"]["options"]
    _, d = basket(api, 3000, "scuba diving")
    assert d["status"] in ("clarify", "no_match") and d["baskets"] == []
    assert api.post("/api/basket", {"purpose": "study"}).status_code == 400 and api.post("/api/basket", {"budget": 5, "purpose": "study"}).status_code == 400
    assert api.post("/api/basket", {"budget": 500}).status_code == 400


def test_basket_never_includes_out_of_stock_items(api):
    _, b = basket(api, 20000, "gym")
    ids = {i["product"]["id"] for x in b["baskets"] for i in x["items"]}
    assert ids and not ({"VRT-6001", "VRT-1005", "VRT-3003"} & ids)


# ------------------------------------------------------------ Value Lens
def test_value_lens_is_factual_and_has_no_hidden_score(api):
    d = api.get("/api/products/VRT-1002/value-lens?budget=3000&need=long+battery+life").get_json()
    f = {x["id"]: x for x in d["factors"]}
    assert f["budget"]["verdict"] == "good" and "₹501 under your ₹3,000" in f["budget"]["detail"]
    assert f["feat:battery"]["verdict"] in ("good", "neutral") and "hours" in f["feat:battery"]["detail"]
    assert f["price_position"]["verdict"] == "neutral" and "median" in f["price_position"]["detail"]
    assert "score" not in d and "disclaimer" in d and "invent" in d["disclaimer"]
    over = api.get("/api/products/VRT-1001/value-lens?budget=3000").get_json()
    assert {x["id"]: x for x in over["factors"]}["budget"]["verdict"] == "concern" and "over your" in over["factors"][0]["detail"]


def test_value_lens_price_history_claims_only_what_data_supports(api, admin):
    sim = {x["id"]: x for x in api.get("/api/products/VRT-1001/value-lens").get_json()["factors"]}["history"]
    assert sim["verdict"] == "unknown" and "simulated" in sim["detail"].lower() and "not real market data" in sim["detail"]
    none = {x["id"]: x for x in api.get("/api/products/VRT-2002/value-lens").get_json()["factors"]}["history"]
    assert none["verdict"] == "unknown" and "Not enough recorded" in none["detail"]
    admin.patch("/api/admin/products/VRT-4003/price", {"price": 899})
    admin.patch("/api/admin/products/VRT-4003/price", {"price": 999})
    real = {x["id"]: x for x in api.get("/api/products/VRT-4003/value-lens").get_json()["factors"]}["history"]
    assert "Lowest recorded price ₹899" in real["detail"] and "₹100 above" in real["detail"]


def test_value_lens_flags_missing_specs_for_requested_needs(api):
    d = api.get("/api/products/VRT-1003/value-lens?need=long+battery").get_json()
    row = {x["id"]: x for x in d["factors"]}["feat:battery"]
    assert row["verdict"] == "unknown" and "not listed" in row["detail"]
    d = api.get("/api/products/VRT-1002/value-lens?need=comfortable+headphones").get_json()
    assert any("comfortable" in n for n in d["notes"])


# ------------------------------------------------------------ evidence explorer / grounding
def chat(api, msg, history=None):
    return api.c.post("/api/chat", json={"message": msg, "history": [{"role": "user", "content": h} for h in (history or [])]}).get_json()


def test_chat_evidence_lists_fields_used_exclusions_and_reasons(api):
    r = chat(api, "price of VRT-1001")
    assert "price" in r["evidence"]["fields_used"]["VRT-1001"] and r["citations"][0]["id"] == "VRT-1001"
    r = chat(api, "headphones under 3000")
    assert {e["id"] for e in r["evidence"]["excluded"]} == {"VRT-1001"} and "Over budget" in r["evidence"]["excluded"][0]["reason"]
    r = chat(api, "What is the price of the blue running shoe?")
    assert r["status"] == "clarify" and "3 products" in r["evidence"]["reason"] and "₹" not in r["message"]       # asked which one instead of quoting a price


def test_chat_states_when_a_requested_spec_is_not_listed(api):
    r = chat(api, "battery life of VRT-1003")
    assert "isn't listed" in r["message"] and r["citations"][0]["id"] == "VRT-1003" and r["evidence"]["missing"]
    assert "hours" not in r["message"]                                                # no invented battery figure


def test_chat_never_answers_account_or_payment_questions(api):
    for q in ("where is my order", "can I pay with UPI", "apply coupon SAVE10"):
        r = chat(api, q)
        assert r["status"] == "refused" and r["citations"] == [] and "Account" in r["message"]


def test_chat_policy_matches_server_fees(api):
    r = chat(api, "is shipping free?")
    assert r["citations"][0]["id"] == "POL-2" and "999" in r["message"] and "59" in r["message"]
    assert chat(api, "can I cancel an order")["citations"][0]["id"] == "POL-4"
    assert chat(api, "do you ship internationally")["status"] == "refused"


def test_ai_status_reports_real_capability(api):
    s = api.get("/api/ai/status").get_json()
    assert s["mode"] == "grounded" and s["llm_configured"] is False and s["model"] is None and "checked" in s["verification"].lower()
    assert api.get("/api/meta").get_json()["llm"] is False


def test_evaluator_scores_the_demo_store_end_to_end():
    out = subprocess.run([sys.executable, "-m", "backend.evaluate", "demo_store/questions.json", "--no-llm", "--out", "/tmp/_ev.json"], cwd=ROOT, capture_output=True, text=True,
                         env={"ALLOW_DEV_DATA": "1", "DATA_DIR": "/nonexistent", "PATH": "/usr/bin:/usr/local/bin", "PYTHONPATH": str(ROOT)})
    assert out.returncode == 0, out.stderr
    s = json.loads(out.stdout)
    assert s["questions"] >= 50 and s["behaviour_accuracy"] == 1.0 and s["responses_with_unsupported_claims"] == 0 and s["citation_recall"] == 1.0
