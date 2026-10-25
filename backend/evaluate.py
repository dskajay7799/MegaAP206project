"""Reproducible evaluation + latency / token / cost report.

Usage:  python -m backend.evaluate [questions.json] [--no-llm] [--out eval_report.json] [--html eval_report.html]

Question record (extra fields optional):
  {"question": "...", "expected": "answer" | "clarify" | "refuse", "history": ["earlier user message", ...],
   "expected_ids": ["P-1"], "type": "ambiguous" | "out_of_catalogue" | ...}
Key aliases for question / expected / history are accepted; label synonyms (ambiguous, out_of_catalogue, ...) are normalised.
Records without an expected label are reported but never counted as correct. Nothing here is a made-up score: it only
reports what was measured from the questions file you pass in.
"""
import html
import json
import re
import statistics
import sys
import time
from pathlib import Path

from .app import config
from .app.assistant import Assistant
from .app.catalogue import resolve_data
from .app.llm import _nums, fact_table, generate, verify

KEYS_Q, KEYS_E, KEYS_H = ("question", "query", "q"), ("expected", "expected_behavior", "expected_behaviour", "behavior", "behaviour", "label"), ("history",)
LABELS = {"answer": "answer", "answerable": "answer", "answered": "answer", "clarify": "clarify", "clarification": "clarify", "ambiguous": "clarify",
          "refuse": "refuse", "refusal": "refuse", "refused": "refuse", "out_of_catalogue": "refuse", "out-of-catalogue": "refuse",
          "out_of_scope": "refuse", "unanswerable": "refuse", "no_match": "refuse"}
GOT = {"answer": "answer", "clarify": "clarify", "refused": "refuse", "no_match": "refuse"}


def pick(rec, keys):
    return next((rec[k] for k in keys if k in rec), None)


