"""
Shared model rules for max_tokens inference.

This module contains pattern-based rules for inferring max_tokens values
from model names. It's designed to have no Flask dependencies so it can
be imported by both the runtime code and utility scripts.
"""

import re
from typing import List, Optional, Tuple

# Pattern rules to infer max_tokens (output limit) at runtime.
# NOTE: max_tokens is the OUTPUT limit, NOT context window (input+output).
# Each rule is (pattern, max_tokens). First match wins.
# Official documentation links are provided as comments.
MAX_TOKENS_PATTERN_RULES: List[Tuple[re.Pattern, int]] = [
    # -------------------------------------------------------------------------
    # DeepSeek - max_tokens: 8192 (default 4096)
    # Doc: https://api-docs.deepseek.com/api/create-chat-completion
    # -------------------------------------------------------------------------
    (re.compile(r"deepseek", re.IGNORECASE), 8192),
    # -------------------------------------------------------------------------
    # ERNIE (Baidu) - max_output_tokens: 8192 for most models
    # Doc: https://cloud.baidu.com/doc/WENXINWORKSHOP/s/Nlks5zkzu
    # ERNIE-4.0/4.5/5.0 series: max 8192
    # ERNIE-*-128K: 4096 (larger context, limited output)
    # -------------------------------------------------------------------------
    (re.compile(r"ernie.*128k", re.IGNORECASE), 4096),
    (re.compile(r"ernie", re.IGNORECASE), 8192),
    # -------------------------------------------------------------------------
    # Qwen (Alibaba) - max_tokens: 8192 (default 1024 for most models)
    # Doc: https://help.aliyun.com/zh/model-studio/developer-reference/use-qwen-by-calling-api
    # qwen-max/plus/turbo: max 8192
    # -------------------------------------------------------------------------
    (re.compile(r"qwen|qvq|qwq", re.IGNORECASE), 8192),
    # -------------------------------------------------------------------------
    # GLM (Zhipu) - max_tokens: 4096
    # Doc: https://bigmodel.cn/dev/api/normal-model/glm-4
    # GLM-4/GLM-4-Flash/GLM-4-Air: max 4096
    # GLM-4-Long: max 4096 (longer context, same output limit)
    # -------------------------------------------------------------------------
    (re.compile(r"glm.*(?:thinking|rumination)", re.IGNORECASE), 4096),
    (re.compile(r"glm", re.IGNORECASE), 4096),
    # -------------------------------------------------------------------------
    # Doubao (ByteDance/Volcengine) - max_tokens: 4096
    # Doc: https://www.volcengine.com/docs/82379/1298454
    # Doubao-pro/lite-32k: max 4096
    # Doubao-*-thinking: max 16384 (extended for reasoning output)
    # -------------------------------------------------------------------------
    (re.compile(r"doubao.*thinking", re.IGNORECASE), 16384),
    (re.compile(r"doubao", re.IGNORECASE), 4096),
    # -------------------------------------------------------------------------
    # Kimi/Moonshot - max_tokens varies by model
    # Doc: https://platform.moonshot.cn/docs/api/chat
    # moonshot-v1-*: max 4096
    # kimi-k2 via ARK: max 32768 (error: expected <= 32768)
    # -------------------------------------------------------------------------
    (re.compile(r"kimi-k2", re.IGNORECASE), 32768),
    (re.compile(r"kimi|moonshot", re.IGNORECASE), 4096),
    # -------------------------------------------------------------------------
    # OpenAI GPT models (if not in LiteLLM registry)
    # Doc: https://platform.openai.com/docs/models
    # -------------------------------------------------------------------------
    (re.compile(r"gpt-4o|gpt-4-turbo", re.IGNORECASE), 16384),
    (re.compile(r"gpt-4", re.IGNORECASE), 8192),
    (re.compile(r"gpt-3\.5", re.IGNORECASE), 4096),
]

# Canonical rules for mapping model names to LiteLLM-recognized keys.
# Used by generate_llm_model_map.py to create aliases.
LITELLM_CANONICAL_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"deepseek-?r1", re.IGNORECASE), "deepseek-reasoner"),
    (re.compile(r"deepseekr1", re.IGNORECASE), "deepseek-reasoner"),
    (re.compile(r"deepseek-?v[23]", re.IGNORECASE), "deepseek-chat"),
    (re.compile(r"deepseek-chat", re.IGNORECASE), "deepseek-chat"),
]


def infer_max_tokens_by_pattern(model: str) -> Optional[int]:
    """Infer max_tokens using pattern rules. Returns None if no match."""
    normalized = model.strip().lower()
    # Strip provider prefixes (e.g., "ark/deepseek-v3" -> "deepseek-v3")
    while "/" in normalized:
        _, normalized = normalized.split("/", 1)

    for pattern, max_tokens in MAX_TOKENS_PATTERN_RULES:
        if pattern.search(normalized):
            return max_tokens
    return None


def canonicalize_to_litellm(model: str) -> Optional[str]:
    """
    Canonicalize a model name to a LiteLLM-recognized key using pattern rules.
    Returns None if no matching rule is found.
    """
    normalized = model.strip().lower().replace(".", "-")
    # Strip provider prefixes
    while "/" in normalized:
        _, normalized = normalized.split("/", 1)

    for pattern, litellm_key in LITELLM_CANONICAL_RULES:
        if pattern.search(normalized):
            return litellm_key
    return None
