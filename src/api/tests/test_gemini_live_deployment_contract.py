"""Protect the deployment contract for browser-direct Gemini Live."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_live_does_not_require_an_internal_websocket_route() -> None:
    route_source = _read("src/api/flaskr/service/learn/live_follow_up_routes.py")
    requirements = _read("src/api/requirements.txt")
    assert "/live-follow-up/ws/" not in route_source
    assert "Flask-Sock" not in requirements
    assert "simple-websocket" not in requirements
    assert "wsproto" not in requirements

    for relative_path in ("docker/nginx.conf", "docker/nginx.dev.conf"):
        source = _read(relative_path)
        assert "location ^~ /api/learn/live-follow-up/ws/" not in source
        assert "$ai_shifu_connection_upgrade" not in source


def test_live_does_not_require_feature_specific_nginx_host_handling() -> None:
    for relative_path in ("docker/nginx.conf", "docker/nginx.dev.conf"):
        source = _read(relative_path)
        assert "$ai_shifu_request_host" not in source


def test_direct_transport_uses_only_google_constrained_websocket() -> None:
    backend = _read("src/api/flaskr/service/learn/gemini_live_token.py")
    frontend = _read("src/web/src/lib/liveVoiceFollowUp.ts")

    assert "BidiGenerateContentConstrained" in backend
    assert "BidiGenerateContentConstrained" in frontend
    assert "https://generativelanguage.googleapis.com/v1beta/auth_tokens" in backend
    assert "url.origin !== GEMINI_LIVE_WEBSOCKET_ORIGIN" in frontend
    assert "url.pathname !== GEMINI_LIVE_CONSTRAINED_PATH" in frontend


def test_live_feature_flag_defaults_off_in_deployment_examples() -> None:
    compose_files = (
        "docker/docker-compose.yml",
        "docker/docker-compose.latest.yml",
        "docker/docker-compose.dev.yml",
        "docker/docker-compose.runtime-harness.yml",
    )
    for relative_path in compose_files:
        assert 'GEMINI_LIVE_ENABLED: "${GEMINI_LIVE_ENABLED:-false}"' in _read(
            relative_path
        ), relative_path

    assert 'GEMINI_LIVE_ENABLED="False"' in _read("docker/.env.example.full")
