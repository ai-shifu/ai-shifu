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


class _DummyNoneQuery:
    """Query that always returns None for .first()."""

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return None


class _DummyLearnGeneratedElementModel:
    element_bid = _DummyColumn()
    deleted = _DummyColumn()
    query = _DummyNoneQuery()


class _DummyFollowUpInfo:
    def __init__(self, ask_provider_config):
        self.ask_prompt = "ASK_PROMPT::{shifu_system_message}"
        self.ask_model = "gpt-test"
        self.model_args = {"temperature": 0.2}
        self.ask_provider_config = ask_provider_config

    def __json__(self):
        return {
            "ask_model": self.ask_model,
            "ask_provider_config": self.ask_provider_config,
        }


class _DummyGeneration:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.end_kwargs = {}

    def end(self, **kwargs):
        self.end_kwargs = kwargs


class _DummySpan:
    def __init__(self):
        self.output = ""
        self.generations = []
        self.updated = {}
        self.span_calls = []
        self.last_span = None
        self.end_kwargs = {}
        self.events = []

    def generation(self, **kwargs):
        generation = _DummyGeneration(**kwargs)
        self.generations.append(generation)
        return generation

    def span(self, **kwargs):
        self.span_calls.append(kwargs)
        self.last_span = _DummySpan()
        return self.last_span

    def update(self, **kwargs):
        self.updated = kwargs

    def event(self, **kwargs):
        self.events.append(kwargs)

    def end(self, output=None, **kwargs):
        self.output = output or ""
        self.end_kwargs = {"output": output, **kwargs}


class _DummyTrace:
    def __init__(self):
        self.span_output = None
        self.updated = {}
        self.last_span = None

    def span(self, **_kwargs):
        self.last_span = _DummySpan()
        return self.last_span

    def update(self, **kwargs):
        self.updated = kwargs


class _LLMChunk:
    def __init__(self, result: str):
        self.result = result


class _Context:
    def __init__(self):
        self._shifu_info = types.SimpleNamespace(use_learner_language=0)
        self.langfuse_outputs = []

    def get_system_prompt(self, _outline_bid: str):
        return "COURSE_PROMPT"

    def append_langfuse_output(self, value: str):
        self.langfuse_outputs.append(value)


def _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config):
    class _DummyLLMSettings:
        def __init__(self, model, temperature):
            self.model = model
            self.temperature = temperature

    class _DummyAskProviderRuntime:
        def __init__(self, llm_stream_factory=None):
            self.llm_stream_factory = llm_stream_factory

    class _DummyAskProviderTimeoutError(AskProviderError):
        pass

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
        module, "LearnGeneratedElement", _DummyLearnGeneratedElementModel
    )
    monkeypatch.setattr(
        module,
        "get_effective_ask_provider_config",
        lambda config: config,
    )
    monkeypatch.setattr(
        module,
        "get_fmt_prompt",
        lambda *_args, **_kwargs: "COURSE_PROMPT",
    )
    monkeypatch.setattr(module, "LLMSettings", _DummyLLMSettings)
    monkeypatch.setattr(module, "AskProviderRuntime", _DummyAskProviderRuntime)
    monkeypatch.setattr(module, "AskProviderError", AskProviderError)
    monkeypatch.setattr(
        module,
        "AskProviderTimeoutError",
        _DummyAskProviderTimeoutError,
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
        "config": {
            "base_url": "https://api.example.com/v1",
            "api_key": "secret-key",
        },
    }
    _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config)

    llm_call_counter = {"count": 0}

    def _fake_chat_llm(*_args, **_kwargs):
        llm_call_counter["count"] += 1
        yield _LLMChunk("should-not-run")

    monkeypatch.setattr(module, "chat_llm", _fake_chat_llm)

    def _raise_provider_error(**_kwargs):
        if False:
            yield None
        raise AskProviderError("provider failed")

    monkeypatch.setattr(module, "stream_ask_provider_response", _raise_provider_error)

    dummy_trace = _DummyTrace()
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
            trace=dummy_trace,
        )
    )

    contents = _collect_content_chunks(events)
    assert contents == ["server.learn.askProviderUnavailable"]
    assert llm_call_counter["count"] == 0
    assert events[-1].type == GeneratedType.BREAK
    assert len(dummy_trace.last_span.generations) == 1
    generation = dummy_trace.last_span.generations[0]
    assert generation.kwargs["model"] == "dify"
    assert generation.end_kwargs["metadata"]["status"] == "error"
    assert generation.end_kwargs["metadata"]["provider_config"]["config"][
        "api_key"
    ] == ("[REDACTED]")


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

    dummy_trace = _DummyTrace()
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
            trace=dummy_trace,
        )
    )

    contents = _collect_content_chunks(events)
    assert contents == ["provider-", "answer"]
    assert llm_call_counter["count"] == 0
    assert events[-1].type == GeneratedType.BREAK
    assert len(dummy_trace.last_span.generations) == 1
    generation = dummy_trace.last_span.generations[0]
    assert generation.kwargs["model"] == "coze"
    assert generation.end_kwargs["output"] == "provider-answer"
    assert generation.end_kwargs["metadata"]["status"] == "success"


