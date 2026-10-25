"""Registration, login, logout, session bootstrap, password change and (honestly labelled) password reset."""
import datetime as dt
import logging

from flask import Blueprint, current_app, jsonify
from sqlalchemy import select

from .. import mailer, security
from ..http import body, cfg, db, error
from ..models import PasswordReset, User, WishlistItem, utcnow
from ..security import csrf_for, current_user, login_required, rate_limited
from ..services import cart as cart_svc

bp = Blueprint("auth", __name__)
log = logging.getLogger("auth")
GENERIC_LOGIN_ERROR = "That email and password don't match. After several failed attempts, sign-in pauses for a few minutes."


def user_dict(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role, "is_demo": u.is_demo, "created_at": u.created_at.isoformat()}


def session_payload(extra: dict | None = None) -> dict:
    ident = security.identity()
    u = ident["user"]
    out = {"user": user_dict(u) if u else None, "csrf": csrf_for(ident["token"]), **(extra or {})}
    if u:
        out["wishlist_ids"] = [w.product_id for w in db().scalars(select(WishlistItem).where(WishlistItem.user_id == u.id))]
    return out


@bp.get("/api/auth/me")
def me():
    security.ensure_cookie()
    return jsonify(session_payload())


def _finish_login(user: User):
    old_guest = security.guest_key()
    s = db()
    security.start_session(user)
    merged = cart_svc.merge_guest_into_user(s, user, old_guest)
    s.commit()
    return merged


@bp.post("/api/auth/register")
@rate_limited("auth", "AUTH_RATE_LIMIT_PER_MIN")
def register():
    b = body()
    name = " ".join(str(b.get("name", "")).split())
    email = security.normalise_email(b.get("email"))
    pw = b.get("password", "")
    errs = {}
    if not 2 <= len(name) <= 80:
        errs["name"] = "Enter your name (2–80 characters)."
    if not security.valid_email(email):
        errs["email"] = "Enter a valid email address."
    if "password" not in errs and (p := security.password_problem(pw, email, name)):
        errs["password"] = p
    if errs:
        return error(422, "validation_failed", "Check the highlighted fields.", fields=errs)
    s = db()
    if s.scalar(select(User.id).where(User.email == email)):
        return error(409, "email_taken", "An account with that email already exists. Try signing in instead.", fields={"email": "Already registered."})
    u = User(email=email, name=name, password_hash=security.hash_password(pw), password_changed_at=utcnow(), last_login_at=utcnow())
    s.add(u)
    s.flush()
    merged = _finish_login(u)
    resp = jsonify(session_payload({"cart_merged": merged}))
    resp.status_code = 201
    return resp


@bp.post("/api/auth/login")
@rate_limited("auth", "AUTH_RATE_LIMIT_PER_MIN")
def login():
    b = body()
    email, pw = security.normalise_email(b.get("email")), b.get("password", "")
    if not isinstance(pw, str) or not email or len(pw) > 256:
        return error(401, "invalid_credentials", GENERIC_LOGIN_ERROR)
    s = db()
    u = s.scalar(select(User).where(User.email == email))
    now = utcnow()
    if u and u.locked_until and u.locked_until > now:
        security.verify_password(None, pw)                    # same cost as a real attempt; locked accounts look like wrong passwords
        return error(401, "invalid_credentials", GENERIC_LOGIN_ERROR)
    if not (u and u.is_active and security.verify_password(u, pw)):
        if u is None:
            security.verify_password(None, pw)
        else:
            u.failed_logins += 1
            if u.failed_logins >= cfg("MAX_FAILED_LOGINS"):
                u.locked_until, u.failed_logins = now + dt.timedelta(minutes=cfg("LOCKOUT_MINUTES")), 0
                log.warning("account locked after repeated failures (user id=%s)", u.id)
            s.commit()
        return error(401, "invalid_credentials", GENERIC_LOGIN_ERROR)
    u.failed_logins, u.locked_until, u.last_login_at = 0, None, now
    merged = _finish_login(u)
    return jsonify(session_payload({"cart_merged": merged}))


