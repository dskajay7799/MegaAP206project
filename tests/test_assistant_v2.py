"""Regression tests for the "smarter assistant" upgrade (demo store, 52 products).

Two kinds of test:
  * named regressions - each one is a real bug found by probing the assistant with realistic questions;
  * invariants over the question sets in demo_store/ - nothing may be answered with an unsupported claim, and accuracy may not slip.
"""
import json
import random
from pathlib import Path

import pytest
from tests.helpers import ROOT, make_app

from backend.app import nlu
from backend.evaluate import evaluate

app = make_app()
assistant = app.extensions["verity"].runtime.assistant()


def ask(msg, history=None):
    return assistant.respond(msg, history or [])


def ids(r):
    return [p["id"] for p in r["products"]]


# ---------------------------------------------------------------- invariants over the question sets
@pytest.mark.parametrize("name,floor", [("questions", 1.0), ("questions_realistic", 0.97), ("questions_blind", 0.97), ("questions_unseen", 0.97)])
def test_question_sets_hold_accuracy_and_never_make_unsupported_claims(name, floor):
    summary, rows = evaluate(ROOT / "demo_store" / f"{name}.json", use_llm=False)
    bad = [(r["id"], r["question"], r["expected"], r["got"]) for r in rows if r["ok"] is False]
    assert summary["behaviour_accuracy"] >= floor, bad
    assert summary["responses_with_unsupported_claims"] == 0, [r["question"] for r in rows if r["unsupported"]]
    assert summary["citation_recall"] in (None, 1.0)


def test_assistant_never_crashes_on_hostile_input():
    rnd = random.Random(7)
    pool = ["headphones", "under", "between", "and", "1000", "first", "it", "compare", "size", "XL", "?", "₹", "k", "cart", "return", "days", "vs", "",
            "waterproof", "jogging", "VRT-1001", "💥", "इयरफोन", "a" * 300, "<script>", "'; drop table", "999999999999999999999", "1e9", "above", "under k"]
    for _ in range(600):
        q = " ".join(rnd.choice(pool) for _ in range(rnd.randint(0, 7)))[:500]
        h = [" ".join(rnd.choice(pool) for _ in range(rnd.randint(0, 3))) for _ in range(rnd.randint(0, 3))]
        r = ask(q, h)
        assert r["status"] in ("answer", "clarify", "refused", "no_match") and isinstance(r["message"], str) and r["message"]


# ---------------------------------------------------------------- routing bugs
def test_noise_cancelling_is_a_product_feature_not_the_cancellation_policy():
    for q in ("noise cancelling headphones", "noice cancelling headfones", "headphones with noise cancellation"):
        r = ask(q)
        assert r["status"] == "answer" and ids(r) == ["VRT-1001"], q
    assert ask("can I cancel my order after it's processing")["citations"][0]["id"] == "POL-4"      # real cancellation question still works


def test_wired_headphones_are_not_wireless_and_negated_text_is_not_evidence():
    r = ask("wireless headphones under 3000")
    assert ids(r) == ["VRT-1002"]                                   # VRT-1003 is "Wireless: No"
    assert "VRT-1002" not in ids(ask("noise cancelling earbuds"))   # Pulse Lite's description says "No noise cancelling."


def test_numbers_with_units_are_not_prices():
    lo, hi = nlu.parse_range("wireless earbuds with at least 25 hours battery")
    assert (lo, hi) == (None, None)
    assert nlu.parse_range("between 1,000 and 2,500") == (1000.0, 2500.0)
    assert nlu.parse_range("under 2k")[1] == 2000.0
    assert nlu.parse_range("over 15 inch") == (None, None)


def test_short_words_are_not_over_corrected():
    assert ask("show me sofas")["status"] == "no_match"             # "sofa" must not become "soft"
    assert ask("add it to cart", ["VRT-6003"])["status"] == "answer"  # "cart" must not become "care"


