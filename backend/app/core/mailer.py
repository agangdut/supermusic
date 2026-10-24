"""
Sending email (password reset links) through any SMTP service.

Resend, Postmark, Brevo, Mailgun, Amazon SES and Gmail all offer SMTP. Set:

  SMTP_HOST       e.g. smtp.resend.com
  SMTP_PORT       587 (STARTTLS, the default) or 465 (TLS from the start)
  SMTP_USER       e.g. resend
  SMTP_PASSWORD   the service's API key or SMTP password
  MAIL_FROM       e.g. SuperMusic <hello@your-domain.com> (a domain the service verified)

Without SMTP_HOST nothing is sent. Outside production the message is printed to
the backend's log instead, so the reset flow can be tried locally.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger("supermusic.mail")


def enabled() -> bool:
    return bool(os.getenv("SMTP_HOST", "").strip() and os.getenv("MAIL_FROM", "").strip())


def can_send() -> bool:
    """True when a message would reach someone (or the log, on a development machine)."""
    return enabled() or os.getenv("SM_ENV") != "production"


def site_url() -> str:
    """The site's address for links in emails: SITE_URL, else https://SITE_DOMAIN, else local."""
    url = os.getenv("SITE_URL", "").strip()
    if not url and os.getenv("SITE_DOMAIN", "").strip():
        url = f"https://{os.getenv('SITE_DOMAIN').strip()}"
    return (url or "http://localhost:3000").rstrip("/")


def send(to: str, subject: str, text: str) -> bool:
    """Send a plain-text email. False when it couldn't be sent (never raises)."""
    if not enabled():
        if os.getenv("SM_ENV") != "production":
            log.warning("Email not configured (SMTP_HOST); would send to %s:\n%s\n%s", to, subject, text)
            print(f"[mail] to {to}: {subject}\n{text}", flush=True)
            return True
        return False
    msg = EmailMessage()
    msg["From"] = os.getenv("MAIL_FROM").strip()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    host = os.getenv("SMTP_HOST").strip()
    port = int(os.getenv("SMTP_PORT", "") or 587)
    user, password = os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", "")
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls(context=ssl.create_default_context())
        with server:
            if user:
                server.login(user, password)
            server.send_message(msg)
        return True
    except Exception as e:  # a mail outage shouldn't break the page; the person can try again
        log.error("Sending email to %s failed: %s", to, e)
        return False
