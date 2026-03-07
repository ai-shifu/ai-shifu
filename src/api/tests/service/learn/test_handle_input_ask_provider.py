import types


from flaskr.service.learn.ask_provider_adapters import AskProviderError
from flaskr.service.learn.learn_dtos import GeneratedType


class _DummyColumn:
    def __eq__(self, _other):
        return True


class _DummyOrderColumn(_DummyColumn):
    def desc(self):
        return self


class _DummyQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def all(self):
        return []


class _DummyLearnGeneratedBlockModel:
    progress_record_bid = _DummyColumn()
    deleted = _DummyColumn()
    id = _DummyOrderColumn()
    query = _DummyQuery()


class _DummyFollowUpInfo:
    def __init__(self, ask_provider_config):
        self.ask_prompt = "{shifu_system_message}"
        self.ask_model = "gpt-test"
        self.model_args = {"temperature": 0.2}
        self.ask_provider_config = ask_provider_config

    def __json__(self):
        return {
            "ask_model": self.ask_model,
            "ask_provider_config": self.ask_provider_config,
        }


class _DummySpan:
    def __init__(self):
        self.output = ""

    def end(self, output=None):
        self.output = output or ""


class _DummyTrace:
    def __init__(self):
        self.span_output = None
        self.updated = {}

    def span(self, **_kwargs):
        return _DummySpan()

    def update(self, **kwargs):
        self.updated = kwargs


class _LLMChunk:
    def __init__(self, result: str):
        self.result = result


class _Context:
    def __init__(self):
        self._shifu_info = types.SimpleNamespace(use_learner_language=0)

    def get_system_prompt(self, _outline_bid: str):
        return ""


def _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config):
    monkeypatch.setattr(
        module,
        "get_follow_up_info_v2",
        lambda *_args, **_kwargs: _DummyFollowUpInfo(ask_provider_config),
    )
    monkeypatch.setattr(
        module,
        "check_text_with_llm_response",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(module, "_", lambda key: key)
    monkeypatch.setattr(module, "LearnGeneratedBlock", _DummyLearnGeneratedBlockModel)
    monkeypatch.setattr(
        module,
        "get_effective_ask_provider_config",
        lambda config: config,
    )
    monkeypatch.setattr(module.db.session, "add", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.db.session, "flush", lambda *_args, **_kwargs: None)

    call_counter = {"index": 0}

    def _fake_init_generated_block(*_args, **_kwargs):
        call_counter["index"] += 1
        return types.SimpleNamespace(
            generated_block_bid=f"gb-{call_counter['index']}",
            generated_content="",
            role="",
            type=0,
            position=-1,
        )

    monkeypatch.setattr(module, "init_generated_block", _fake_init_generated_block)


def _collect_content_chunks(events):
    return [event.content for event in events if event.type == GeneratedType.CONTENT]


def test_handle_input_ask_provider_only_returns_provider_error_without_llm(
    app, monkeypatch
):
    from flaskr.service.learn import handle_input_ask as module

    ask_provider_config = {
        "provider": "dify",
        "mode": "provider_only",
        "config": {},
    }
    _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config)

    llm_call_counter = {"count": 0}

    def _fake_chat_llm(*_args, **_kwargs):
        llm_call_counter["count"] += 1
        yield _LLMChunk("should-not-run")

    monkeypatch.setattr(module, "chat_llm", _fake_chat_llm)

    def _raise_provider_error(**_kwargs):
        raise AskProviderError("provider failed")

    monkeypatch.setattr(module, "stream_ask_provider_response", _raise_provider_error)

    events = list(
        module.handle_input_ask(
            app=app,
            context=_Context(),
            user_info=types.SimpleNamespace(user_id="user-1"),
            attend_id="attend-1",
            input="hello",
            outline_item_info=types.SimpleNamespace(
                shifu_bid="shifu-1",
                bid="outline-1",
                title="Outline",
                position=1,
            ),
            trace_args={"output": ""},
            trace=_DummyTrace(),
        )
    )

    contents = _collect_content_chunks(events)
    assert contents == ["server.learn.askProviderUnavailable"]
    assert llm_call_counter["count"] == 0
    assert events[-1].type == GeneratedType.BREAK


def test_handle_input_ask_provider_then_llm_falls_back_to_llm(app, monkeypatch):
    from flaskr.service.learn import handle_input_ask as module

    ask_provider_config = {
        "provider": "dify",
        "mode": "provider_then_llm",
        "config": {},
    }
    _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config)

    llm_call_counter = {"count": 0}

    def _fake_chat_llm(*_args, **_kwargs):
        llm_call_counter["count"] += 1
        yield _LLMChunk("llm-fallback-answer")

    monkeypatch.setattr(module, "chat_llm", _fake_chat_llm)

    def _provider_then_llm_stream(**kwargs):
        if kwargs.get("provider") == "llm":
            runtime = kwargs.get("runtime")
            if runtime is None or runtime.llm_stream_factory is None:
                return iter([])
            return (
                types.SimpleNamespace(content=chunk.result)
                for chunk in runtime.llm_stream_factory()
            )
        raise AskProviderError("provider failed")

    monkeypatch.setattr(
        module,
        "stream_ask_provider_response",
        _provider_then_llm_stream,
    )

    events = list(
        module.handle_input_ask(
            app=app,
            context=_Context(),
            user_info=types.SimpleNamespace(user_id="user-1"),
            attend_id="attend-1",
            input="hello",
            outline_item_info=types.SimpleNamespace(
                shifu_bid="shifu-1",
                bid="outline-1",
                title="Outline",
                position=1,
            ),
            trace_args={"output": ""},
            trace=_DummyTrace(),
        )
    )

    contents = _collect_content_chunks(events)
    assert "llm-fallback-answer" in contents
    assert llm_call_counter["count"] == 1
    assert events[-1].type == GeneratedType.BREAK


def test_handle_input_ask_provider_response_skips_llm(app, monkeypatch):
    from flaskr.service.learn import handle_input_ask as module

    ask_provider_config = {
        "provider": "coze",
        "mode": "provider_then_llm",
        "config": {"bot_id": "bot-1"},
    }
    _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config)

    llm_call_counter = {"count": 0}

    def _fake_chat_llm(*_args, **_kwargs):
        llm_call_counter["count"] += 1
        yield _LLMChunk("should-not-run")

    monkeypatch.setattr(module, "chat_llm", _fake_chat_llm)

    provider_chunks = [
        types.SimpleNamespace(content="provider-"),
        types.SimpleNamespace(content="answer"),
    ]
    monkeypatch.setattr(
        module,
        "stream_ask_provider_response",
        lambda **_kwargs: iter(provider_chunks),
    )

    events = list(
        module.handle_input_ask(
            app=app,
            context=_Context(),
            user_info=types.SimpleNamespace(user_id="user-1"),
            attend_id="attend-1",
            input="hello",
            outline_item_info=types.SimpleNamespace(
                shifu_bid="shifu-1",
                bid="outline-1",
                title="Outline",
                position=1,
            ),
            trace_args={"output": ""},
            trace=_DummyTrace(),
        )
    )

    contents = _collect_content_chunks(events)
    assert contents == ["provider-", "answer"]
    assert llm_call_counter["count"] == 0
    assert events[-1].type == GeneratedType.BREAK
