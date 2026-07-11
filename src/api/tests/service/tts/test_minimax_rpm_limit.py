from flaskr.api.tts import minimax_provider


def _set_config(monkeypatch, mapping):
    monkeypatch.setattr(
        minimax_provider,
        "get_config",
        lambda name, default=None: mapping.get(name, default),
    )


def test_resolve_rpm_turbo_tier_default(monkeypatch):
    _set_config(monkeypatch, {})
    assert minimax_provider._resolve_minimax_rpm_limit("speech-2.8-turbo") == 200
    assert minimax_provider._resolve_minimax_rpm_limit("speech-01-turbo") == 200


def test_resolve_rpm_hd_tier_default(monkeypatch):
    _set_config(monkeypatch, {})
    assert minimax_provider._resolve_minimax_rpm_limit("speech-2.8-hd") == 20
    assert minimax_provider._resolve_minimax_rpm_limit("speech-02-hd") == 20


def test_resolve_rpm_json_override_takes_precedence(monkeypatch):
    _set_config(monkeypatch, {"MINIMAX_TTS_RPM_LIMITS": '{"speech-2.8-hd": 15}'})
    # Explicit override wins over the tier default.
    assert minimax_provider._resolve_minimax_rpm_limit("speech-2.8-hd") == 15
    # Models not in the override map still use their tier default.
    assert minimax_provider._resolve_minimax_rpm_limit("speech-2.8-turbo") == 200


def test_resolve_rpm_invalid_override_json_is_ignored(monkeypatch):
    _set_config(monkeypatch, {"MINIMAX_TTS_RPM_LIMITS": "not-json"})
    assert minimax_provider._resolve_minimax_rpm_limit("speech-2.8-turbo") == 200


def test_resolve_rpm_unknown_model_falls_back_to_global(monkeypatch):
    _set_config(monkeypatch, {"MINIMAX_TTS_RPM_LIMIT": 42})
    # No tier suffix and no override -> global fallback.
    assert minimax_provider._resolve_minimax_rpm_limit("some-future-model") == 42


def test_resolve_rpm_unknown_model_without_global_disables_gating(monkeypatch):
    _set_config(monkeypatch, {})
    # Global default is 0 which disables gating for unknown models.
    assert minimax_provider._resolve_minimax_rpm_limit("some-future-model") == 0