# ---------------------------------------------------------------- needs, ranges, ranking
def test_needs_are_translated_to_catalogue_words_and_the_reading_is_shown():
    r = ask("I need something to listen to music while jogging")
    assert r["status"] == "answer" and "VRT-1005" in ids(r) and "VRT-1007" not in ids(r)
    assert "I read “music” as" in r["message"] and "Need “music” matched to" in r["evidence"]["reason"]
    assert "VRT-8001" in ids(ask("something to carry my laptop"))
    assert ids(ask("something for a rainy day"))[:1] == ["VRT-2008"] or "VRT-2008" in ids(ask("something for a rainy day"))


def test_gender_is_never_silently_ignored_but_recipient_is_noted():
    r = ask("shoes for men")
    assert r["status"] == "clarify" and "can't filter by “men”" in r["message"]
    r = ask("gift for my dad under 2000")
    assert r["status"] == "answer" and all(p["price"] <= 2000 for p in r["products"]) and "recipient" in r["message"]


def test_waterproof_is_never_presented_as_an_exact_match():
    r = ask("waterproof bag")
    assert r["status"] == "clarify" and "Nothing is listed as “waterproof”" in r["message"]


def test_price_ranges():
    r = ask("headphones between 1000 and 3000")
    assert set(ids(r)) == {"VRT-1002", "VRT-1003"} and "between ₹1,000 and ₹3,000" in r["message"]
    r = ask("anything above 4000")
    assert "VRT-1001" in ids(r) and all(p["price"] >= 4000 for p in r["products"])
    r = ask("anything under 300 rupees")
    assert r["status"] == "answer" and all(p["price"] <= 300 for p in r["products"])
    assert ask("laptop backpack under 1000")["status"] == "no_match"


def test_ranking_uses_typed_specs_and_reports_missing_data():
    r = ask("which headphones have the longest battery")
    assert ids(r)[0] == "VRT-1001" and "40 hours" in r["message"] and "doesn't list battery life" in r["message"]
    assert ids(ask("which earbuds charge the fastest"))[0] == "VRT-1005"
    assert ids(ask("what is the cheapest thing you sell"))[0] == "VRT-7002"
    assert ids(ask("most expensive product"))[0] == "VRT-1001"
    assert ids(ask("lightest running shoe"))[0] == "VRT-3003"
    assert ask("longest lasting power bank")["status"] in ("refused", "no_match")          # the power bank has no battery-hours spec: say so, don't guess


# ---------------------------------------------------------------- questions about one product
def test_feature_questions_are_answered_from_the_record_or_refused():
    r = ask("does the kettle have auto shut off")
    assert r["status"] == "answer" and "Auto shut-off" in r["message"] and ids(r) == ["VRT-4004"]
    r = ask("is the Pulse Lite noise cancelling")
    assert r["message"].startswith("No —") and ids(r) == ["VRT-1002"]
    r = ask("does the Cube speaker have a microphone")
    assert r["status"] == "refused" and "doesn't list" in r["message"]
    r = ask("is the Halo ANC good for the gym")
    assert r["status"] == "refused" and "study, commute, travel, office" in r["message"]
    r = ask("is the rain jacket waterproof")
    assert r["status"] == "answer" and "closest listed wording" in r["message"] and "“rain”" not in r["message"]


def test_sizes_colours_and_laptop_fit():
    assert ask("do the jeans come in 32")["message"].startswith("Yes")
    assert ask("jeans in size 40")["message"].startswith("No")
    assert ask("is the kurta available in size M")["message"].startswith("Yes")
    assert ask("does the rain jacket come in red")["message"].startswith("No")
    assert "Black, Sand" in ask("what colours does the Halo ANC come in")["message"]
    assert ask("does the laptop backpack fit a 14 inch laptop")["message"].startswith("Yes")
    assert ask("what size is the football")["status"] == "answer"


