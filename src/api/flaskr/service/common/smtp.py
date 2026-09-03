"""Small SMTP transport primitive for application email delivery."""

from __future__ import annotations

import smtplib
import ssl
from contextlib import suppress
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


class SmtpConfigurationError(RuntimeError):
    """Raised when the SMTP relay configuration is incomplete."""


SMTP_TIMEOUT_SECONDS = 10.0
_INVALID_SMTP_PORT_MESSAGE = "SMTP port is invalid."
_INCOMPLETE_SMTP_CONFIGURATION_MESSAGE = "SMTP relay configuration is incomplete."


def is_smtp_configured(app: Flask) -> bool:
    """Return whether the relay has all values required for authenticated delivery."""
    server_name = str(app.config.get("SMTP_SERVER") or "").strip()
    sender = str(app.config.get("SMTP_SENDER") or "").strip()
    username = str(app.config.get("SMTP_USERNAME") or "").strip()
    password = str(app.config.get("SMTP_PASSWORD") or "")
    try:
        port = int(app.config.get("SMTP_PORT") or 25)
    except (TypeError, ValueError):
        return False
    return bool(server_name and sender and username and password and 1 <= port <= 65535)


def _smtp_port(app: Flask) -> int:
    try:
        port = int(app.config.get("SMTP_PORT") or 25)
    except (TypeError, ValueError) as exc:
        raise SmtpConfigurationError(_INVALID_SMTP_PORT_MESSAGE) from exc
    if not 1 <= port <= 65535:
        raise SmtpConfigurationError(_INVALID_SMTP_PORT_MESSAGE)
    return port


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
    if not is_smtp_configured(app):
        raise SmtpConfigurationError(_INCOMPLETE_SMTP_CONFIGURATION_MESSAGE)

    message = MIMEMultipart("alternative")
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject.replace("\r", "").replace("\n", "").strip()
    message["X-Auto-Response-Suppress"] = "All"
    message.attach(MIMEText(plain_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    server: smtplib.SMTP | None = None
    try:
        server = smtplib.SMTP(
            server_name,
            _smtp_port(app),
            timeout=SMTP_TIMEOUT_SECONDS,
        )
        server.starttls(context=ssl.create_default_context())
        server.login(username, password)
        server.sendmail(sender, [recipient], message.as_string())
    finally:
        if server is not None:
            try:
                server.quit()
            except OSError:
                with suppress(OSError):
                    server.close()
    return {"provider": "smtp", "accepted": "true"}
