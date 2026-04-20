from __future__ import annotations
# ruff: noqa: E402

from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import sys
from typing import Callable, Iterator, Literal, TypedDict

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from dotenv import load_dotenv
from langfuse import Langfuse
from langfuse.client import StatefulTraceClient
from langfuse.model import ModelUsage
from markdown_flow import MarkdownFlow, ProcessMode
from markdown_flow.enums import BlockType
from markdown_flow.llm import LLMProvider
from openai import OpenAI

BASE_SYSTEM_PROMPT = "Follow the system and user instructions precisely."
DOCUMENT_PROMPT = """# 角色
你叫孙志岗，是一名 AI 大模型专家，也是专业的教师。你使用的语言是 {{sys_user_language}}

# 任务
- 你在讲的课叫《跟 AI 学 AI 通识》，涉及大语言模型、AI 的通识知识
- 你在一对一授课，听课的只有一个人
- 要按照给你的风格和格式要求，遵从指令要求，向用户讲课
- 不要引导下一步动作，比如提问、设问
- 不要做自我介绍
- 不要打招呼

# 风格
- 用罗振宇的讲课逻辑和说服技巧做输出
- 【金句密集】 输出对仗、押尾或类比式金句（如“乐观者不是相信永远晴天，而是随手撑伞”）
- 【口语共情】 大量使用“咱们”“咱”与听众并肩，制造陪聊感
- 【设问驱动】 频繁抛出“你有没有想过…？”“你注意到没有...？”等开放式问题
- 【跨界引用】 随手拿文学、商业、历史、科技作类比，提升思维高度
- 称呼用户时可以用`你` 或者学员的称呼，但一定不要用 `大家`、`同学们` 等称呼多人的方式

# 学员
- 假定学员对 AI 完全不了解。要用他容易听懂的方式讲课

# 格式
- 按照 Markdown 格式输出
- 输出不要有任何级别的标题（如#, ##, ### 或 H1, H2 之类）
- 在中文和英文，中文和数字之间，要加个空格。例如：「AI 大模型」「准确率 99%」
- 重点内容（关键步骤/颠覆认知点/观点总结）做加粗处理

"""

DEFAULT_INITIAL_VARIABLES: dict[str, str | list[str]] = {
    "sys_user_language": "中文",
}

DEFAULT_USER_INPUTS: dict[str, list[str]] = {
    "agreeed_points": ["AI 是一种工具", "每种 AI 产品都需要学习使用方法"],
    "sys_user_nickname": ["小明"],
    "sys_user_background": ["互联网行业产品经理，5 年经验"],
    "purpose": ["提升竞争力"],
}

REPORT_FINAL_SHINGLE_SIZE = 5
REPORT_NEAR_DUPLICATE_THRESHOLD = 0.85
REPORT_REPETITION_SHINGLE_SIZE = 7
REPORT_REPEAT_THRESHOLD = 0.2

STRATEGY_BLOCK_PROMPT_AS_USER_IGNORE_USER_INPUT = (
    "block_prompt_as_user_ignore_user_input"
)

TEST_DOCUMENT = """===## 对 AI 的常见误解===

- 问个好，说下自己的名字，表示初次见面很高兴
- 表示很想知道用户是否同意下面几个观点。只提问，不要对观点做解释：
   1. AI 是一种工具
   2. 每种 AI 产品都需要学习使用方法
   3. 打造 AI 产品是技术高手的事情

?[%{{agreeed_points}} AI 是一种工具 || 每种 AI 产品都需要学习使用方法 || 打造 AI 产品是技术高手的事情 || 都不同意 ]

- 首先表示，在辅导过几十家企业、上万人用 AI 提升业绩、效率之后，你总结出这三种观点是多数人都会有的对 AI 的误解
- 用户同意的观点是'''{{agreeed_points}}'''。重复讲下用户的回答，然后根据用户的回答，遵照如下指引组合应答：
  - 如果用户回答的是「都不同意」，赞赏用户的见识，然后表示这门课整体上可能对用户的帮助不大，可能某些地方会有启发，可以按需决定是否继续学习
  - 如果用户同意的观点包含「AI 是一种工具」，表示这个误解是导致很多人用不好 AI 的罪魁祸首。工具具有确定性，而 AI 其实更像人，不可能永远不犯错。应该像和人协作一样，基于一定出错的假设，通过各种管理手段（比如事先讨论、阶段 review 等）提升正确率
  - 如果用户同意的观点包含「每种 AI 产品都需要学习使用方法」，表示这是延续使用传统软件的思维，那些软件受技术限制，都只能让人去适应它们，所以要学习。但 AI 是一种在无限靠近人、适应人的技术，所以只要掌握了最基本的 AI 通识，就像掌握了和人沟通、协作的基本法则一样，对任何新出的 AI 产品，都不需要学习直接就能用出最好的效果
  - 如果用户同意的观点包含「打造 AI 产品是技术高手的事情 」，表示这是这个时代最大的遗憾。很多人因为有这个误解，所以一直在等着别人发明适合自己的工具，或者花高价请人开发。其实掌握了 AI 通识之后，最懂自己需要什么的人，能定制出最适合自己的 AI 产品。这个过程就和教实习生帮自己做事别无二致
- 盛情邀请用户继续学习，然后礼貌地做下自我介绍，你是 AI 师傅的创始人，曾是哈尔滨工业大学的副教授，后来在网易和得到 App 工作过。你的工作领域主要是互联网、人工智能和教育的结合。已经帮助各行各业的几万人转型成 AI 专业人士，还帮助数十家企业成功落地 AI 到生产实践
- 在 ChatGPT 问世的第 6 天，你就注册并被深深地震撼。在深入了解这个技术变革之后，你给自己定了一个目标：===**帮助 100 万人顺利走进 AGI 时代**===
- 在实现这个目标的过程中，你发现用好 AI 的前提是用户需要知道如何调教 AI，发挥 AI 的长处，弥补 AI 的短处。调教好了，可以一句话就让 AI 帮用户完成繁琐的工作
- 这门课就是讲如何调教 AI 的，帮用户成为 AI 的主人
- 而且，调教的思路非常符合人的直觉，最核心的只需要理解三件事。画 mindmap 图来呈现，所有子节点都在右边：
    1. 明白 AI 的一切表现都是概率的结果；
    2. 知道 AI 的知识来自哪里；
    3. 知道如何操纵 AI 的记忆
---
- 向用户强调用户可能还没注意到的，这门用 AI 师傅制作的课本身就是 AI 适应人的例证
- 用户所看到的一切都不是提前写好的固定文字，而是由 AI 此时此刻量身定制的。而且，了解越多用户的喜好和个人情况，就能越个性化地讲课，提升学习体验和效果。
- 询问用户希望怎样被称呼？

?[%{{sys_user_nickname}}...我可以怎样称呼你？]

- 用户叫`{{sys_user_nickname}}`，向用户打个友好的招呼，然后真诚地赞美一下这个称呼
- 向用户解释说，为让课程中的案例可以贴合用户，需要知道用户现在是做什么的。
- 请用户详细地从行业、岗位、工作年限、当前状态等角度介绍自己，越详细越好。给出 3 个例子
- 请用户一定要输入自己的真实情况，这样后面就能匹配用户的情况讲课

?[%{{sys_user_background}}我不告诉你 | ...你的身份背景、当前状态如何？]

- 用户的背景是`{{sys_user_background}}`，真心地表达一下赞美和同理心
- 用逐条列出的格式，聊一聊 AI 对背景是`{{sys_user_background}}`的人能产生的帮助。既要分析当下，也要分析 1-5 年后，并且假定 AGI 会在 5 年内实现
- 问用户希望 AI 能帮自己解决什么具体问题。你会在后续课程中围绕这个目标进行授课。

?[%{{purpose}} 还没想好 |...学 AI 的目的是什么？]

已知用户背景：{{sys_user_background}}
已知用户的学习目的：{{purpose}}

- 客观分析一下用户的学习目的的可行性
- 告知用户，随时可以回到这里修改自己的目的。
"""


