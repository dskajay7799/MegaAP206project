"""Small helpers shared by every route module: per-request DB session, JSON errors, body parsing."""
from flask import current_app, g, jsonify, request


def ext():
    return current_app.extensions["verity"]


def cfg(key: str):
    return current_app.config[key]


def db():
    if "db" not in g:
        g.db = ext().db.session()
    return g.db


def error(status: int, code: str, message: str, **extra):
    body = {"error": {"code": code, "message": message, "request_id": g.get("rid", ""), **extra}}
    resp = jsonify(body)
    resp.status_code = status
    return resp


def body() -> dict:
    b = request.get_json(silent=True)
    return b if isinstance(b, dict) else {}


def assistant():
    return ext().runtime.assistant()


def pagination(default: int = 20, maximum: int = 100) -> tuple[int, int]:
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        size = min(maximum, max(1, int(request.args.get("page_size", default))))
    except ValueError:
        size = default
    return page, size
