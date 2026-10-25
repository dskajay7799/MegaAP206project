"""Minimal SMTP sender for password-reset mail. Only used when SMTP_HOST and MAIL_FROM are configured (untested against a live server here)."""
import smtplib
import ssl
from email.message import EmailMessage


def configured(cfg) -> bool:
    return bool(cfg["SMTP_HOST"] and cfg["MAIL_FROM"])


def send(cfg, to: str, subject: str, text: str):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["MAIL_FROM"], to, subject
    msg.set_content(text)
    with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15) as s:
        s.starttls(context=ssl.create_default_context())
        if cfg["SMTP_USER"]:
            s.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        s.send_message(msg)
