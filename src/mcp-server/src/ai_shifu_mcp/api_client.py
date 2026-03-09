"""Thin async HTTP wrapper around the AI-Shifu REST API."""

import os

import httpx


class AiShifuClient:
    """Manages authentication and HTTP calls to AI-Shifu.

    The client expects every response to follow the standard envelope::

        {"code": 0, "message": "success", "data": ...}

    Non-zero ``code`` values are raised as ``AiShifuAPIError``.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.base_url = (base_url or os.environ["AISHIFU_BASE_URL"]).rstrip("/")
        self.api_key = api_key or os.environ["AISHIFU_API_KEY"]
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Create the underlying ``httpx.AsyncClient``."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=60.0,
        )

    async def close(self) -> None:
        """Gracefully close the HTTP client."""
        if self._client:
            await self._client.aclose()

    # ── HTTP helpers ──────────────────────────────────

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Send a request and unwrap the ``{code, message, data}`` envelope.

        Raises
        ------
        AiShifuAPIError
            When the response ``code`` is non-zero.
        httpx.HTTPStatusError
            When the HTTP status itself indicates failure.
        """
        resp = await self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise AiShifuAPIError(body.get("code", -1), body.get("message", "Unknown error"))
        return body.get("data")

    async def get(self, path: str, **kw):
        return await self._request("GET", path, **kw)

    async def post(self, path: str, **kw):
        return await self._request("POST", path, **kw)

    async def put(self, path: str, **kw):
        return await self._request("PUT", path, **kw)

    async def delete(self, path: str, **kw):
        return await self._request("DELETE", path, **kw)

    async def patch(self, path: str, **kw):
        return await self._request("PATCH", path, **kw)


class AiShifuAPIError(Exception):
    """Raised when the AI-Shifu API returns a non-zero business code."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"AI-Shifu API error ({code}): {message}")