class MultiOpenAICompatibleProvider(LLMProvider):
    def __init__(self):
        self._clients: dict[tuple[str, str, float, int], OpenAI] = {}
        self._completion_cache: dict[str, str] = {}
        self._timeout = float(os.getenv("MDFLOW_TEST_REQUEST_TIMEOUT") or "120")
        self._max_retries = int(os.getenv("MDFLOW_TEST_MAX_RETRIES") or "0")
        self._current_trace: StatefulTraceClient | None = None
        self._run_metadata: dict[str, object] = {}
        self._call_metadata: dict[str, object] = {}
        self._call_seq = 0

    def set_current_trace(self, trace: StatefulTraceClient | None) -> None:
        """Set the current trace for generation tracking. Each process call should have its own trace."""
        self._current_trace = trace
        self._call_seq = 0

    def clear_trace(self) -> None:
        self._current_trace = None
        self._run_metadata = {}
        self._call_metadata = {}
        self._call_seq = 0

    def set_run_metadata(self, **metadata: object) -> None:
        self._run_metadata = dict(metadata)

    def set_call_metadata(self, **metadata: object) -> None:
        self._call_metadata = dict(metadata)

    def _openai_request_params(
        self, provider_name: str, model: str, temperature: float | None
    ) -> dict[str, object]:
        if provider_name != "openai":
            return {"temperature": temperature} if temperature is not None else {}

        t = float(temperature) if temperature is not None else 0.0
        if model.startswith("gpt-5.2"):
            return {
                "reasoning_effort": "none",
                "temperature": t,
            }
        if model.startswith("gpt-5.1"):
            return {
                "reasoning_effort": "none",
                "temperature": 1,
            }
        if model.startswith("gpt-5-pro"):
            return {
                "reasoning_effort": "none",
            }
        if model.startswith("gpt-5"):
            return {
                "reasoning_effort": "minimal",
                "temperature": 1,
            }
        return {"temperature": t}

    def _cache_key(
        self,
        *,
        provider_name: str,
        base_url: str,
        model: str,
        params: dict[str, object],
        messages: list[dict[str, str]],
    ) -> str:
        payload = {
            "provider": provider_name,
            "base_url": base_url,
            "model": model,
            "params": params,
            "messages": messages,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _start_generation(
        self,
        *,
        model: str | None,
        messages: list[dict[str, str]],
        provider_name: str,
        base_url: str,
        request_params: dict[str, object],
        cached: bool,
    ):
        # Create generation on current trace (each process call has its own trace)
        if not self._current_trace:
            return None

        self._call_seq += 1
        call_seq = self._call_seq
        action = self._call_metadata.get("action")
        generation_name_parts = ["generation"]
        if action:
            generation_name_parts.append(str(action))
        generation_name_parts.append(str(call_seq))
        generation_name = "/".join(generation_name_parts)

        metadata = {
            **self._run_metadata,
            **self._call_metadata,
            "provider": provider_name,
            "base_url": base_url,
            "request_params": request_params,
            "cached": cached,
        }
        try:
            return self._current_trace.generation(
                name=generation_name,
                model=model or "",
                input=messages,
                metadata=metadata,
                start_time=datetime.now(timezone.utc),
            )
        except Exception:
            return None

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        provider_name, api_key, base_url, resolved_model = self._resolve_provider(
            model or ""
        )
        client = self._get_client(api_key, base_url)
        request_params = self._openai_request_params(
            provider_name, resolved_model, temperature
        )
        cache_key = self._cache_key(
            provider_name=provider_name,
            base_url=base_url,
            model=resolved_model,
            params=request_params,
            messages=messages,
        )
        cached = self._completion_cache.get(cache_key)
        generation = self._start_generation(
            model=resolved_model,
            messages=messages,
            provider_name=provider_name,
            base_url=base_url,
            request_params=request_params,
            cached=cached is not None,
        )
        if cached is not None:
            if generation:
                generation.end(
                    output=cached,
                    end_time=datetime.now(timezone.utc),
                    level="DEBUG",
                    status_message="cache_hit",
                )
            return cached

        kwargs: dict[str, object] = {
            "model": resolved_model,
            "messages": messages,
            **request_params,
        }
        try:
            resp = client.chat.completions.create(**kwargs)
            if not resp.choices:
                raise RuntimeError(f"Empty response choices (provider={provider_name})")
            content = resp.choices[0].message.content or ""
            self._completion_cache[cache_key] = content
            usage = None
            resp_usage = getattr(resp, "usage", None)
            if resp_usage:
                prompt_tokens = getattr(resp_usage, "prompt_tokens", None)
                completion_tokens = getattr(resp_usage, "completion_tokens", None)
                total_tokens = getattr(resp_usage, "total_tokens", None)
                if (
                    prompt_tokens is not None
                    and completion_tokens is not None
                    and total_tokens is not None
                ):
                    usage = ModelUsage(
                        unit="TOKENS",
                        input=int(prompt_tokens),
                        output=int(completion_tokens),
                        total=int(total_tokens),
                    )
            if generation:
                generation.end(
                    output=content,
                    usage=usage,
                    end_time=datetime.now(timezone.utc),
                )
            return content
        except Exception as exc:
            if generation:
                generation.end(
                    end_time=datetime.now(timezone.utc),
                    level="ERROR",
                    status_message=str(exc),
                )
            raise

    def stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
    ) -> Iterator[str]:
        provider_name, api_key, base_url, resolved_model = self._resolve_provider(
            model or ""
        )
        client = self._get_client(api_key, base_url)
        request_params = self._openai_request_params(
            provider_name, resolved_model, temperature
        )
        generation = self._start_generation(
            model=resolved_model,
            messages=messages,
            provider_name=provider_name,
            base_url=base_url,
            request_params=request_params,
            cached=False,
        )
        kwargs: dict[str, object] = {
            "model": resolved_model,
            "messages": messages,
            "stream": True,
            **request_params,
        }
        try:
            stream = client.chat.completions.create(**kwargs)
            content_parts: list[str] = []
            for chunk in stream:
                if (
                    chunk.choices
                    and chunk.choices[0].delta
                    and chunk.choices[0].delta.content
                ):
                    content_parts.append(chunk.choices[0].delta.content)
                    yield chunk.choices[0].delta.content
            if generation:
                generation.end(
                    output="".join(content_parts),
                    end_time=datetime.now(timezone.utc),
                )
        except Exception as exc:
            if generation:
                generation.end(
                    end_time=datetime.now(timezone.utc),
                    level="ERROR",
                    status_message=str(exc),
                )
            raise

    def _get_client(self, api_key: str, base_url: str) -> OpenAI:
        key = (api_key, base_url, self._timeout, self._max_retries)
        client = self._clients.get(key)
        if client:
            return client
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )
        self._clients[key] = client
        return client

    def _resolve_provider(self, model: str) -> tuple[str, str, str, str]:
        model = (model or "").strip()
        if model.startswith("qwen/"):
            model = "dashscope/" + model[len("qwen/") :]
        elif model.startswith("glm/"):
            model = "zai/" + model[len("glm/") :]
        elif model.startswith("ark/"):
            model = "volcengine/" + model[len("ark/") :]
        elif "/" not in model and model.startswith("deepseek"):
            model = f"deepseek/{model}"
        elif "/" not in model and model.startswith("gemini-"):
            model = f"gemini/{model}"

        # OpenAI (default)
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        openai_base_env = os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).strip()
        openai_base_override = os.getenv("MDFLOW_TEST_OPENAI_BASE_URL", "").strip()
        if openai_base_override:
            openai_base = openai_base_override
        elif model.startswith("gpt-5"):
            openai_base = "https://api.openai.com/v1"
        else:
            openai_base = openai_base_env

        # DeepSeek
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        deepseek_base = (
            os.getenv("DEEPSEEK_API_BASE", "")
            or os.getenv("DEEPSEEK_API_URL", "")
            or "https://api.deepseek.com"
        ).strip()

        # DashScope (Qwen) (OpenAI-compatible mode)
        dashscope_key = (
            os.getenv("DASHSCOPE_API_KEY", "") or os.getenv("QWEN_API_KEY", "")
        ).strip()
        dashscope_base = (
            os.getenv("DASHSCOPE_API_BASE", "")
            or os.getenv("QWEN_API_URL", "")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).strip()

        # Z.AI (OpenAI-compatible)
        zai_key = (
            os.getenv("ZAI_API_KEY", "")
            or os.getenv("BIGMODEL_API_KEY", "")
            or os.getenv("GLM_API_KEY", "")
        ).strip()
        zai_base = os.getenv("ZAI_API_BASE", "https://api.z.ai/api/paas/v4").strip()

        # Volcengine (OpenAI-compatible)
        volcengine_key = (
            os.getenv("VOLCENGINE_API_KEY", "") or os.getenv("ARK_API_KEY", "")
        ).strip()
        volcengine_base = os.getenv(
            "VOLCENGINE_API_BASE", "https://ark.cn-beijing.volces.com/api/v3"
        ).strip()

        if model.startswith("deepseek/"):
            return _require(
                "deepseek",
                deepseek_key,
                deepseek_base,
                model[len("deepseek/") :],
            )
        if model.startswith("dashscope/"):
            return _require(
                "dashscope",
                dashscope_key,
                dashscope_base,
                model[len("dashscope/") :],
            )
        if model.startswith("zai/"):
            return _require("zai", zai_key, zai_base, model[len("zai/") :])
        if model.startswith("volcengine/"):
            return _require(
                "volcengine",
                volcengine_key,
                volcengine_base,
                model[len("volcengine/") :],
            )

        return _require("openai", openai_key, openai_base, model)


