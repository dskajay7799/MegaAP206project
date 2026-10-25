import json

import pytest
from tests.helpers import ROOT, make_app

from backend.app import llm
from backend.app.llm import fact_table, verify

# This file protects the ORIGINAL grounded-assistant behaviour against the small, hand-checked 10-product DEV- fixture (dev_data/).
app = make_app(DEV_DATA_DIR=ROOT / "dev_data")
c = app.test_client()
assistant = app.extensions["verity"].runtime.assistant()


def ask(msg, history=None):
    r = c.post("/api/chat", json={"message": msg, "history": [{"role": "user", "content": h} for h in (history or [])]})
    return r.status_code, r.get_json()


def ids(d):
    return [p["id"] for p in d["products"]]


# ---------- original flows ----------
def test_flows():
    assert c.get("/api/health").get_json()["data_source"] == "dev-sample"
    s, d = ask("price of the blue running shoe")
    assert d["status"] == "clarify" and len(d["options"]) == 3          # trap question
    s, d = ask("price of DEV-001")
    assert d["status"] == "answer" and "₹2,499" in d["message"] and d["citations"][0]["id"] == "DEV-001"
    s, d = ask("do you sell iPhones?")
    assert d["status"] == "no_match" and d["message"].startswith("I couldn't find “iphone” in our catalogue.") and "We stock" in d["message"]
    s, d = ask("what is the return policy")
    assert d["status"] == "answer" and d["citations"][0]["id"].startswith("POL-")
    assert ask("where is my order")[1]["status"] == "refused"
    s, d = ask("compare DEV-004 and DEV-006")
    assert d["comparison"]["rows"][0]["values"] == ["₹1,299", "₹699"]
    s, d = ask("under ₹1,000, and I already said I want cotton", ["cotton shirts"])
    assert ids(d) == ["DEV-006"]
    s, d = ask("   ")
    assert s == 400 and d["error"]["code"] == "invalid_request"


# ---------- exact IDs, price/stock, policy ----------
def test_id_price_stock_and_citation_evidence():
    _, d = ask("is DEV-003 in stock?")
    assert "out of stock" in d["message"] and d["citations"][0]["record"]["id"] == "DEV-003"
    _, d = ask("earbuds battery")
    assert "20 hours" in d["message"] and ids(d) == ["DEV-008"]
    _, d = ask("price of Cotton Crew T-Shirt")                            # exact title beats superset matches
    assert d["status"] == "answer" and ids(d) == ["DEV-006"]


def test_policy_cited_and_uncovered_policy_refused():
    _, d = ask("how long does shipping take")
    assert d["status"] == "answer" and "3 to 6 business days" in d["message"] and d["citations"][0]["kind"] == "policy"
    _, d = ask("do you ship to Dubai?")
    assert d["status"] == "refused" and "dubai" in d["message"].lower()    # never answers a question the policy doesn't cover
    _, d = ask("refund kitne din mein milega")                            # Hinglish filler must not cause a false refusal
    assert d["status"] == "answer"


# ---------- unsupported / ambiguous ----------
@pytest.mark.parametrize("q", ["apply coupon SAVE20", "pay with UPI", "log in to my account", "track my order"])
def test_unsupported_features_refused(q):
    assert ask(q)[1]["status"] == "refused"


def test_ambiguity_and_unmatched_words_never_guess():
    _, d = ask("price of cotton shirt")
    assert d["status"] == "clarify" and len(d["options"]) >= 2
    _, d = ask("price of red running shoe")                               # no red shoe: must not quote a blue shoe's price
    assert d["status"] == "no_match" and "₹" not in d["message"]
    _, d = ask("which one is better?")
    assert d["status"] == "clarify"
    _, d = ask("compare shoe and shirt")
    assert d["status"] == "clarify"


def test_typos_hinglish_and_no_false_correction():
    assert ids(ask("shrit cottn")[1]) == ["DEV-004", "DEV-006", "DEV-005"]
    assert ask("joota blue")[1]["status"] == "answer"
    assert ask("iphoen")[1]["status"] == "no_match"


