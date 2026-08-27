"""Extract questionnaire evidence from untrusted external assistant answers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from flaskr.service.profile.api import LEARNER_PROFILE_NICKNAME_MAX_LENGTH
from flaskr.service.profile_research.session import ProfileResearchValidationError
from flaskr.util.prompt_loader import load_prompt_template

if TYPE_CHECKING:
    from flaskr.service.profile_research.session import _ProfileResearchSession
    from markdown_flow import LLMProvider


def parse_assistant_answers(
    provider: LLMProvider, session: _ProfileResearchSession, raw_text: str
) -> tuple[str, str]:
    """Return supplemental evidence and a separately stated nickname."""
    result = provider.complete(
        messages=[
            {
                "role": "system",
                "content": load_prompt_template("profile_research_assistant_answers"),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "questionnaire": session.assistant_prompt,
                        "manual_variables": session.variables,
                        "conversation": session.context,
                        "external_answer": raw_text,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        model=session.model,
        temperature=0,
    )
    try:
        payload = json.loads(result)
    except (TypeError, ValueError) as exc:
        msg = "assistant answers could not be extracted"
        raise ProfileResearchValidationError(msg) from exc
    if not isinstance(payload, dict) or set(payload) != {"answers", "nickname"}:
        msg = "assistant answers have an invalid shape"
        raise ProfileResearchValidationError(msg)
    answers = payload["answers"]
    nickname = payload["nickname"]
    if not isinstance(answers, str) or not isinstance(nickname, str):
        msg = "assistant answers must contain text"
        raise ProfileResearchValidationError(msg)
    answers, nickname = answers.strip(), nickname.strip()
    if len(answers) > 10_000 or len(nickname) > LEARNER_PROFILE_NICKNAME_MAX_LENGTH:
        msg = "assistant answers exceed their limits"
        raise ProfileResearchValidationError(msg)
    return answers, nickname
