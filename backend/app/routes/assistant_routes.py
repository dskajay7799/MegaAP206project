"""AI assistant (grounded chat), feedback, AI status, SmartMatch, Smart Budget Basket."""
import hmac
import logging

from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from sqlalchemy import select

from .. import chatlog, config, store
from ..http import assistant, body, cfg, db, error, ext
from ..llm import generate
from ..models import Preference
from ..schemas import ChatRequest
from ..security import csrf_exempt, current_user, rate_limited
from ..services import analytics, basket as basket_svc, smartmatch

bp = Blueprint("assistant", __name__)
log = logging.getLogger("assistant")


def _prefs():
    u = current_user()
    if not u:
        return None
    p = db().get(Preference, u.id)
    if not p:
        return None
    return {"categories": list(p.categories or []), "requirements": list(p.requirements or []), "budget_max": p.budget_max_paise / 100 if p.budget_max_paise else None}


@bp.post("/api/chat")
@csrf_exempt
@rate_limited("chat", "RATE_LIMIT_PER_MIN")
def chat():
    b = body()
    from flask import g
    rid = g.rid
    try:
        req = ChatRequest.model_validate(b)
    except ValidationError:
        return error(400, "invalid_request", f"Please send a non-empty message of up to {cfg('MAX_MESSAGE_CHARS')} characters.")
    try:
        res = generate(assistant(), req.message, [h.content for h in req.history if h.role == "user"])
    except Exception:
        log.exception("chat failed rid=%s", rid)
        return error(500, "internal_error", "Something went wrong on our side. Please try again.")
    from .catalog import rows_for
    rich = {r.id: store.serialize(r) for r in rows_for([c["id"] for c in res.get("products", [])])}
    res["products"] = [{**c, **rich.get(c["id"], {}), **({"matched_on": c["matched_on"]} if "matched_on" in c else {})} for c in res.get("products", [])]   # same shape as the storefront cards
    res["metrics"]["request_id"] = rid
    chatlog.log_chat(ext().db, cfg("LOG_CHATS"), str(b.get("session_id", "")), req.message, res)
    log.info("chat rid=%s status=%s mode=%s ms=%s tokens=%s", rid, res["status"], res["mode"], res["metrics"]["latency_ms"], res["metrics"]["llm_tokens"])
    return jsonify(res)


@bp.post("/api/feedback")
@csrf_exempt
@rate_limited("feedback", "RATE_LIMIT_PER_MIN")
def feedback():
    b = body()
    if not isinstance(b.get("helpful"), bool):
        return error(400, "invalid_request", "helpful must be true or false.")
    chatlog.log_feedback(ext().db, cfg("LOG_CHATS"), str(b.get("session_id", "")), str(b.get("request_id", "")), b["helpful"])
    return "", 204


@bp.get("/api/ai/status")
def ai_status():
    on = bool(config.GROQ_API_KEY)
    return {"mode": "ai" if on else "grounded", "llm_configured": on, "provider": "Groq" if on else None, "model": config.GROQ_MODEL if on else None,
            "verification": "Every ID, number and stock statement is checked against the record it cites before any AI wording is shown; otherwise the grounded text is used.",
            "fallback": "Deterministic text written directly from catalogue and policy records.", "logging": cfg("LOG_CHATS")}


@bp.get("/api/stats")
def stats():
    key = request.headers.get("X-Admin-Key", "")
    if not cfg("ADMIN_KEY") or not hmac.compare_digest(key, cfg("ADMIN_KEY")):
        return error(403, "forbidden", "Not available.")
    return analytics.ai_stats(db())


@bp.post("/api/smartmatch")
@csrf_exempt
@rate_limited("smartmatch", "RATE_LIMIT_PER_MIN")
def smartmatch_route():
    b = body()
    text = str(b.get("text", "")).strip()[:500]
    if not text:
        return error(400, "invalid_request", "Describe what you need, for example “wireless headphones for studying under ₹3,000”.")
    budget = b.get("budget")
    try:
        budget = float(budget) if budget not in (None, "") else None
    except (TypeError, ValueError):
        return error(400, "invalid_request", "Budget must be a number.")
    weights = b.get("weights") if isinstance(b.get("weights"), dict) else None
    res = smartmatch.run(assistant(), text, budget=budget, weights=weights, in_stock_only=b.get("in_stock_only", True) is not False, prefs=_prefs(),
                         limit=max(1, min(int(b.get("limit", 6) or 6), 12)), use_preferences=b.get("use_preferences", True) is not False)
    return jsonify(res)


@bp.post("/api/basket")
@csrf_exempt
@rate_limited("basket", "RATE_LIMIT_PER_MIN")
def basket_route():
    b = body()
    try:
        budget = float(b.get("budget"))
    except (TypeError, ValueError):
        return error(400, "invalid_request", "Enter your total budget in rupees.")
    if budget < 50 or budget > 1_000_000:
        return error(400, "invalid_request", "Enter a budget between ₹50 and ₹10,00,000.")
    text = str(b.get("purpose", "")).strip()[:300]
    if not text:
        return error(400, "invalid_request", "Say what the basket is for, for example “study setup” or “headphones and a backpack”.")
    return jsonify(basket_svc.build(assistant(), budget, text, in_stock_only=b.get("in_stock_only", True) is not False))