# ---------- multi-turn ----------
def test_multi_turn_constraints_accumulate_and_reset():
    h1 = ["Show me cotton shirts"]
    _, d = ask("Under ₹2,000", h1)
    assert d["context"]["max_price"] == 2000 and d["context"]["attributes"] == ["cotton"] and len(d["products"]) == 3
    h2 = h1 + ["Under ₹2,000"]
    _, d = ask("only white ones", h2)
    assert ids(d) == ["DEV-004"] and d["context"]["max_price"] == 2000
    _, d = ask("only black ones", h2)                                      # honest empty result, with the constraint named
    assert d["status"] == "no_match" and "black" in d["message"]
    _, d = ask("show me yoga mats", h2)                                    # unrelated request must not inherit old constraints
    assert ids(d) == ["DEV-010"] and d["context"]["max_price"] is None
    _, d = ask("only in stock ones", ["blue running shoes"])
    assert ids(d) == ["DEV-001", "DEV-002"]
    _, d = ask("which is cheapest?", h1)
    assert ids(d) == ["DEV-006"] and "₹699" in d["message"]
    _, d = ask("which one is better?", h1)                                 # compares what was shown, declares no winner
    assert d["comparison"] and "depends" in d["message"]


def test_budget_failures_are_honest():
    _, d = ask("cotton shirts under 500")
    assert d["status"] == "no_match" and ids(d) == ["DEV-006"] and "₹699" in d["message"]


# ---------- comparison ----------
def test_comparison_multi_and_missing_data():
    _, d = ask("compare DEV-001, DEV-002 and DEV-003")
    assert len(d["comparison"]["columns"]) == 3 and d["comparison"]["rows"][0]["differs"]
    _, d = ask("compare DEV-008 and DEV-009")
    row = {r["label"]: r["values"] for r in d["comparison"]["rows"]}
    assert row["Description"] == ["Not available in catalogue"] * 2 and row["battery"][1] == "Not available in catalogue"
    r = c.get("/api/compare?ids=DEV-004,DEV-006").get_json()
    assert [p["id"] for p in r["products"]] == ["DEV-004", "DEV-006"]
    assert c.get("/api/compare?ids=DEV-004").status_code == 400
    assert c.get("/api/compare?ids=DEV-004,NOPE").status_code == 404


# ---------- verifier ----------
def test_verifier_blocks_hallucinations():
    ctx, ids_ = '{"price_text": "₹699", "id": "DEV-006"}', {"DEV-006"}
    assert verify("The tee costs ₹699 [DEV-006].", ctx, "price?", ids_)
    assert not verify("The tee costs ₹599 [DEV-006].", ctx, "price?", ids_)      # invented price
    assert not verify("The tee costs ₹699.", ctx, "price?", ids_)                # no citation
    assert not verify("It costs ₹699 [DEV-999].", ctx, "price?", ids_)           # fake ID


def test_verifier_binds_claims_to_the_cited_record():
    allowed = {"DEV-004", "DEV-006", "DEV-003"}
    f = fact_table(assistant, allowed)
    assert verify("The tee is ₹699 [DEV-006].", "", "q", allowed, f)
    assert not verify("The shirt is ₹699 [DEV-004].", "", "q", allowed, f)       # real price, but of a different product
    assert not verify("The tee is in stock and ₹699 [DEV-003].", "", "q", allowed, f)
    assert not verify("DEV-003 is in stock [DEV-003].", "", "q", allowed, f)     # stock wording contradicts the record
    assert verify("DEV-003 is out of stock [DEV-003].", "", "q", allowed, f)


class _Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass

    def json(self):
        return {"usage": {"total_tokens": 50}, "choices": [{"message": {"content": self.text}}]}


def _with_llm(monkeypatch, behaviour):
    monkeypatch.setattr(llm.config, "GROQ_API_KEY", "test")
    monkeypatch.setattr(llm.requests, "post", behaviour)


