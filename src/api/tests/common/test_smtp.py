"""Verify SMTP transport safety and relay configuration checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Flask
from flaskr.service.common.smtp import is_smtp_configured, send_smtp_email

if TYPE_CHECKING:
    import pytest


def _smtp_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SMTP_SERVER="smtp.example.com",
        SMTP_PORT=587,
        SMTP_USERNAME="mailer",
        SMTP_PASSWORD="password",
        SMTP_SENDER="no-reply@example.com",
    )
    return app


def test_smtp_configuration_requires_all_relay_values() -> None:
    app = _smtp_app()
    assert is_smtp_configured(app)

    app.config["SMTP_PASSWORD"] = ""
    assert not is_smtp_configured(app)


def test_smtp_send_keeps_provider_acceptance_when_quit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeSmtp:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            calls["connection"] = (host, port, timeout)

        def starttls(self, *, context: object) -> None:
            calls["tls_context"] = context

        def login(self, username: str, password: str) -> None:
            calls["login"] = (username, password)

        def sendmail(self, sender: str, recipients: list[str], message: str) -> None:
            calls["sendmail"] = (sender, recipients, message)

        def quit(self) -> None:
            message = "connection already closed"
            raise OSError(message)

        def close(self) -> None:
            calls["closed"] = True

    monkeypatch.setattr("flaskr.service.common.smtp.smtplib.SMTP", FakeSmtp)

    response = send_smtp_email(
        _smtp_app(),
        recipient="teacher@example.com",
        subject="Credit update",
        plain_body="Credits added.",
        html_body="<p>Credits added.</p>",
    )

    assert response == {"provider": "smtp", "accepted": "true"}
    assert calls["connection"] == ("smtp.example.com", 587, 10.0)
    assert "tls_context" in calls
    assert calls["closed"] is True
