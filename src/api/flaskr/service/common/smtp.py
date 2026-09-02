"""Small SMTP transport primitive for application email delivery."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


class SmtpConfigurationError(RuntimeError):
    """Raised when the SMTP relay configuration is incomplete."""


def send_smtp_email(
    app: Flask,
    *,
    recipient: str,
    subject: str,
    plain_body: str,
    html_body: str,
) -> dict[str, str]:
    """Send one MIME alternative email using the configured SMTP relay."""
    server_name = str(app.config.get("SMTP_SERVER") or "").strip()
    sender = str(app.config.get("SMTP_SENDER") or "").strip()
    username = str(app.config.get("SMTP_USERNAME") or "").strip()
    password = str(app.config.get("SMTP_PASSWORD") or "")
    if not all((server_name, sender, username, password)):
        raise SmtpConfigurationError

    message = MIMEMultipart("alternative")
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject.replace("\r", "").replace("\n", "").strip()
    message["X-Auto-Response-Suppress"] = "All"
    message.attach(MIMEText(plain_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    server = smtplib.SMTP(server_name, int(app.config.get("SMTP_PORT") or 25))
    try:
        server.starttls()
        server.login(username, password)
        server.sendmail(sender, [recipient], message.as_string())
    finally:
        server.quit()
    return {"provider": "smtp", "accepted": "true"}
