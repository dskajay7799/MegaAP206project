"""Optional, privacy-preserving analytics (LOG_CHATS=1): question text, reply type, latency, tokens and a random per-tab id.
No user id, name, email or IP is ever attached. Failures never affect the shopper."""
import logging
import threading

from .models import ChatLog, Feedback

log = logging.getLogger("chatlog")


def _write(db, obj):
    try:
        with db.scope() as s:
            s.add(obj)
    except Exception as e:
        log.warning("analytics write failed: %s", type(e).__name__)


def _async(db, obj):
    threading.Thread(target=_write, args=(db, obj), daemon=True).start()


def log_chat(db, enabled: bool, session_id: str, message: str, res: dict):
    if enabled:
        m = res["metrics"]
        _async(db, ChatLog(session_id=session_id[:40], message=message[:500], status=res["status"], mode=res["mode"], latency_ms=m["latency_ms"], tokens=m["llm_tokens"]))


def log_feedback(db, enabled: bool, session_id: str, request_id: str, helpful: bool):
    if enabled:
        _async(db, Feedback(session_id=session_id[:40], request_id=request_id[:16], helpful=helpful))