def pct(vals, p):
    s = sorted(vals)
    return round(s[max(0, -(-len(s) * p // 100) - 1)], 2) if s else None   # nearest-rank percentile


def unsupported_claims(res: dict, question: str, a: Assistant, history=()) -> list[str]:
    """Citation and number checks on the final message, whatever produced it (grounded text or LLM rewrite)."""
    msg, issues = res["message"], []
    question = " ".join([*history, question])      # numbers the shopper said in earlier turns are theirs too
    question += " " + " ".join(str(int(float(n) * 1000)) for n in re.findall(r"(\d+(?:\.\d+)?)\s*k\b", question, re.I))      # "2k" is 2000
    tags = re.findall(r"\[([^\]]+)\]", msg)
    known = set(a.by_id) | set(a.sec_by_id)
    issues += [f"unknown citation [{t}]" for t in dict.fromkeys(tags) if t not in known]
    cited = {c["id"] for c in res["citations"]}
    issues += [f"citation [{t}] not in evidence" for t in dict.fromkeys(tags) if t in known and t not in cited]
    facts = fact_table(a, cited)
    allowed = set().union(*facts["nums"].values(), set()) | _nums(question)
    if res["status"] == "answer":
        if res.get("mode") == "grounded":     # deterministic text: every ₹ amount must be a cited price, the shopper's number, or a price difference
            prices = [a.by_id[c].price for c in cited if c in a.by_id and a.by_id[c].price is not None]
            diffs = {abs(x - y) for x in prices for y in prices}
            ok_amt = {f"{v:.0f}" for v in [*prices, *diffs]} | _nums(question)
            bad = [m for m in re.findall(r"₹(\d+(?:,\d+)*)", msg) if m.replace(",", "") not in ok_amt]
            issues += [f"unsupported price ₹{m}" for m in bad]
        elif not verify(msg, "", question, cited, facts):
            issues.append("claim not supported by its cited record")
    else:
        bad = [m for m in re.findall(r"₹(\d+(?:,\d+)*)", msg) if m.replace(",", "") not in allowed]
        issues += [f"unsupported price ₹{m}" for m in bad]
    return issues


def evaluate(path: Path, use_llm: bool):
    products, sections, source = resolve_data()
    a = Assistant(products, sections)
    rows = []
    for n, rec in enumerate(json.loads(path.read_text(encoding="utf-8")), 1):
        q, raw = pick(rec, KEYS_Q), pick(rec, KEYS_E)
        exp = LABELS.get(str(raw).strip().lower()) if raw is not None else None
        hist = pick(rec, KEYS_H) or []
        hist = [h["content"] if isinstance(h, dict) else str(h) for h in hist if not isinstance(h, dict) or h.get("role", "user") == "user"]
        res = generate(a, q, hist, use_llm=use_llm)
        got = GOT[res["status"]]
        issues = unsupported_claims(res, q, a, hist)
        exp_ids = rec.get("expected_ids")
        cites = {c["id"] for c in res["citations"]}
        rows.append({"n": n, "id": rec.get("id", n), "type": rec.get("type"), "question": q, "history": hist, "expected": exp, "got": got, "status": res["status"],
                     "ok": (got == exp) if exp else None, "citations_ok": (set(exp_ids) <= cites) if exp_ids else None,
                     "mode": res["mode"], "latency_ms": res["metrics"]["latency_ms"], "llm_tokens": res["metrics"]["llm_tokens"],
                     "unsupported": issues, "message": res["message"]})
    judged = [r for r in rows if r["expected"]]

    def acc(sub):
        return round(sum(r["ok"] for r in sub) / len(sub), 3) if sub else None
    lat, tok = [r["latency_ms"] for r in rows], [r["llm_tokens"] for r in rows]
    types = sorted({r["type"] for r in judged if r["type"]})
    summary = {"data_source": source, "questions_file": str(path), "llm_enabled": bool(use_llm and config.GROQ_API_KEY),
               "questions": len(rows), "labelled": len(judged), "unlabelled": len(rows) - len(judged),
               "behaviour_accuracy": acc(judged), "answer_accuracy": acc([r for r in judged if r["expected"] == "answer"]),
               "clarification_accuracy": acc([r for r in judged if r["expected"] == "clarify"]),
               "refusal_accuracy": acc([r for r in judged if r["expected"] == "refuse"]),
               "accuracy_by_type": {t: acc([r for r in judged if r["type"] == t]) for t in types},
               "citation_recall": acc_c(rows),
               "responses_with_unsupported_claims": sum(bool(r["unsupported"]) for r in rows),
               "latency_ms": {"mean": round(statistics.mean(lat), 2) if lat else None, "p95": pct(lat, 95)},
               "llm_tokens_per_query": round(statistics.mean(tok), 1) if tok else 0,
               "cost_per_query_inr": round(statistics.mean(tok) * config.INR_PER_1K_TOKENS / 1000, 5) if tok else 0}
    return summary, rows


def acc_c(rows):
    sub = [r for r in rows if r["citations_ok"] is not None]
    return round(sum(r["citations_ok"] for r in sub) / len(sub), 3) if sub else None


def render_html(summary: dict, rows: list) -> str:
    e = html.escape
    fmt = lambda v: "n/a" if v is None else (f"{v:.1%}" if isinstance(v, float) and v <= 1 else str(v))
    cards = [("Behaviour accuracy", fmt(summary["behaviour_accuracy"])), ("Answer", fmt(summary["answer_accuracy"])),
             ("Clarification", fmt(summary["clarification_accuracy"])), ("Refusal", fmt(summary["refusal_accuracy"])),
             ("Unsupported-claim responses", str(summary["responses_with_unsupported_claims"])),
             ("Latency mean / p95", f"{summary['latency_ms']['mean']} / {summary['latency_ms']['p95']} ms"),
             ("LLM tokens / query", str(summary["llm_tokens_per_query"])), ("Cost / query (INR)", str(summary["cost_per_query_inr"]))]
    tr = "".join(f"<tr class=\"{'bad' if r['ok'] is False or r['unsupported'] else ''}\"><td>{e(str(r['id']))}</td><td>{e(r['type'] or '')}</td>"
                 f"<td>{e(' › '.join(r['history'] + [r['question']]))}</td><td>{e(r['expected'] or '—')}</td><td>{e(r['got'])}</td>"
                 f"<td>{'✓' if r['ok'] else ('✗' if r['ok'] is False else '—')}</td><td>{r['latency_ms']}</td><td>{e('; '.join(r['unsupported']) or '—')}</td></tr>" for r in rows)
    return f"""<!doctype html><meta charset=utf-8><title>Verity evaluation report</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;background:#f6f3ee;color:#1b1a17;margin:0;padding:32px;max-width:1100px;margin:auto}}
h1{{font-family:Georgia,serif}}.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:20px 0}}
.c{{background:#fff;border:1px solid #e4ded3;border-radius:10px;padding:14px}}.c b{{display:block;font-size:1.4rem}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}td,th{{border:1px solid #e4ded3;padding:6px 8px;text-align:left;vertical-align:top}}
tr.bad td{{background:#fbeceb}}.n{{color:#6b665c}}</style>
<h1>Verity evaluation report</h1>
<p class=n>Data source: <b>{e(summary['data_source'])}</b> · questions file: {e(summary['questions_file'])} · {summary['questions']} questions ({summary['labelled']} labelled) · LLM: {'on' if summary['llm_enabled'] else 'off (grounded mode)'}</p>
<div class=g>{''.join(f'<div class=c>{e(k)}<b>{e(v)}</b></div>' for k, v in cards)}</div>
<p class=n>Accuracy by type: {e(json.dumps(summary['accuracy_by_type']))}</p>
<table><tr><th>ID<th>Type<th>Question<th>Expected<th>Got<th>OK<th>ms<th>Unsupported claims</tr>{tr}</table>"""


def main():
    argv = sys.argv[1:]
    opt = lambda name, default: argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default
    flags = {opt("--out", None), opt("--html", None)}
    args = [x for x in argv if not x.startswith("--") and x not in flags]
    path = Path(args[0]) if args else config.DATA_DIR / "questions.json"
    summary, rows = evaluate(path, "--no-llm" not in argv)
    Path(opt("--out", "eval_report.json")).write_text(json.dumps({"summary": summary, "results": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(opt("--html", "eval_report.html")).write_text(render_html(summary, rows), encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    for r in rows:
        if r["ok"] is False or r["unsupported"]:
            print(f"  ✗ [{r['id']}] {r['question']!r}: expected {r['expected']}, got {r['got']} {r['unsupported']}")


if __name__ == "__main__":
    main()