# ---------------------------------------------------------------- policy
def test_policy_questions_use_the_policy_numbers_exactly():
    r = ask("can I return a shirt after 10 days")
    assert r["status"] == "answer" and r["message"].startswith("No — 10 days is outside the 7-day return window")
    assert ask("I got a kurta 3 days ago, can I still return it")["message"].startswith("Yes")
    r = ask("how much is shipping for a 800 rupee order")
    assert "flat Rs 59" in r["message"] and "₹800" in r["message"]
    assert "free" in ask("will I pay shipping on a ₹1500 order")["message"]
    assert ask("is there warranty on shoes")["status"] == "answer"
    r = ask("how long is the warranty on a kettle")                 # the warranty policy names electronics, apparel, footwear only
    assert r["status"] == "refused" and "apparel, electronics, footwear" in r["message"]
    assert ask("how many days do I have to send something back")["citations"][0]["id"] == "POL-1"
    assert ask("who pays for return shipping")["status"] == "refused"
    assert ask("what if my product arrives damaged")["status"] == "refused"
    assert ask("retrun policy")["citations"][0]["id"] == "POL-1"


# ---------------------------------------------------------------- conversation
def test_follow_ups_are_about_the_product_under_discussion():
    r = ask("and how long is the battery", ["VRT-1001"])
    assert ids(r) == ["VRT-1001"] and "40 hours" in r["message"]     # used to answer about a different product (VRT-1007)
    assert ids(ask("is it in stock", ["electric kettle"])) == ["VRT-4004"]
    assert ask("what about its warranty", ["VRT-1001"])["citations"][0]["id"] == "POL-3"
    r = ask("is it available in XL", ["kurta"])
    assert ids(r) == ["VRT-2004"] and r["message"].startswith("Yes")


def test_ordinals_and_pronouns_resolve_against_the_last_results():
    first = ask("headphones")
    r = ask("tell me more about the first one", ["headphones"])
    assert ids(r) == [first["products"][0]["id"]]
    r = ask("compare the first two", ["wireless headphones"])
    assert len(r["comparison"]["columns"]) == 2
    r = ask("add the first one to cart", ["running shoes"])
    assert r["status"] == "answer" and any(f["action"] == "add_to_cart" for f in r["followups"])
    assert ask("add it to cart")["status"] == "clarify"               # nothing to refer to: ask, never guess
    assert ids(ask("which one is cheaper", ["backpack"])) == ["VRT-8002"]


def test_new_search_is_not_mistaken_for_a_follow_up():
    r = ask("a bottle that keeps water cold", ["VRT-1001"])
    assert ids(r) == ["VRT-4002"]


# ---------------------------------------------------------------- small talk / scope
@pytest.mark.parametrize("q", ["hello", "hey verity", "thanks!", "what can you do", "who are you", "bye", "are you a bot"])
def test_small_talk_is_answered_without_pretending_to_search(q):
    r = ask(q)
    assert r["status"] == "clarify" and "couldn't find" not in r["message"] and r["followups"]


def test_a_greeting_followed_by_a_request_is_still_a_request():
    assert "VRT-1006" in ids(ask("hi, bluetooth speaker please"))


@pytest.mark.parametrize("q", ["tell me a joke", "what's the weather today", "what is 25 times 4", "can you book me a flight"])
def test_off_topic_requests_are_declined_politely(q):
    r = ask(q)
    assert r["status"] == "refused" and "shopping assistant" in r["message"]


def test_unknown_products_get_a_helpful_dead_end():
    r = ask("iphone 15 price")
    assert r["status"] == "no_match" and "We stock" in r["message"] and r["followups"]
    assert ask("do you sell laptops")["status"] == "clarify"        # only laptop *backpacks*: say so


def test_a_new_product_request_after_a_product_conversation_is_not_a_follow_up():
    # found by the real-browser test: "do you sell iPhones?" right after discussing a shoe used to be answered about the shoe
    r = ask("do you sell iPhones?", ["VRT-3001"])
    assert r["status"] == "no_match" and "iphone" in r["message"].lower() and not r["products"]
