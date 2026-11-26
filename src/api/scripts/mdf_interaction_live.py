"""Run the lesson gateway in a standalone evaluation process."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pydantic_ai.models import Model


def _discard_usage(*_args: object, **_kwargs: object) -> None:
    """Discard application metering while preserving provider usage in the stream."""


@contextmanager
def build_live_model(model_name: str) -> Iterator[Model]:
    """Use the configured provider without starting application services or telemetry."""
    from dotenv import load_dotenv
    from flask import Flask, has_app_context

    if has_app_context():
        message = "Live interaction evaluation requires a standalone process."
        raise ValueError(message)

    # The gateway discovers providers at import time. Load the same local provider
    # settings as the backend without importing the application factory.
    with (
        patch.dict(os.environ, {"LITELLM_LOG": "ERROR"}),
        patch.object(logging.getLogger("flaskr.api.llm"), "disabled", new=True),
        patch.object(logging.getLogger("LiteLLM"), "disabled", new=True),
    ):
        if not os.getenv("SKIP_LOAD_DOTENV"):
            load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

        from flaskr.api import llm
        from flaskr.api.langfuse import (
            LangfuseObservationHandle,
            MockClient,
            create_advancement_trace_id,
        )
        from flaskr.api.llm.markdownflow_model import GatewayModel
        from flaskr.service.common.models import AppError

        model_name = model_name.strip()
        message = (
            "Model unavailable. Use a routed model ID and configure its provider "
            "in the shell or src/api/.env."
        )
        try:
            parameters, _, _ = llm.get_litellm_params_and_model(model_name)
        except AppError:
            raise ValueError(message) from None
        if not parameters:
            raise ValueError(message)

        # GatewayModel uses Flask for logging. Keeping the app out of context
        # makes runtime configuration read only from the environment.
        app = Flask("mdf_interaction_eval")
        span = LangfuseObservationHandle(MockClient(), create_advancement_trace_id())
        with (
            patch.object(app.logger, "disabled", new=True),
            patch.object(llm, "record_llm_usage", _discard_usage),
            patch.object(llm.litellm, "global_disable_no_log_param", new=False),
            patch.object(llm.litellm, "suppress_debug_info", new=True),
        ):
            yield GatewayModel(
                app,
                model_name,
                user_id="",
                span=span,
                generation_name="mdf_interaction_evaluation",
                timeout=45,
                retry_deadline_seconds=60,
                num_retries=0,
                **{"no-log": True},
            )