def test_handle_input_ask_dify_uses_context_without_follow_up_prompt(app, monkeypatch):
    from flaskr.service.learn import handle_input_ask as module

    ask_provider_config = {
        "provider": "dify",
        "mode": "provider_then_llm",
        "config": {"base_url": "https://dify.example.com", "api_key": "key"},
    }
    _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config)

    captured = {"messages": None}

    def _fake_stream_ask_provider_response(**kwargs):
        if kwargs.get("provider") == "dify":
            captured["messages"] = kwargs.get("messages")
            return iter([types.SimpleNamespace(content="provider-answer")])
        return iter([])

    monkeypatch.setattr(
        module,
        "stream_ask_provider_response",
        _fake_stream_ask_provider_response,
    )
    monkeypatch.setattr(module, "chat_llm", lambda *_args, **_kwargs: iter([]))

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
    assert contents == ["provider-answer"]
    assert captured["messages"] == [
        {"role": "system", "content": "COURSE_PROMPT"},
        {"role": "user", "content": "hello"},
    ]


# ---------------------------------------------------------------------------
# Block ownership and ASK event tests
# ---------------------------------------------------------------------------


def _setup_llm_only_patches(monkeypatch, module, llm_chunks):
    ask_provider_config = {"provider": "llm", "mode": "provider_then_llm", "config": {}}
    _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config)

    def _fake_stream(**_kwargs):
        for chunk in llm_chunks:
            yield types.SimpleNamespace(content=chunk)

    monkeypatch.setattr(module, "stream_ask_provider_response", _fake_stream)


def test_answer_content_uses_answer_block_bid(app, monkeypatch):
    """All teacher-side CONTENT events should use answer block's bid (gb-2)."""
    from flaskr.service.learn import handle_input_ask as module

    _setup_llm_only_patches(monkeypatch, module, ["chunk1", "chunk2"])

    events = list(
        module.handle_input_ask(
            app=app,
            context=_Context(),
            user_info=types.SimpleNamespace(user_id="user-1"),
            attend_id="attend-1",
            input="question",
            outline_item_info=types.SimpleNamespace(
                shifu_bid="s1", bid="o1", title="T", position=1
            ),
            trace_args={"output": ""},
            trace=_DummyTrace(),
        )
    )

    content_events = [e for e in events if e.type == GeneratedType.CONTENT]
    # ask block = gb-1, answer block = gb-2
    for e in content_events:
        assert e.generated_block_bid == "gb-2"


def test_ask_event_emitted(app, monkeypatch):
    """An ASK event should be emitted with anchor_element_bid."""
    from flaskr.service.learn import handle_input_ask as module

    _setup_llm_only_patches(monkeypatch, module, ["reply"])

    events = list(
        module.handle_input_ask(
            app=app,
            context=_Context(),
            user_info=types.SimpleNamespace(user_id="user-1"),
            attend_id="attend-1",
            input="my question",
            outline_item_info=types.SimpleNamespace(
                shifu_bid="s1", bid="o1", title="T", position=1
            ),
            trace_args={"output": ""},
            trace=_DummyTrace(),
            anchor_element_bid="elem_anchor_123",
        )
    )

    ask_events = [e for e in events if e.type == GeneratedType.ASK]
    assert len(ask_events) == 1
    assert ask_events[0].content == "my question"
    assert ask_events[0].anchor_element_bid == "elem_anchor_123"


def test_ask_event_uses_ask_block_bid(app, monkeypatch):
    """ASK uses ask block bid while teacher content stays on answer block bid."""
    from flaskr.service.learn import handle_input_ask as module

    _setup_llm_only_patches(monkeypatch, module, ["reply"])

    events = list(
        module.handle_input_ask(
            app=app,
            context=_Context(),
            user_info=types.SimpleNamespace(user_id="user-1"),
            attend_id="attend-1",
            input="my question",
            outline_item_info=types.SimpleNamespace(
                shifu_bid="s1", bid="o1", title="T", position=1
            ),
            trace_args={"output": ""},
            trace=_DummyTrace(),
            anchor_element_bid="elem_anchor_123",
        )
    )

    ask_events = [e for e in events if e.type == GeneratedType.ASK]
    content_events = [e for e in events if e.type == GeneratedType.CONTENT]

    assert len(ask_events) == 1
    assert len(content_events) == 1
    assert ask_events[0].generated_block_bid == "gb-1"
    assert content_events[0].generated_block_bid == "gb-2"


