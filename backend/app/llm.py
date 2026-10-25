"""Groq phrasing layer + hallucination guard.

The deterministic pipeline (assistant.py) decides WHAT is true and whether to answer, ask or refuse.
Groq only rewrites an already-grounded answer into friendlier text. verify() then rejects the rewrite if it contains
any citation, price or number that is not in the context, or any uncited sentence -> we fall back to the grounded text.
"""
import json
import logging
import re
import time

import requests

from . import config

log = logging.getLogger("llm")
URL = "https://api.groq.com/openai/v1/chat/completions"
SYSTEM = """You are Verity, a precise shopping assistant for an online store. Use ONLY the CONTEXT.
1. Every sentence stating a fact (price, stock, rating, attribute, policy) must end with its citation tag, e.g. [DEV-001] or [POL-2]. Use only IDs present in CONTEXT.
2. Never state a price, number, product or policy that is not in CONTEXT. Never guess or round.
3. Be concise (max 60 words), friendly, plain English. If several products are listed, recommend at most 3 and say why (price, rating, stock).
4. Output only the answer text."""


def _nums(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"\[[^\]]*\]", " ", s).replace(",", "")))


_OUT = re.compile(r"out of stock|unavailable|sold out", re.I)
_IN = re.compile(r"(?<!out of )\bin stock\b", re.I)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if re.search(r"\w", s)]


def fact_table(assistant, ids) -> dict:
    """Per-ID numbers and stock status taken from the real records; used to bind each claim to the ID it cites."""
    nums, stock = {}, {}
    for cid in ids:
        if cid in assistant.by_id:
            p = assistant.by_id[cid]
            rec = {k: v for k, v in assistant.full_record(p).items() if k != "image"}     # file names must not widen the set of "allowed" numbers
            nums[cid] = _nums(json.dumps(rec, ensure_ascii=False)) | _nums(p.id)
            stock[cid] = p.stock
        elif cid in assistant.sec_by_id:
            nums[cid] = _nums(assistant.sec_by_id[cid].text)
    return {"nums": nums, "stock": stock}


def verify(text: str, context: str, question: str, allowed_ids: set[str], facts: dict | None = None, derived=frozenset()) -> bool:
    """True only if every cited ID is real, every sentence is cited, and every number is supported.

    Without `facts` the check is global (numbers must appear somewhere in the context). With `facts`, each sentence's numbers
    must belong to the records *that sentence cites* (or be the shopper's own numbers / a number the pipeline derived), and
    stock wording must agree with the cited products' stock status."""
    tags = re.findall(r"\[([^\]]+)\]", text)
    if not tags or any(t not in allowed_ids for t in tags):
        return False
    sents = _sentences(text)
    if any("[" not in s for s in sents):
        return False
    if facts is None:
        return _nums(text) <= _nums(context) | _nums(question)
    shopper = _nums(question)
    for s in sents:
        cited = re.findall(r"\[([^\]]+)\]", s)
        ok = set().union(*(facts["nums"].get(c, set()) for c in cited)) | shopper | set(derived)
        if not _nums(s) <= ok:
            return False
        prods = [c for c in cited if c in facts["stock"]]
        if _OUT.search(s) and any(facts["stock"][c] != "out_of_stock" for c in prods):
            return False
        if _IN.search(s) and any(facts["stock"][c] != "in_stock" for c in prods):
            return False
    return True


def _polish(assistant, res: dict, question: str, usage: dict) -> str | None:
    cmp_ = res["comparison"] and {"columns": [{"id": c["id"], "title": c["title"]} for c in res["comparison"]["columns"]],
                                   "rows": [{"label": r["label"], "values": r["values"]} for r in res["comparison"]["rows"]]}
    ctx = {"products": res["products"], "comparison": cmp_,
           "policy": [{k: c[k] for k in ("id", "label", "snippet")} for c in res["citations"] if c["kind"] == "policy"], "grounded_draft": res["message"]}
    context = json.dumps(ctx, ensure_ascii=False)
    try:
        r = requests.post(URL, timeout=8, headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"}, json={
            "model": config.GROQ_MODEL, "temperature": 0, "max_tokens": 220,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": f"CONTEXT:\n{context}\n\nSHOPPER QUESTION: {question}"}]})
        r.raise_for_status()
        data = r.json()
        usage["llm_calls"] += 1
        usage["llm_tokens"] += data.get("usage", {}).get("total_tokens", 0)
        text = data["choices"][0]["message"]["content"].strip()
    except Exception as e:  # network, quota, bad payload -> grounded fallback
        log.warning("groq unavailable: %s", type(e).__name__)
        return None
    ids = {c["id"] for c in res["citations"]}
    facts = fact_table(assistant, ids)
    derived = _nums(res["message"]) - set().union(*facts["nums"].values(), set())   # counts / differences the pipeline computed
    if verify(text, context, question, ids, facts, derived):
        return text
    log.warning("groq output rejected by verifier")
    return None


def generate(assistant, message: str, history: list[str] | None = None, use_llm: bool = True) -> dict:
    t = time.perf_counter()
    res = assistant.respond(message, history or [])
    usage = {"llm_calls": 0, "llm_tokens": 0}
    res["mode"] = "grounded"
    if use_llm and config.GROQ_API_KEY and res["status"] == "answer":
        text = _polish(assistant, res, message, usage)
        if text:
            res["message"], res["mode"] = text, "ai"
    res["metrics"] = {"latency_ms": round((time.perf_counter() - t) * 1000, 1), **usage}
    return res