@bp.post("/api/auth/logout")
def logout():
    security.end_session()
    db().commit()
    return jsonify(session_payload())


@bp.post("/api/auth/password/change")
@login_required
@rate_limited("auth", "AUTH_RATE_LIMIT_PER_MIN")
def change_password():
    b, u = body(), current_user()
    if not security.verify_password(u, b.get("current_password", "")):
        return error(403, "wrong_password", "Your current password is incorrect.", fields={"current_password": "Incorrect."})
    problem = security.password_problem(b.get("new_password", ""), u.email, u.name)
    if problem:
        return error(422, "validation_failed", problem, fields={"new_password": problem})
    u.password_hash, u.password_changed_at = security.hash_password(b["new_password"]), utcnow()
    security.revoke_sessions(u.id, keep_hash=security.token_hash(security.identity()["token"]))
    db().commit()
    return jsonify({"ok": True, "message": "Password changed. Other devices have been signed out."})


@bp.post("/api/auth/password/forgot")
@rate_limited("auth", "AUTH_RATE_LIMIT_PER_MIN")
def forgot():
    email = security.normalise_email(body().get("email"))
    smtp = mailer.configured(current_app.config)
    dev_link = (not cfg("PRODUCTION")) and cfg("DEV_SHOW_RESET_LINK")
    if not smtp and not dev_link:
        return error(501, "reset_unavailable", "Password reset by email isn't set up on this deployment, so no email can be sent. Ask the store administrator to reset your password.")
    s = db()
    u = s.scalar(select(User).where(User.email == email)) if security.valid_email(email) else None
    link = None
    if u and u.is_active:
        for old in s.scalars(select(PasswordReset).where(PasswordReset.user_id == u.id, PasswordReset.used_at.is_(None))):
            old.used_at = utcnow()
        token = security.new_token()
        s.add(PasswordReset(token_hash=security.token_hash(token), user_id=u.id, expires_at=utcnow() + dt.timedelta(minutes=30)))
        s.commit()
        base = cfg("PUBLIC_URL") or ""
        link = f"{base}/#/reset?token={token}"
        if smtp:
            try:
                mailer.send(current_app.config, u.email, "Reset your Verity password", f"Use this link within 30 minutes to choose a new password:\n\n{link}\n\nIf you didn't ask for this, ignore this email.")
            except Exception as e:                                  # never reveal delivery details to the requester
                log.warning("reset mail failed: %s", type(e).__name__)
    if smtp:
        return jsonify({"ok": True, "message": "If an account exists for that email, a reset link has been sent. It expires in 30 minutes."}), 202
    return jsonify({"ok": True, "demo": True, "message": "Demo mode: email isn't configured, so nothing was sent. For testing only, the reset link appears below.",
                    "demo_reset_link": link}), 202


@bp.post("/api/auth/password/reset")
@rate_limited("auth", "AUTH_RATE_LIMIT_PER_MIN")
def reset():
    b = body()
    token = str(b.get("token", ""))
    s = db()
    pr = s.scalar(select(PasswordReset).where(PasswordReset.token_hash == security.token_hash(token))) if token else None
    if not pr or pr.used_at or pr.expires_at <= utcnow():
        return error(400, "invalid_token", "That reset link is invalid or has expired. Request a new one.")
    u = s.get(User, pr.user_id)
    problem = security.password_problem(b.get("new_password", ""), u.email, u.name)
    if problem:
        return error(422, "validation_failed", problem, fields={"new_password": problem})
    u.password_hash, u.password_changed_at, u.failed_logins, u.locked_until = security.hash_password(b["new_password"]), utcnow(), 0, None
    pr.used_at = utcnow()
    security.revoke_sessions(u.id)
    s.commit()
    return jsonify({"ok": True, "message": "Password updated. Sign in with your new password."})