def test_llm_failure_and_bad_output_fall_back_to_grounded_text(monkeypatch):
    def boom(*a, **k):
        raise llm.requests.ConnectionError("down")
    _with_llm(monkeypatch, boom)
    d = llm.generate(assistant, "price of DEV-001")
    assert d["mode"] == "grounded" and "₹2,499" in d["message"]
    _with_llm(monkeypatch, lambda *a, **k: _Resp("It costs only ₹1,999 [DEV-001]."))      # hallucinated price is rejected
    d = llm.generate(assistant, "price of DEV-001")
    assert d["mode"] == "grounded" and "₹2,499" in d["message"]
    _with_llm(monkeypatch, lambda *a, **k: _Resp("The Aero Run shoe costs ₹2,499 [DEV-001]."))
    d = llm.generate(assistant, "price of DEV-001")
    assert d["mode"] == "ai" and d["metrics"]["llm_tokens"] == 50


# ---------- HTTP layer ----------
def test_invalid_requests_and_errors():
    assert c.post("/api/chat", data="not json", content_type="text/plain").status_code == 400
    assert c.post("/api/chat", json=["x"]).status_code == 400
    assert c.post("/api/chat", json={"message": "x" * 501}).status_code == 400
    assert c.post("/api/chat", json={"message": "hi", "history": [{"role": "system", "content": "x"}]}).status_code == 400
    r = c.get("/api/nope")
    assert r.status_code == 404 and r.get_json()["error"]["code"] == "not_found"
    assert c.get("/api/stats").status_code == 403


def test_security_headers_and_cors():
    r = c.get("/api/health", headers={"Origin": "https://shop.example.app"})
    assert r.headers["Access-Control-Allow-Origin"] == "https://shop.example.app" and r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Access-Control-Allow-Origin" not in c.get("/api/health", headers={"Origin": "https://evil.example"}).headers
    assert c.options("/api/chat").status_code == 204
    assert "default-src 'self'" in c.get("/").headers["Content-Security-Policy"]


# ---------- catalogue browser ----------
def test_browse_filters_compose_and_paginate():
    d = c.get("/api/products?category=Apparel&max_price=1500&sort=price_asc").get_json()
    assert d["total"] == 2 and [p["id"] for p in d["items"]] == ["DEV-006", "DEV-004"]
    assert c.get("/api/products?q=blue+running").get_json()["total"] == 3
    assert c.get("/api/products?in_stock=1&category=Fitness").get_json()["total"] == 0
    assert c.get("/api/products?q=please+show").get_json()["total"] == 10          # filler-only query is ignored, not "no results"
    assert c.get("/api/products?q=shrit&max_price=1500").get_json()["total"] == 2   # typo + price compose
    assert c.get("/api/products?page=99").get_json()["page"] == 1
    d = c.get("/api/products?sort=rating").get_json()["items"]
    assert [p["rating"] for p in d] == sorted((p["rating"] for p in d), reverse=True)
    assert c.get("/api/products/DEV-001").get_json()["attributes"]["colour"] == "blue"
    assert c.get("/api/products/NOPE").status_code == 404
    m = c.get("/api/meta").get_json()
    assert m["products"] == 10 and {x["name"] for x in m["categories"]} >= {"Footwear", "Apparel"}


def test_feedback():
    assert c.post("/api/feedback", json={"helpful": True, "request_id": "x"}).status_code == 204
    assert c.post("/api/feedback", json={"helpful": "yes"}).status_code == 400


def test_missing_catalogue_is_reported_not_invented(tmp_path, monkeypatch):
    from backend.app import catalogue, config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "ALLOW_DEV_DATA", False)
    with pytest.raises(RuntimeError, match="catalogue.json"):
        catalogue.resolve_data()


def test_rate_limit_returns_429(monkeypatch):
    monkeypatch.setitem(app.config, "RATE_LIMIT_PER_MIN", 3)
    limiter = app.extensions["verity"].limiter
    limiter.clear()
    codes = [c.post("/api/chat", json={"message": "price of DEV-001"}, headers={"X-Forwarded-For": "9.9.9.9"}).status_code for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3:] == [429, 429]
    limiter.clear()