def test_guardrail_uses_answer_block_bid(app, monkeypatch):
    """When guardrail triggers, CONTENT events should still use answer block bid."""
    from flaskr.service.learn import handle_input_ask as module

    ask_provider_config = {"provider": "llm", "mode": "provider_then_llm", "config": {}}
    _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config)
    monkeypatch.setattr(
        module,
        "check_text_with_llm_response",
        lambda *_args, **_kwargs: ["guardrail response"],
    )

    events = list(
        module.handle_input_ask(
            app=app,
            context=_Context(),
            user_info=types.SimpleNamespace(user_id="user-1"),
            attend_id="attend-1",
            input="bad input",
            outline_item_info=types.SimpleNamespace(
                shifu_bid="s1", bid="o1", title="T", position=1
            ),
            trace_args={"output": ""},
            trace=_DummyTrace(),
        )
    )

    content_events = [e for e in events if e.type == GeneratedType.CONTENT]
    assert len(content_events) == 1
    # answer block = gb-2 (ask block = gb-1)
    assert content_events[0].generated_block_bid == "gb-2"
    # ASK event should still be emitted before guardrail
    ask_events = [e for e in events if e.type == GeneratedType.ASK]
    assert len(ask_events) == 1


def test_handle_input_ask_nests_follow_up_span_under_parent_observation(
    app, monkeypatch
):
    from flaskr.service.learn import handle_input_ask as module

    ask_provider_config = {
        "provider": "coze",
        "mode": "provider_then_llm",
        "config": {"bot_id": "bot-1"},
    }
    _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config)
    monkeypatch.setattr(
        module,
        "stream_ask_provider_response",
        lambda **_kwargs: iter([types.SimpleNamespace(content="provider-answer")]),
    )
    monkeypatch.setattr(module, "chat_llm", lambda *_args, **_kwargs: iter([]))

    context = _Context()
    trace = _DummyTrace()
    root_span = _DummySpan()

    events = list(
        module.handle_input_ask(
            app=app,
            context=context,
            user_info=types.SimpleNamespace(user_id="user-1"),
            attend_id="attend-1",
            input="hello",
            outline_item_info=types.SimpleNamespace(
                shifu_bid="shifu-1",
                bid="outline-1",
                title="Outline",
                position=1,
            ),
            trace_args={},
            trace=trace,
            parent_observation=root_span,
        )
    )

    contents = _collect_content_chunks(events)
    assert contents == ["provider-answer"]
    assert trace.last_span is None
    assert len(root_span.span_calls) == 1
    assert root_span.last_span is not None
    assert len(root_span.last_span.generations) == 1
    assert root_span.last_span.generations[0].kwargs["model"] == "coze"
    assert trace.updated["input"] == "hello"
    assert root_span.updated["output"] == "provider-answer"
    assert trace.updated["output"] == "provider-answer"
    assert context.langfuse_outputs == ["provider-answer"]


def test_handle_input_ask_guardrail_finalizes_trace_and_root_span(app, monkeypatch):
    from flaskr.service.learn import handle_input_ask as module

    ask_provider_config = {"provider": "llm", "mode": "provider_then_llm", "config": {}}
    _setup_handle_input_ask_patches(monkeypatch, module, ask_provider_config)
    monkeypatch.setattr(
        module,
        "check_text_with_llm_response",
        lambda *_args, **_kwargs: ["guardrail response"],
    )

    context = _Context()
    trace = _DummyTrace()
    root_span = _DummySpan()

    list(
        module.handle_input_ask(
            app=app,
            context=context,
            user_info=types.SimpleNamespace(user_id="user-1"),
            attend_id="attend-1",
            input="blocked",
            outline_item_info=types.SimpleNamespace(
                shifu_bid="s1",
                bid="o1",
                title="T",
                position=1,
            ),
            trace_args={},
            trace=trace,
            parent_observation=root_span,
        )
    )

    assert root_span.last_span is not None
    assert root_span.last_span.output == "guardrail response"
    assert trace.updated["input"] == "blocked"
    assert root_span.updated["output"] == "guardrail response"
    assert trace.updated["output"] == "guardrail response"
    assert context.langfuse_outputs == ["guardrail response"]