def _require(
    provider: str, api_key: str, base_url: str, model: str
) -> tuple[str, str, str, str]:
    if not api_key:
        raise RuntimeError(f"Missing API key for provider '{provider}'")
    if not base_url:
        raise RuntimeError(f"Missing base_url for provider '{provider}'")
    return provider, api_key, base_url, model


def _load_env() -> None:
    api_root = Path(__file__).resolve().parents[1]
    env_path = api_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _strip_quotes(value: str) -> str:
    v = (value or "").strip()
    if (v.startswith("'") and v.endswith("'")) or (
        v.startswith('"') and v.endswith('"')
    ):
        return v[1:-1]
    return v


def _bool_env(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _init_langfuse_client() -> Langfuse | None:
    if not _bool_env("MDFLOW_TEST_LANGFUSE_ENABLED", True):
        return None
    public_key = _strip_quotes(os.getenv("LANGFUSE_PUBLIC_KEY", ""))
    secret_key = _strip_quotes(os.getenv("LANGFUSE_SECRET_KEY", ""))
    host = _strip_quotes(os.getenv("LANGFUSE_HOST", ""))
    if not (public_key and secret_key and host):
        return None
    try:
        return Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    except Exception:
        return None


def _models_from_env() -> list[str]:
    raw = (os.getenv("MDFLOW_TEST_MODELS") or "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]

    return ["gpt-5", "deepseek/deepseek-chat"]


def _strategies_from_env() -> list[str]:
    raw = (os.getenv("MDFLOW_TEST_STRATEGIES") or "").strip()
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    return [
        "role_no_merge",
        "role_merge",
        "role_merge_prompt_text_skip",
        "role_merge_prompt_text_send",
        "role_merge_prompt_text_send_skip_text_question",
        "role_merge_user_facts_only",
        "role_merge_user_facts_only_assistant_last_paragraph",
        "single_message_merge",
        "assistant_only_merge",
    ]


def _temperature_from_env() -> float:
    raw = (os.getenv("MDFLOW_TEST_TEMPERATURE") or "").strip()
    if not raw:
        return 0.0
    return float(raw)


def _initial_variables_from_env() -> dict[str, str | list[str]]:
    raw = (os.getenv("MDFLOW_TEST_INITIAL_VARIABLES") or "").strip()
    if not raw:
        return dict(DEFAULT_INITIAL_VARIABLES)

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid JSON in MDFLOW_TEST_INITIAL_VARIABLES") from exc

    if not isinstance(obj, dict):
        raise RuntimeError("MDFLOW_TEST_INITIAL_VARIABLES must be a JSON object")

    normalized: dict[str, str | list[str]] = {}
    for key, value in obj.items():
        if isinstance(value, list):
            normalized[str(key)] = [str(v) for v in value]
        else:
            normalized[str(key)] = str(value)

    return normalized


def _user_inputs_from_env() -> dict[str, list[str]]:
    raw = (os.getenv("MDFLOW_TEST_USER_INPUTS") or "").strip()
    if not raw:
        return dict(DEFAULT_USER_INPUTS)

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid JSON in MDFLOW_TEST_USER_INPUTS") from exc

    if not isinstance(obj, dict):
        raise RuntimeError("MDFLOW_TEST_USER_INPUTS must be a JSON object")

    normalized: dict[str, list[str]] = {}
    for key, value in obj.items():
        if isinstance(value, list):
            normalized[str(key)] = [str(v) for v in value]
        else:
            normalized[str(key)] = [str(value)]

    return normalized


def _strategy_help() -> dict[str, str]:
    return {
        "role_merge": "包含 user+assistant，连续同角色合并（不把 interaction prompt 放入 context）。",
        "role_no_merge": "包含 user+assistant，不合并（不把 interaction prompt 放入 context）。",
        "assistant_only_merge": "只包含 assistant，连续同角色合并（不包含 user，也不包含 interaction prompt）。",
        "assistant_only_no_merge": "只包含 assistant，不合并（不包含 user，也不包含 interaction prompt）。",
        "role_merge_prompt_text_send": (
            "包含 user+assistant，连续同角色合并；将 interaction prompt 归一化为纯文本，"
            "并作为 assistant message 写入 context。"
        ),
        "role_merge_prompt_text_send_skip_text_question": (
            "同 role_merge_prompt_text_send，但跳过 `?[%{{var}}...question]` 这种“纯文本提问”交互，"
            "不把该 interaction prompt 写入 context。"
        ),
        "role_merge_prompt_text_skip": (
            "包含 user+assistant，连续同角色合并；将 interaction prompt 归一化为纯文本，"
            "但不写入 context。"
        ),
        "role_merge_user_facts_only": (
            "包含 user+assistant，连续同角色合并；仅保留“事实型”的 user 历史（昵称/背景/目的），"
            "丢弃“观点选择”等非事实 user 历史。"
        ),
        "role_merge_user_facts_only_assistant_last_paragraph": (
            "包含 user+assistant，连续同角色合并；仅保留“事实型”的 user 历史（昵称/背景/目的），"
            "并把 assistant 历史裁剪为每条仅保留最后一段（降低风格噪声）。"
        ),
        "single_message_merge": (
            "包含 user+assistant，连续同角色合并；每次调用时把全部历史拼成 1 条 message（带 User:/Assistant: 标签）。"
        ),
        STRATEGY_BLOCK_PROMPT_AS_USER_IGNORE_USER_INPUT: (
            "把每个非交互块的 block.content（提示词/指令）渲染后作为 user message 写入 context；"
            "同时不把学员在 interaction 中的输入写入 context（但仍用于变量更新）。"
        ),
        "v2_like_merge": "role_merge 的别名。",
    }


def _is_text_question_interaction_prompt(raw_content: str) -> bool:
    """Return True for prompts like: ?[%{{var}}...question] (no button/options part)."""
    content = (raw_content or "").strip()
    if not content.startswith("?[%{{"):
        return False
    end = content.find("}}")
    if end == -1:
        return False
    tail = content[end + 2 :].lstrip()
    return tail.startswith("...")


def _normalize_interaction_prompt(
    interaction_variable: str, render_content: str
) -> str:
    var_name = (interaction_variable or "").strip()
    if var_name == "agreeed_points":
        return (
            "以下观点你怎么看？\n"
            "1. AI 是一种工具\n"
            "2. 每种 AI 产品都需要学习使用方法\n"
            "3. 打造 AI 产品是技术高手的事情\n"
            "4. 都不同意"
        )

    text = (render_content or "").strip()
    if "..." in text:
        tail = text.split("...", 1)[1].strip()
        if tail.endswith("]"):
            tail = tail[:-1].rstrip()
        return tail

    if text.startswith("?[%") and text.endswith("]"):
        # Fallback: drop the mdflow wrapper
        inner = text[3:-1].strip()
        if inner.startswith("{{") and "}}" in inner:
            inner = inner.split("}}", 1)[1].strip()
        return inner

    return text


def _assistant_last_paragraph(text: str) -> str:
    content = (text or "").strip()
    if not content:
        return ""
    parts = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    return parts[-1] if parts else content


def _collapse_context_to_single_message(
    messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    cleaned: list[tuple[str, str, str]] = []
    for msg in messages:
        role = (msg.get("role") or "").strip()
        content = (msg.get("content") or "").strip()
        if not role or not content:
            continue
        label = (
            "Assistant" if role == "assistant" else "User" if role == "user" else role
        )
        cleaned.append((role, label, content))

    if not cleaned:
        return []

    lines: list[str] = []
    for _, label, content in cleaned:
        lines.append(f"{label}:")
        lines.append(content)
        lines.append("")

    combined = "\n".join(lines).rstrip()
    if not combined:
        return []

    last_role = cleaned[-1][0] if cleaned else "user"
    if last_role not in {"assistant", "user"}:
        last_role = "user"
    return [{"role": last_role, "content": combined}]


_VAR_PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def _render_placeholders(text: str, variables: dict[str, str | list[str]]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key, "")
        if isinstance(value, list):
            return ", ".join(str(v) for v in value if str(v).strip())
        return str(value)

    return _VAR_PLACEHOLDER_RE.sub(repl, text or "")


class TranscriptEvent(TypedDict):
    role: Literal["assistant", "user"]
    kind: str
    block_index: int
    content: str


class CallEvent(TypedDict):
    seq: int
    block_index: int
    action: str
    context_messages: int
    context_chars: int
    output_chars: int
    output_fp: str
    ctx_overlap: float
    ctx_jaccard: float
    preview: str


_INTERACTION_EVENT_KINDS = {"interaction_prompt", "input", "interaction_validation"}


def _interaction_events(transcript: list[TranscriptEvent]) -> list[TranscriptEvent]:
    return [
        event
        for event in transcript
        if (event.get("kind") or "") in _INTERACTION_EVENT_KINDS
    ]


def _assistant_content_events(
    transcript: list[TranscriptEvent],
) -> list[TranscriptEvent]:
    return [
        event
        for event in transcript
        if event.get("role") == "assistant"
        and event.get("kind") == "content"
        and (event.get("content") or "").strip()
    ]


def _normalize_lines_for_dup_detection(text: str) -> list[str]:
    normalized_lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\\s+", "", line)
        line = re.sub(r"^\\d+[.)]\\s+", "", line)
        line = re.sub(r"\\s+", " ", line).strip().lower()
        if line:
            normalized_lines.append(line)
    return normalized_lines


def _analyze_content_repetition(
    transcript: list[TranscriptEvent],
    *,
    shingle_size: int,
    repeat_threshold: float,
) -> dict[str, object]:
    content_events = _assistant_content_events(transcript)

    rows: list[dict[str, object]] = []
    seen_shingles: set[str] = set()
    seen_lines: set[str] = set()
    prev_shingles: set[str] | None = None
    prev_blocks: list[tuple[int, set[str]]] = []

    for seq, event in enumerate(content_events, start=1):
        block_index = int(event.get("block_index", -1))
        content = str(event.get("content") or "")
        normalized = _normalize_for_similarity(content)
        shingles = _shingle_set(normalized, size=shingle_size) if normalized else set()

        seen_ratio = 0.0
        if seq > 1 and shingles:
            seen_ratio = len(shingles & seen_shingles) / len(shingles)

        prev_jaccard = 0.0
        if seq > 1 and prev_shingles is not None:
            prev_jaccard = _jaccard_similarity(shingles, prev_shingles)

        max_prev_jaccard = 0.0
        max_prev_block_index: int | None = None
        if seq > 1 and prev_blocks:
            best = max(
                (
                    (_jaccard_similarity(shingles, prev_set), prev_idx)
                    for prev_idx, prev_set in prev_blocks
                ),
                key=lambda item: item[0],
                default=(0.0, None),
            )
            max_prev_jaccard, max_prev_block_index = float(best[0]), best[1]

        normalized_lines = _normalize_lines_for_dup_detection(content)
        repeated_lines = 0
        if seq > 1 and normalized_lines:
            repeated_lines = sum(1 for line in normalized_lines if line in seen_lines)
        total_lines = len(normalized_lines)

        rows.append(
            {
                "seq": seq,
                "block_index": block_index,
                "chars": len(content),
                "fp": _short_fingerprint(content),
                "shingles": len(shingles),
                "seen_ratio": seen_ratio,
                "prev_jaccard": prev_jaccard,
                "max_prev_jaccard": max_prev_jaccard,
                "max_prev_block_index": max_prev_block_index,
                "repeated_lines": repeated_lines,
                "total_lines": total_lines,
                "preview": _truncate_note(content, limit=120),
            }
        )

        seen_shingles |= shingles
        prev_shingles = shingles
        prev_blocks.append((block_index, shingles))
        seen_lines.update(normalized_lines)

    eligible = rows[1:] if len(rows) > 1 else []
    total_shingles = sum(int(r.get("shingles") or 0) for r in eligible)
    weighted_avg_seen = (
        sum(
            float(r.get("seen_ratio") or 0.0) * int(r.get("shingles") or 0)
            for r in eligible
        )
        / total_shingles
        if total_shingles
        else 0.0
    )
    weighted_avg_prev = (
        sum(
            float(r.get("prev_jaccard") or 0.0) * int(r.get("shingles") or 0)
            for r in eligible
        )
        / total_shingles
        if total_shingles
        else 0.0
    )
    max_seen = max((float(r.get("seen_ratio") or 0.0) for r in eligible), default=0.0)
    max_prev = max((float(r.get("prev_jaccard") or 0.0) for r in eligible), default=0.0)
    repeat_blocks = sum(
        1 for r in eligible if float(r.get("seen_ratio") or 0.0) >= repeat_threshold
    )

    return {
        "rows": rows,
        "summary": {
            "content_blocks": len(rows),
            "repeat_avg": weighted_avg_seen,
            "repeat_max": max_seen,
            "prev_sim_avg": weighted_avg_prev,
            "prev_sim_max": max_prev,
            "repeat_blocks": repeat_blocks,
            "repeat_threshold": repeat_threshold,
            "shingle_size": shingle_size,
        },
    }


class RunResult(TypedDict):
    model: str
    strategy: str
    status: Literal["ok", "error", "running", "pending"]
    final_output: str
    transcript: list[TranscriptEvent]
    calls: list[CallEvent]
    error: str
    langfuse_session_id: str
    langfuse_trace_id: str


def run_once(
    *,
    model: str,
    strategy: str,
    temperature: float,
    initial_variables: dict[str, str | list[str]],
    user_inputs: dict[str, list[str]],
    provider: MultiOpenAICompatibleProvider,
    max_block_index: int | None,
    langfuse_client: Langfuse | None = None,
    session_id: str = "",
    user_id: str = "",
) -> dict[str, object]:
    mdflow = (
        MarkdownFlow(
            document=TEST_DOCUMENT,
            llm_provider=provider,
            base_system_prompt=BASE_SYSTEM_PROMPT,
            document_prompt=DOCUMENT_PROMPT,
        )
        .set_model(model)
        .set_temperature(temperature)
    )

    blocks = mdflow.get_all_blocks()
    variables: dict[str, str | list[str]] = dict(initial_variables)
    context_cache: list[dict[str, str]] = []
    transcript: list[TranscriptEvent] = []
    calls: list[CallEvent] = []
    call_seq = 0

    include_user = strategy in {
        "role_merge",
        "role_no_merge",
        "role_merge_prompt_text_send",
        "role_merge_prompt_text_skip",
        "role_merge_prompt_text_send_skip_text_question",
        "role_merge_user_facts_only",
        "role_merge_user_facts_only_assistant_last_paragraph",
        "single_message_merge",
        "v2_like_merge",
        STRATEGY_BLOCK_PROMPT_AS_USER_IGNORE_USER_INPUT,
    }
    merge = strategy in {
        "role_merge",
        "role_merge_prompt_text_send",
        "role_merge_prompt_text_skip",
        "role_merge_prompt_text_send_skip_text_question",
        "role_merge_user_facts_only",
        "role_merge_user_facts_only_assistant_last_paragraph",
        "single_message_merge",
        "assistant_only_merge",
        "v2_like_merge",
    }
    normalize_interaction_prompt = strategy in {
        "role_merge_prompt_text_send",
        "role_merge_prompt_text_skip",
        "role_merge_prompt_text_send_skip_text_question",
    }
    include_interaction_render = strategy in {
        "role_merge_prompt_text_send",
        "role_merge_prompt_text_send_skip_text_question",
    }
    user_facts_only = strategy in {
        "role_merge_user_facts_only",
        "role_merge_user_facts_only_assistant_last_paragraph",
    }
    assistant_last_paragraph_only = strategy in {
        "role_merge_user_facts_only_assistant_last_paragraph"
    }
    single_message_mode = strategy in {"single_message_merge"}
    block_prompt_as_user = strategy == STRATEGY_BLOCK_PROMPT_AS_USER_IGNORE_USER_INPUT
    ignore_user_input_in_context = (
        strategy == STRATEGY_BLOCK_PROMPT_AS_USER_IGNORE_USER_INPUT
    )

    def cache_add(*, role: str, content: str) -> None:
        if role == "user" and not include_user:
            return
        if not content.strip():
            return
        if role == "assistant" and assistant_last_paragraph_only:
            content = _assistant_last_paragraph(content)
            if not content.strip():
                return

        if merge and context_cache and context_cache[-1].get("role") == role:
            context_cache[-1]["content"] = (
                context_cache[-1].get("content", "") + "\n" + content
            )
        else:
            context_cache.append({"role": role, "content": content})

    def record_transcript(
        role: Literal["assistant", "user"],
        kind: str,
        block_index: int,
        content: str,
    ) -> None:
        if not content.strip():
            return
        transcript.append(
            {
                "role": role,
                "kind": kind,
                "block_index": block_index,
                "content": content.rstrip(),
            }
        )

    def context_for_call() -> list[dict[str, str]]:
        ctx = list(context_cache)
        return _collapse_context_to_single_message(ctx) if single_message_mode else ctx

    def record_call(
        *,
        block_index: int,
        action: str,
        context: list[dict[str, str]],
        output: str,
    ) -> None:
        nonlocal call_seq
        content = (output or "").strip()
        if not content:
            return

        call_seq += 1
        ctx_text = "\n".join(
            (msg.get("content") or "").strip()
            for msg in context
            if (msg.get("content") or "").strip()
        )
        ctx_norm = _normalize_for_similarity(ctx_text)
        out_norm = _normalize_for_similarity(content)
        ctx_shingles = (
            _shingle_set(ctx_norm, size=REPORT_REPETITION_SHINGLE_SIZE)
            if ctx_norm
            else set()
        )
        out_shingles = (
            _shingle_set(out_norm, size=REPORT_REPETITION_SHINGLE_SIZE)
            if out_norm
            else set()
        )
        if not out_shingles:
            ctx_overlap = 0.0
        else:
            ctx_overlap = len(out_shingles & ctx_shingles) / len(out_shingles)
        ctx_jaccard = _jaccard_similarity(out_shingles, ctx_shingles)

        calls.append(
            {
                "seq": call_seq,
                "block_index": int(block_index),
                "action": str(action),
                "context_messages": len(context),
                "context_chars": len(ctx_text),
                "output_chars": len(content),
                "output_fp": _short_fingerprint(content),
                "ctx_overlap": float(ctx_overlap),
                "ctx_jaccard": float(ctx_jaccard),
                "preview": _truncate_note(content, limit=120),
            }
        )

    def create_process_trace(
        name: str, block_idx: int, action: str, input_data: dict | None = None
    ) -> StatefulTraceClient | None:
        """Create a new trace for each process call (aligned with context_v2)."""
        if not langfuse_client or not session_id:
            return None
        try:
            return langfuse_client.trace(
                name=name,
                user_id=user_id,
                session_id=session_id,
                input=input_data or {},
                metadata={
                    "block_index": block_idx,
                    "action": action,
                    "model": model,
                    "strategy": strategy,
                },
                tags=["mdflow", "process", f"block:{block_idx}", f"action:{action}"],
            )
        except Exception:
            return None

    def end_process_trace(trace: StatefulTraceClient | None, output: str = "") -> None:
        """End a trace and clear the provider's current trace."""
        provider.set_current_trace(None)
        if trace:
            try:
                trace.update(output=output)
            except Exception:
                pass

    for block_index, block in enumerate(blocks):
        if max_block_index is not None and block_index > max_block_index:
            break

        if block_prompt_as_user and block.block_type != BlockType.INTERACTION:
            prompt_text = _render_placeholders(
                getattr(block, "content", "") or "", variables
            ).strip()
            if prompt_text:
                cache_add(role="user", content=prompt_text)
                record_transcript("user", "block_prompt", block_index, prompt_text)

        context = context_for_call()
        if block.block_type == BlockType.INTERACTION:
            # Trace for interaction render
            render_trace = create_process_trace(
                f"process/block_{block_index}/interaction_render",
                block_index,
                "interaction_render",
                {"context_length": len(context)},
            )
            provider.set_current_trace(render_trace)
            provider.set_call_metadata(
                block_index=block_index,
                mdflow_block_type="interaction",
                action="interaction_render",
            )
            render_result = mdflow.process(
                block_index=block_index,
                mode=ProcessMode.COMPLETE,
                context=context,
            )
            render_content = getattr(render_result, "content", "") or ""
            end_process_trace(render_trace, render_content)
            record_call(
                block_index=block_index,
                action="interaction_render",
                context=context,
                output=render_content,
            )

            interaction_variable = (
                block.variables[0] if getattr(block, "variables", None) else ""
            ) or ""
            rendered_prompt = (
                _normalize_interaction_prompt(interaction_variable, render_content)
                if normalize_interaction_prompt
                else render_content
            )
            record_transcript(
                "assistant", "interaction_prompt", block_index, rendered_prompt
            )
            selected_values = user_inputs.get(interaction_variable, [])
            if not selected_values:
                selected_values = ["TEST_INPUT"]

            user_input = (
                {interaction_variable: selected_values} if interaction_variable else {}
            )

            # Trace for interaction input
            input_trace = create_process_trace(
                f"process/block_{block_index}/interaction_input",
                block_index,
                "interaction_input",
                {"user_input": user_input, "context_length": len(context)},
            )
            provider.set_current_trace(input_trace)
            provider.set_call_metadata(
                block_index=block_index,
                mdflow_block_type="interaction",
                action="interaction_input",
                interaction_variable=interaction_variable,
            )
            input_result = mdflow.process(
                block_index=block_index,
                mode=ProcessMode.COMPLETE,
                context=context,
                user_input=user_input,
            )
            validation_content = getattr(input_result, "content", "") or ""
            end_process_trace(input_trace, validation_content)
            record_call(
                block_index=block_index,
                action="interaction_input",
                context=context,
                output=validation_content,
            )

            if getattr(input_result, "variables", None):
                variables.update(input_result.variables or {})

            user_message = (
                ",".join(selected_values)
                if len(selected_values) > 1
                else (selected_values[0] if selected_values else "")
            )
            record_transcript("user", "input", block_index, user_message)
            record_transcript(
                "assistant", "interaction_validation", block_index, validation_content
            )

            if include_interaction_render and not (
                strategy == "role_merge_prompt_text_send_skip_text_question"
                and _is_text_question_interaction_prompt(block.content)
            ):
                cache_add(role="assistant", content=rendered_prompt)
            keep_user_message = True
            if ignore_user_input_in_context:
                keep_user_message = False
            if user_facts_only:
                keep_user_message = interaction_variable in {
                    "sys_user_nickname",
                    "sys_user_background",
                    "purpose",
                }
            if keep_user_message:
                cache_add(role="user", content=user_message)
            continue

        # Treat everything else as content-like (LLMResult.content)
        # Trace for content processing
        content_trace = create_process_trace(
            f"process/block_{block_index}/content",
            block_index,
            "content_complete",
            {"context_length": len(context), "variables": variables},
        )
        provider.set_current_trace(content_trace)
        provider.set_call_metadata(
            block_index=block_index,
            mdflow_block_type=str(block.block_type.value),
            action="content_complete",
        )
        result = mdflow.process(
            block_index=block_index,
            mode=ProcessMode.COMPLETE,
            context=context,
            variables=variables,
        )
        content = getattr(result, "content", "") or ""
        end_process_trace(content_trace, content)
        record_call(
            block_index=block_index,
            action="content_complete",
            context=context,
            output=content,
        )
        record_transcript("assistant", "content", block_index, content)
        cache_add(role="assistant", content=content)

    final_output = ""
    for event in reversed(transcript):
        if (
            event["role"] == "assistant"
            and event["kind"] == "content"
            and event["content"]
        ):
            final_output = str(event["content"] or "")
            break

    return {
        "strategy": strategy,
        "final_output": final_output,
        "transcript": transcript,
        "calls": calls,
    }


def _format_mapping(mapping: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for key in sorted(mapping.keys()):
        value = mapping[key]
        if isinstance(value, list):
            rendered = ", ".join(str(v) for v in value)
        else:
            rendered = str(value)
        lines.append(f"- `{key}`: {rendered}")
    return lines


def _truncate_note(text: str, limit: int = 80) -> str:
    s = (text or "").strip().replace("\n", " ")
    if not s:
        return ""
    s = s if len(s) <= limit else (s[: limit - 1] + "…")
    return s.replace("|", "\\|")


def _normalize_for_similarity(text: str) -> str:
    normalized = (text or "").strip()
    if not normalized:
        return ""

    normalized = re.sub(r"```.*?```", "", normalized, flags=re.DOTALL)
    normalized = normalized.replace("`", "").replace("*", "")
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return normalized


def _short_fingerprint(text: str) -> str:
    normalized = _normalize_for_similarity(text)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]


def _shingle_set(text: str, *, size: int) -> set[str]:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    return {compact[i : i + size] for i in range(len(compact) - size + 1)}


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _text_similarity(a: str, b: str, *, shingle_size: int = 5) -> float:
    left = _normalize_for_similarity(a)
    right = _normalize_for_similarity(b)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return _jaccard_similarity(
        _shingle_set(left, size=shingle_size),
        _shingle_set(right, size=shingle_size),
    )


def _choose_fence(content: str, *, base: str = "```") -> str:
    fence = base
    while fence in (content or ""):
        fence += "`"
    return fence


def _write_fenced_block(
    w: Callable[[str], None], content: str, *, language: str = "text"
) -> None:
    body = (content or "").rstrip("\n")
    fence = _choose_fence(body)
    w(f"{fence}{language}".rstrip())
    if body:
        for line in body.splitlines():
            w(line)
    w(fence)


def _write_report(
    *,
    out_path: Path,
    now: str,
    temperature: float,
    strategies: list[str],
    initial_variables: dict[str, str | list[str]],
    user_inputs: dict[str, list[str]],
    request_config: dict[str, object],
    runs: list[RunResult],
) -> None:
    help_map = _strategy_help()
    shingle_size = REPORT_FINAL_SHINGLE_SIZE
    near_duplicate_threshold = REPORT_NEAR_DUPLICATE_THRESHOLD
    repeat_shingle_size = REPORT_REPETITION_SHINGLE_SIZE
    repeat_threshold = REPORT_REPEAT_THRESHOLD

    with out_path.open("w", encoding="utf-8") as f:

        def w(line: str = "") -> None:
            f.write(line + "\n")

        statuses: dict[str, int] = {"pending": 0, "running": 0, "ok": 0, "error": 0}
        for run in runs:
            statuses[run["status"]] = statuses.get(run["status"], 0) + 1

        models_in_order: list[str] = []
        seen_models: set[str] = set()
        for run in runs:
            if run["model"] in seen_models:
                continue
            models_in_order.append(run["model"])
            seen_models.add(run["model"])

        w("# MarkdownFlow context strategy report")
        w("")
        w(f"- Generated at: `{now}`")
        w(f"- Temperature: `{temperature}`")
        w(
            "- Progress: "
            f"`{statuses.get('ok', 0) + statuses.get('error', 0)}/{len(runs)}` completed "
            f"(`ok`={statuses.get('ok', 0)}, `error`={statuses.get('error', 0)}, "
            f"`running`={statuses.get('running', 0)}, `pending`={statuses.get('pending', 0)})"
        )
        w(f"- Models: {', '.join(f'`{m}`' for m in models_in_order)}")
        w(f"- Strategies: {', '.join(f'`{s}`' for s in strategies)}")
        w(
            f"- Similarity: Jaccard over `{shingle_size}`-char shingles on normalized final output; "
            f"near-duplicate threshold=`{near_duplicate_threshold}`"
        )
        w("")

        w("## Summary (by model)")
        w("")
        for model in models_in_order:
            model_runs = [run for run in runs if run["model"] == model]
            baseline_strategy = strategies[0] if strategies else ""
            baseline_run = next(
                (
                    run
                    for run in model_runs
                    if run["strategy"] == baseline_strategy and run["status"] == "ok"
                ),
                None,
            )
            baseline_output = baseline_run["final_output"] if baseline_run else ""

            w(f"### `{model}`")
            w("")
            w("| strategy | status | chars | fp | sim_to_baseline | preview |")
            w("| --- | --- | ---: | --- | ---: | --- |")
            for strategy in strategies:
                run = next((r for r in model_runs if r["strategy"] == strategy), None)
                if not run:
                    continue

                preview = ""
                char_count = ""
                fingerprint = ""
                sim_to_baseline = ""

                if run["status"] == "ok":
                    output = run["final_output"] or ""
                    preview = _truncate_note(output, limit=160)
                    char_count = str(len(output))
                    fingerprint = _short_fingerprint(output)
                    if baseline_output and output:
                        sim_to_baseline = f"{_text_similarity(baseline_output, output, shingle_size=shingle_size):.3f}"
                elif run["status"] == "error":
                    preview = _truncate_note(run["error"], limit=160)

                w(
                    "| "
                    + " | ".join(
                        [
                            f"`{strategy}`",
                            f"`{run['status']}`",
                            char_count or "—",
                            f"`{fingerprint}`" if fingerprint else "—",
                            sim_to_baseline or "—",
                            preview or "—",
                        ]
                    )
                    + " |"
                )
            w("")

            ok_runs = [
                run
                for run in model_runs
                if run["status"] == "ok" and (run["final_output"] or "").strip()
            ]
            if not ok_runs:
                continue

            fp_groups: dict[str, list[str]] = {}
            for run in ok_runs:
                fp = _short_fingerprint(run["final_output"])
                fp_groups.setdefault(fp or "—", []).append(run["strategy"])

            exact_duplicates = {
                fp: items
                for fp, items in fp_groups.items()
                if fp != "—" and len(items) > 1
            }
            w("**Exact duplicates (same fp)**")
            w("")
            if exact_duplicates:
                for fp, items in sorted(
                    exact_duplicates.items(), key=lambda item: (-len(item[1]), item[0])
                ):
                    w(f"- `{fp}`: {', '.join(f'`{s}`' for s in sorted(items))}")
            else:
                w("- (none)")
            w("")

            shingles_by_strategy: dict[str, set[str]] = {
                run["strategy"]: _shingle_set(
                    _normalize_for_similarity(run["final_output"]), size=shingle_size
                )
                for run in ok_runs
            }
            near_duplicates: list[tuple[float, str, str]] = []
            for left, right in itertools.combinations(
                sorted(shingles_by_strategy.keys()), 2
            ):
                sim = _jaccard_similarity(
                    shingles_by_strategy[left], shingles_by_strategy[right]
                )
                if sim >= near_duplicate_threshold:
                    near_duplicates.append((sim, left, right))

            w(f"**Near duplicates (sim >= {near_duplicate_threshold})**")
            w("")
            if near_duplicates:
                for sim, left, right in sorted(
                    near_duplicates, key=lambda item: item[0], reverse=True
                ):
                    w(f"- `{left}` <-> `{right}`: `{sim:.3f}`")
            else:
                w("- (none)")
            w("")

            w("**Block repetition (assistant content vs previous blocks)**")
            w("")
            w(
                f"- Shingles: `{repeat_shingle_size}` chars; repeat threshold: `{repeat_threshold}` "
                "(repeat_avg/max computed over content blocks after the first)"
            )
            w("")
            w(
                "| strategy | status | content_blocks | repeat_avg | repeat_max | prev_sim_avg | prev_sim_max | repeat_blocks |"
            )
            w("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
            for strategy in strategies:
                run = next((r for r in model_runs if r["strategy"] == strategy), None)
                if not run:
                    continue
                if run["status"] != "ok":
                    w(
                        "| "
                        + " | ".join(
                            [
                                f"`{strategy}`",
                                f"`{run['status']}`",
                                "—",
                                "—",
                                "—",
                                "—",
                                "—",
                                "—",
                            ]
                        )
                        + " |"
                    )
                    continue

                analysis = _analyze_content_repetition(
                    run.get("transcript") or [],
                    shingle_size=repeat_shingle_size,
                    repeat_threshold=repeat_threshold,
                )
                summary = dict(analysis.get("summary") or {})
                w(
                    "| "
                    + " | ".join(
                        [
                            f"`{strategy}`",
                            f"`{run['status']}`",
                            str(summary.get("content_blocks") or 0),
                            f"{float(summary.get('repeat_avg') or 0.0):.3f}",
                            f"{float(summary.get('repeat_max') or 0.0):.3f}",
                            f"{float(summary.get('prev_sim_avg') or 0.0):.3f}",
                            f"{float(summary.get('prev_sim_max') or 0.0):.3f}",
                            str(summary.get("repeat_blocks") or 0),
                        ]
                    )
                    + " |"
                )
            w("")

            w("**Context echo (assistant outputs vs provided context)**")
            w("")
            w(
                f"- Shingles: `{repeat_shingle_size}` chars; echo threshold: `{repeat_threshold}` "
                "(averages weighted by output_chars)"
            )
            w("")
            w(
                "| strategy | status | content_calls | echo_avg | echo_max | echo_calls |"
            )
            w("| --- | --- | ---: | ---: | ---: | ---: |")
            for strategy in strategies:
                run = next((r for r in model_runs if r["strategy"] == strategy), None)
                if not run:
                    continue
                if run["status"] != "ok":
                    w(
                        "| "
                        + " | ".join(
                            [
                                f"`{strategy}`",
                                f"`{run['status']}`",
                                "—",
                                "—",
                                "—",
                                "—",
                            ]
                        )
                        + " |"
                    )
                    continue

                content_calls = [
                    c
                    for c in (run.get("calls") or [])
                    if (c.get("action") or "") == "content_complete"
                ]
                total_chars = sum(
                    int(c.get("output_chars") or 0) for c in content_calls
                )
                echo_avg = (
                    sum(
                        float(c.get("ctx_overlap") or 0.0)
                        * int(c.get("output_chars") or 0)
                        for c in content_calls
                    )
                    / total_chars
                    if total_chars
                    else 0.0
                )
                echo_max = max(
                    (float(c.get("ctx_overlap") or 0.0) for c in content_calls),
                    default=0.0,
                )
                echo_calls = sum(
                    1
                    for c in content_calls
                    if float(c.get("ctx_overlap") or 0.0) >= repeat_threshold
                )
                w(
                    "| "
                    + " | ".join(
                        [
                            f"`{strategy}`",
                            f"`{run['status']}`",
                            str(len(content_calls)),
                            f"{echo_avg:.3f}",
                            f"{echo_max:.3f}",
                            str(echo_calls),
                        ]
                    )
                    + " |"
                )
            w("")

        w("## Final outputs")
        w("")
        for run in runs:
            model = run["model"]
            strategy = run["strategy"]
            status = run["status"]
            char_count = len(run["final_output"] or "") if status == "ok" else 0
            fp = _short_fingerprint(run["final_output"]) if status == "ok" else ""

            summary_parts = [model, strategy, status]
            if status == "ok":
                summary_parts.append(f"{char_count} chars")
                if fp:
                    summary_parts.append(f"fp={fp}")

            w("<details>")
            w(f"<summary>{' / '.join(summary_parts)}</summary>")
            w("")
            if status == "ok":
                content_analysis = _analyze_content_repetition(
                    run.get("transcript") or [],
                    shingle_size=repeat_shingle_size,
                    repeat_threshold=repeat_threshold,
                )
                summary = dict(content_analysis.get("summary") or {})
                rows = list(content_analysis.get("rows") or [])

                w("**Content blocks repetition**")
                w("")
                w(
                    f"- content_blocks: `{int(summary.get('content_blocks') or 0)}`; "
                    f"repeat_avg: `{float(summary.get('repeat_avg') or 0.0):.3f}`; "
                    f"repeat_max: `{float(summary.get('repeat_max') or 0.0):.3f}`; "
                    f"prev_sim_avg: `{float(summary.get('prev_sim_avg') or 0.0):.3f}`; "
                    f"prev_sim_max: `{float(summary.get('prev_sim_max') or 0.0):.3f}`; "
                    f"repeat_blocks(>= {repeat_threshold}): `{int(summary.get('repeat_blocks') or 0)}`"
                )
                w("")
                if rows:
                    w(
                        "| seq | block | chars | fp | seen_ratio | prev_sim | max_prev_sim@block | repeated_lines | preview |"
                    )
                    w("| ---: | ---: | ---: | --- | ---: | ---: | --- | ---: | --- |")
                    for row in rows:
                        max_ref = ""
                        if row.get("max_prev_block_index") is not None:
                            max_ref = (
                                f"{float(row.get('max_prev_jaccard') or 0.0):.3f}"
                                f"@{int(row.get('max_prev_block_index') or 0)}"
                            )
                        repeated_lines = int(row.get("repeated_lines") or 0)
                        total_lines = int(row.get("total_lines") or 0)
                        repeated_label = (
                            f"{repeated_lines}/{total_lines}" if total_lines else "0/0"
                        )

                        w(
                            "| "
                            + " | ".join(
                                [
                                    str(int(row.get("seq") or 0)),
                                    str(int(row.get("block_index") or 0)),
                                    str(int(row.get("chars") or 0)),
                                    f"`{row.get('fp') or ''}`"
                                    if row.get("fp")
                                    else "—",
                                    f"{float(row.get('seen_ratio') or 0.0):.3f}",
                                    f"{float(row.get('prev_jaccard') or 0.0):.3f}",
                                    f"`{max_ref}`" if max_ref else "—",
                                    repeated_label,
                                    row.get("preview") or "—",
                                ]
                            )
                            + " |"
                        )
                    w("")
                else:
                    w("_No assistant content blocks recorded._")
                    w("")

                w("**Context echo (content_complete)**")
                w("")
                content_calls = [
                    c
                    for c in (run.get("calls") or [])
                    if (c.get("action") or "") == "content_complete"
                ]
                if not content_calls:
                    w("_No content calls recorded._")
                else:
                    w(
                        "| seq | block | ctx_msgs | ctx_chars | out_chars | ctx_overlap | ctx_jaccard | fp | preview |"
                    )
                    w("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |")
                    for c in content_calls:
                        w(
                            "| "
                            + " | ".join(
                                [
                                    str(int(c.get("seq") or 0)),
                                    str(int(c.get("block_index") or 0)),
                                    str(int(c.get("context_messages") or 0)),
                                    str(int(c.get("context_chars") or 0)),
                                    str(int(c.get("output_chars") or 0)),
                                    f"{float(c.get('ctx_overlap') or 0.0):.3f}",
                                    f"{float(c.get('ctx_jaccard') or 0.0):.3f}",
                                    f"`{c.get('output_fp') or ''}`"
                                    if c.get("output_fp")
                                    else "—",
                                    c.get("preview") or "—",
                                ]
                            )
                            + " |"
                        )
                w("")

                w("**Final output (last assistant content)**")
                w("")
                _write_fenced_block(
                    w, run["final_output"].rstrip(), language="markdown"
                )
                w("")
                w("**Interactions (all rounds)**")
                w("")
                interaction_events = _interaction_events(run.get("transcript") or [])
                if not interaction_events:
                    w("_No interactions recorded._")
                else:
                    for idx, event in enumerate(interaction_events, start=1):
                        label = f"{event['role']} ({event['kind']}, block {event['block_index']})"
                        w(f"{idx}. {label}")
                        w("")
                        _write_fenced_block(
                            w, event["content"].rstrip(), language="text"
                        )
                        w("")
            elif status == "error":
                _write_fenced_block(w, run["error"].rstrip(), language="text")
            else:
                w("_No output yet._")
            w("")
            w("</details>")
            w("")

        w("## Transcripts")
        w("")
        for run in runs:
            model = run["model"]
            strategy = run["strategy"]
            status = run["status"]

            w("<details>")
            w(f"<summary>{model} / {strategy} / {status}</summary>")
            w("")
            w(f"- status: `{status}`")
            if run.get("langfuse_session_id"):
                w(f"- langfuse_session_id: `{run['langfuse_session_id']}`")
            if run.get("langfuse_trace_id"):
                w(f"- langfuse_trace_id: `{run['langfuse_trace_id']}`")

            if status == "error":
                w("")
                _write_fenced_block(w, run["error"].rstrip(), language="text")
                w("")
                w("</details>")
                w("")
                continue

            if status != "ok":
                w("")
                w("_No transcript yet._")
                w("")
                w("</details>")
                w("")
                continue

            w("")
            for idx, event in enumerate(run["transcript"], start=1):
                label = (
                    f"{event['role']} ({event['kind']}, block {event['block_index']})"
                )
                w(f"{idx}. {label}")
                w("")
                _write_fenced_block(w, event["content"].rstrip(), language="text")
                w("")
            w("</details>")
            w("")

        w("## Reference")
        w("")

        w("<details>")
        w("<summary>Strategies</summary>")
        w("")
        for strategy in strategies:
            desc = help_map.get(strategy, "")
            w(f"- `{strategy}`: {desc}".rstrip())
        w("")
        w("</details>")
        w("")

        w("<details>")
        w("<summary>Fixed inputs</summary>")
        w("")
        w("**initial_variables**")
        w("")
        for line in _format_mapping(initial_variables):
            w(line)
        w("")
        w("**user_inputs**")
        w("")
        for line in _format_mapping(user_inputs):
            w(line)
        w("")
        w("**request_config**")
        w("")
        for line in _format_mapping(request_config):
            w(line)
        w("")
        w("</details>")
        w("")

        w("<details>")
        w("<summary>Fixed prompts</summary>")
        w("")
        _write_fenced_block(w, BASE_SYSTEM_PROMPT.strip(), language="text")
        w("")
        _write_fenced_block(w, DOCUMENT_PROMPT.strip(), language="text")
        w("")
        w("</details>")
        w("")

        w("<details>")
        w("<summary>Fixed MarkdownFlow document</summary>")
        w("")
        _write_fenced_block(w, TEST_DOCUMENT.rstrip(), language="text")
        w("")
        w("</details>")
        w("")


def main() -> None:
    _load_env()

    models = _models_from_env()
    strategies = _strategies_from_env()
    temperature = _temperature_from_env()
    initial_variables = _initial_variables_from_env()
    user_inputs = _user_inputs_from_env()
    max_block_index_raw = (os.getenv("MDFLOW_TEST_MAX_BLOCK_INDEX") or "").strip()
    max_block_index = int(max_block_index_raw) if max_block_index_raw else None

    request_timeout = float(os.getenv("MDFLOW_TEST_REQUEST_TIMEOUT") or "120")
    max_retries = int(os.getenv("MDFLOW_TEST_MAX_RETRIES") or "0")
    openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    openai_base_url_gpt_5 = (
        os.getenv("MDFLOW_TEST_OPENAI_BASE_URL") or "https://api.openai.com/v1"
    ).strip()
    deepseek_base_url = os.getenv(
        "DEEPSEEK_API_URL", "https://api.deepseek.com"
    ).strip()

    provider = MultiOpenAICompatibleProvider()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    out_path_raw = (os.getenv("MDFLOW_TEST_OUT_PATH") or "").strip()
    if out_path_raw:
        out_path = Path(out_path_raw)
        if not out_path.is_absolute():
            out_path = Path(__file__).resolve().parents[1] / out_path_raw
    else:
        out_path = Path(__file__).resolve().parents[1] / "result.md"
    langfuse_client = _init_langfuse_client()
    langfuse_user_id = (
        os.getenv("MDFLOW_TEST_LANGFUSE_USER_ID") or "mdflow-test"
    ).strip()
    langfuse_session_prefix = (
        os.getenv("MDFLOW_TEST_LANGFUSE_SESSION_ID") or f"mdflow-test-{now}"
    ).strip()
    langfuse_host = _strip_quotes(os.getenv("LANGFUSE_HOST", ""))
    langfuse_flush_each_run = _bool_env("MDFLOW_TEST_LANGFUSE_FLUSH_EACH_RUN", True)
    request_config = {
        "request_timeout_seconds": request_timeout,
        "max_retries": max_retries,
        "openai_base_url": openai_base_url,
        "openai_base_url_gpt_5": openai_base_url_gpt_5,
        "deepseek_base_url": deepseek_base_url,
        "max_block_index": max_block_index if max_block_index is not None else "all",
        "langfuse_enabled": bool(langfuse_client),
        "langfuse_host": langfuse_host or "",
        "langfuse_session_mode": "per_model_strategy_with_trace_per_process",
        "langfuse_session_prefix": langfuse_session_prefix,
    }

    runs: list[RunResult] = [
        {
            "model": model,
            "strategy": strategy,
            "status": "pending",
            "final_output": "",
            "transcript": [],
            "calls": [],
            "error": "",
            "langfuse_session_id": "",
            "langfuse_trace_id": "",
        }
        for model in models
        for strategy in strategies
    ]

    _write_report(
        out_path=out_path,
        now=now,
        temperature=temperature,
        strategies=strategies,
        initial_variables=initial_variables,
        user_inputs=user_inputs,
        request_config=request_config,
        runs=runs,
    )

    for run in runs:
        model = run["model"]
        strategy = run["strategy"]
        run["status"] = "running"
        provider.clear_trace()

        # Session per model+strategy, each process call creates its own trace (aligned with context_v2)
        run_session_id = f"{langfuse_session_prefix}/{model}/{strategy}"
        run["langfuse_session_id"] = run_session_id

        # Set run metadata for the provider (will be included in each generation)
        provider.set_run_metadata(
            model=model,
            strategy=strategy,
            temperature=temperature,
            max_block_index=max_block_index if max_block_index is not None else "all",
            langfuse_session_id=run_session_id,
        )

        _write_report(
            out_path=out_path,
            now=now,
            temperature=temperature,
            strategies=strategies,
            initial_variables=initial_variables,
            user_inputs=user_inputs,
            request_config=request_config,
            runs=runs,
        )
        print(f"Running: model={model} strategy={strategy}", flush=True)
        try:
            payload = run_once(
                model=model,
                strategy=strategy,
                temperature=temperature,
                initial_variables=initial_variables,
                user_inputs=user_inputs,
                provider=provider,
                max_block_index=max_block_index,
                langfuse_client=langfuse_client,
                session_id=run_session_id,
                user_id=langfuse_user_id,
            )
            run["status"] = "ok"
            run["final_output"] = str(payload["final_output"] or "")
            run["transcript"] = list(payload["transcript"] or [])
            run["calls"] = list(payload["calls"] or [])
            run["error"] = ""
        except Exception as exc:
            run["status"] = "error"
            run["final_output"] = ""
            run["transcript"] = []
            run["calls"] = []
            run["error"] = str(exc)
        finally:
            provider.clear_trace()
            if langfuse_client and langfuse_flush_each_run:
                try:
                    langfuse_client.flush()
                except Exception:
                    pass

        _write_report(
            out_path=out_path,
            now=now,
            temperature=temperature,
            strategies=strategies,
            initial_variables=initial_variables,
            user_inputs=user_inputs,
            request_config=request_config,
            runs=runs,
        )

    print(f"Wrote: {out_path}")
    if langfuse_client and not langfuse_flush_each_run:
        try:
            langfuse_client.flush()
        except Exception:
            pass


if __name__ == "__main__":
    main()
