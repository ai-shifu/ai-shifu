from flaskr.service.learn import learn_funcs


class FakeRedis:
    """Minimal Redis .eval stub implementing the counter-semaphore Lua.

    Distinguishes acquire (key, max, ttl) from release (key) by arg count.
    """

    def __init__(self):
        self.counters: dict[str, int] = {}

    def eval(self, _script, _numkeys, *args):
        key = args[0]
        if len(args) >= 3:  # acquire: key, max_count, ttl
            max_count = int(args[1])
            current = self.counters.get(key, 0)
            if current < max_count:
                self.counters[key] = current + 1
                return 1
            return 0
        # release: key only
        current = self.counters.get(key, 0)
        if current > 0:
            self.counters[key] = current - 1
        return 1


def test_tts_synth_semaphore_caps_at_limit_and_releases(app, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake, raising=False)
    app.config["MAX_PARALLEL_TTS_SYNTH_COUNT"] = 2

    assert learn_funcs._tts_synth_sem_acquire(app, "u1", "o1") is True
    assert learn_funcs._tts_synth_sem_acquire(app, "u1", "o1") is True
    # third over the cap -> busy
    assert learn_funcs._tts_synth_sem_acquire(app, "u1", "o1") is False

    # releasing one frees a slot
    learn_funcs._tts_synth_sem_release(app, "u1", "o1")
    assert learn_funcs._tts_synth_sem_acquire(app, "u1", "o1") is True

    # a different outline has its own independent counter
    assert learn_funcs._tts_synth_sem_acquire(app, "u1", "o2") is True


def test_tts_synth_semaphore_fail_open_without_redis(app, monkeypatch):
    monkeypatch.setattr("flaskr.dao.redis_client", None, raising=False)
    app.config["MAX_PARALLEL_TTS_SYNTH_COUNT"] = 1

    # Redis unavailable -> never block synthesis (fail open, no cap enforced)
    assert learn_funcs._tts_synth_sem_acquire(app, "u", "o") is True
    assert learn_funcs._tts_synth_sem_acquire(app, "u", "o") is True


def test_tts_synth_semaphore_disabled_when_zero(app, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake, raising=False)
    app.config["MAX_PARALLEL_TTS_SYNTH_COUNT"] = 0

    assert learn_funcs._tts_synth_sem_acquire(app, "u", "o") is True
    # disabled cap does not touch Redis at all
    assert fake.counters == {}


def test_tts_synth_semaphore_ignores_incomplete_key(app, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake, raising=False)
    app.config["MAX_PARALLEL_TTS_SYNTH_COUNT"] = 1

    # Missing user/outline -> fail open, no counter created
    assert learn_funcs._tts_synth_sem_acquire(app, "", "o") is True
    assert learn_funcs._tts_synth_sem_acquire(app, "u", "") is True
    assert fake.counters == {}


def test_yield_tts_synthesis_sheds_request_when_full(app, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake, raising=False)
    app.config["MAX_PARALLEL_TTS_SYNTH_COUNT"] = 1

    body_calls = {"n": 0}

    def _body():
        body_calls["n"] += 1
        yield "chunk"

    # occupy the only slot
    assert learn_funcs._tts_synth_sem_acquire(app, "u", "o") is True

    out = list(
        learn_funcs._yield_tts_synthesis(
            app,
            user_bid="u",
            outline_bid="o",
            unknown_error_log="x",
            body=_body,
        )
    )

    # shed: no events yielded, body never invoked, occupied slot untouched
    assert out == []
    assert body_calls["n"] == 0
    key = learn_funcs._get_tts_synth_sem_key(app, "u", "o")
    assert fake.counters.get(key) == 1


def test_yield_tts_synthesis_runs_and_releases_slot(app, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("flaskr.dao.redis_client", fake, raising=False)
    app.config["MAX_PARALLEL_TTS_SYNTH_COUNT"] = 1

    def _body():
        yield "a"
        yield "b"

    with app.app_context():
        out = list(
            learn_funcs._yield_tts_synthesis(
                app,
                user_bid="u",
                outline_bid="o",
                unknown_error_log="x",
                body=_body,
            )
        )

    assert out == ["a", "b"]
    # slot released after the generator is exhausted
    key = learn_funcs._get_tts_synth_sem_key(app, "u", "o")
    assert fake.counters.get(key, 0) == 0
