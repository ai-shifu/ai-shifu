"""Protect the deployment contract required by Gemini Live WebSockets."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_gunicorn_defaults_use_four_gthread_workers_with_sixteen_threads() -> None:
    tree = ast.parse(_read("src/api/gunicorn.conf.py"))
    assignments: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name):
            assignments[target.id] = ast.literal_eval(node.value)

    assert assignments["worker_class"] == "gthread"
    assert assignments["workers"] == 4
    assert assignments["threads"] == 16


def test_every_versioned_api_startup_uses_the_live_safe_worker_shape() -> None:
    startup_files = (
        "src/api/Dockerfile",
        "docker/docker-compose.yml",
        "docker/docker-compose.latest.yml",
        "docker/docker-compose.dev.yml",
        "docker/docker-compose.runtime-harness.yml",
        ".cursor/run-api.sh",
        "INSTALL_MANUAL.md",
    )

    for relative_path in startup_files:
        source = _read(relative_path)
        active_lines = [
            line
            for line in source.splitlines()
            if "exec gunicorn" in line
            or line.lstrip().startswith("CMD gunicorn")
            or line.lstrip().startswith("gunicorn -")
        ]
        assert active_lines, relative_path
        for line in active_lines:
            assert "-k gthread" in line, (relative_path, line)
            assert "--threads 16" in line, (relative_path, line)
            assert "-w 4" in line, (relative_path, line)


def test_nginx_live_route_preserves_upgrade_and_idle_timeout() -> None:
    for relative_path in ("docker/nginx.conf", "docker/nginx.dev.conf"):
        source = _read(relative_path)
        location_start = source.index("location ^~ /api/learn/live-follow-up/ws/ {")
        location_end = source.index("\n        }", location_start)
        location = source[location_start:location_end]

        assert "proxy_http_version 1.1;" in location
        assert "proxy_set_header Upgrade $http_upgrade;" in location
        assert "proxy_set_header Connection $ai_shifu_connection_upgrade;" in location
        assert "proxy_buffering off;" in location
        assert "proxy_request_buffering off;" in location
        assert "proxy_read_timeout 75s;" in location
        assert "proxy_send_timeout 75s;" in location


def test_live_server_dependencies_are_exactly_pinned() -> None:
    requirements = set(_read("src/api/requirements.txt").splitlines())

    assert "Flask-Sock==0.7.0" in requirements
    assert "simple-websocket==1.1.0" in requirements
    assert "wsproto==1.3.2" in requirements


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
