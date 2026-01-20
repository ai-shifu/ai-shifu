from types import SimpleNamespace
from typing import Generator, List


class FakeLLMResponse:
    def __init__(
        self,
        result: str,
        *,
        chunk_id: str = "mock-1",
        is_end: bool = False,
        is_truncated: bool = False,
        finish_reason: str = "stop",
        usage=None,
    ):
        self.id = chunk_id
        self.is_end = is_end
        self.is_truncated = is_truncated
        self.result = result
        self.finish_reason = finish_reason
        self.usage = usage
        self.choices = [SimpleNamespace(delta=SimpleNamespace(content=result))]


def _stream_chunks(stream: bool) -> List[str]:
    if stream:
        return ["mock-", "llm"]
    return ["mock-llm"]


def fake_invoke_llm(*args, **kwargs) -> Generator[FakeLLMResponse, None, None]:
    stream = bool(kwargs.get("stream", False))
    chunks = _stream_chunks(stream)
    for idx, chunk in enumerate(chunks, start=1):
        yield FakeLLMResponse(
            chunk,
            chunk_id=f"mock-invoke-{idx}",
            is_end=idx == len(chunks),
            finish_reason="stop" if idx == len(chunks) else None,
        )


def fake_chat_llm(*args, **kwargs) -> Generator[FakeLLMResponse, None, None]:
    stream = bool(kwargs.get("stream", False))
    chunks = _stream_chunks(stream)
    for idx, chunk in enumerate(chunks, start=1):
        yield FakeLLMResponse(
            chunk,
            chunk_id=f"mock-chat-{idx}",
            is_end=idx == len(chunks),
            finish_reason="stop" if idx == len(chunks) else None,
        )


def fake_get_allowed_models() -> list[str]:
    return []


def fake_get_current_models(app) -> list[dict[str, str]]:
    return []
