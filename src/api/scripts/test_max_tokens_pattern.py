#!/usr/bin/env python3
"""
Test script for MAX_TOKENS_PATTERN_RULES inference mechanism.

This script tests the pattern matching logic independently without Flask dependencies.

Usage:
    cd src/api
    python scripts/test_max_tokens_pattern.py
"""

import re
from typing import List, Tuple, Optional

# Copy the MAX_TOKENS_PATTERN_RULES from llm/__init__.py
# This ensures we test the exact same rules
MAX_TOKENS_PATTERN_RULES: List[Tuple[re.Pattern, int]] = [
    # -------------------------------------------------------------------------
    # DeepSeek - max_tokens: 8192 (default 4096)
    # Doc: https://api-docs.deepseek.com/api/create-chat-completion
    # -------------------------------------------------------------------------
    (re.compile(r"deepseek", re.IGNORECASE), 8192),
    # -------------------------------------------------------------------------
    # ERNIE (Baidu) - max_output_tokens varies by model
    # Doc: https://cloud.baidu.com/doc/WENXINWORKSHOP/s/Nlks5zkzu
    # ERNIE-*-128K: 4096 (larger context, but same output limit)
    # ERNIE-*-8K: 4096 (most models support up to 4096 output)
    # -------------------------------------------------------------------------
    (re.compile(r"ernie.*128k", re.IGNORECASE), 4096),
    (re.compile(r"ernie", re.IGNORECASE), 4096),
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
    # Doubao-*-thinking: max 16384 (extended for reasoning)
    # -------------------------------------------------------------------------
    (re.compile(r"doubao.*thinking", re.IGNORECASE), 16384),
    (re.compile(r"doubao", re.IGNORECASE), 4096),
    # -------------------------------------------------------------------------
    # Kimi/Moonshot - max_tokens: 4096 / 8192
    # Doc: https://platform.moonshot.cn/docs/api/chat
    # kimi-k2: newer model with larger output capacity
    # -------------------------------------------------------------------------
    (re.compile(r"kimi-k2", re.IGNORECASE), 8192),
    (re.compile(r"kimi|moonshot", re.IGNORECASE), 4096),
]


def _infer_max_tokens_by_pattern(model: str) -> Optional[int]:
    """Infer max_tokens using pattern rules. Returns None if no match."""
    normalized = model.strip().lower()
    # Strip provider prefixes (e.g., "ark/deepseek-v3" -> "deepseek-v3")
    while "/" in normalized:
        _, normalized = normalized.split("/", 1)

    for pattern, max_tokens in MAX_TOKENS_PATTERN_RULES:
        if pattern.search(normalized):
            return max_tokens
    return None


def test_pattern_rules():
    """Test the pattern matching rules directly."""
    print("=" * 70)
    print("Testing MAX_TOKENS_PATTERN_RULES")
    print("=" * 70)

    test_cases = [
        # DeepSeek models
        ("deepseek-v3-2", 8192, "DeepSeek V3.2"),
        ("deepseek-chat", 8192, "DeepSeek Chat"),
        ("deepseek-r1", 8192, "DeepSeek R1"),
        ("deepseek-reasoner", 8192, "DeepSeek Reasoner"),
        ("ark/deepseek-v3-1", 8192, "ARK DeepSeek V3.1"),
        ("deepseek-ai/deepseek-r1", 8192, "DeepSeek AI R1"),
        # ERNIE models
        ("ernie-4.0-8k", 4096, "ERNIE 4.0 8K"),
        ("ernie-4.0-128k", 4096, "ERNIE 4.0 128K"),
        ("ernie-3.5-turbo", 4096, "ERNIE 3.5 Turbo"),
        # Qwen models
        ("qwen-max", 8192, "Qwen Max"),
        ("qwen-plus", 8192, "Qwen Plus"),
        ("qwen-turbo", 8192, "Qwen Turbo"),
        ("qwq-32b-preview", 8192, "QwQ 32B"),
        ("qvq-72b-preview", 8192, "QVQ 72B"),
        # GLM models
        ("glm-4", 4096, "GLM-4"),
        ("glm-4-flash", 4096, "GLM-4 Flash"),
        ("glm-4-air", 4096, "GLM-4 Air"),
        ("glm-4-thinking", 4096, "GLM-4 Thinking"),
        ("glm-4-rumination", 4096, "GLM-4 Rumination"),
        # Doubao models
        ("doubao-seed-1-6", 4096, "Doubao Seed 1.6"),
        ("doubao-seed-1-6-flash", 4096, "Doubao Flash"),
        ("doubao-seed-1-6-thinking", 16384, "Doubao Thinking"),
        # Kimi models
        ("kimi-k2", 8192, "Kimi K2"),
        ("kimi-k2-thinking", 8192, "Kimi K2 Thinking"),
        ("moonshot-v1-8k", 4096, "Moonshot V1 8K"),
        ("moonshot-v1-32k", 4096, "Moonshot V1 32K"),
        # Unknown models (should return None)
        ("unknown-model", None, "Unknown Model"),
        ("gpt-4o", None, "GPT-4o (not in our rules)"),
        ("claude-3-opus", None, "Claude 3 Opus (not in our rules)"),
    ]

    passed = 0
    failed = 0

    for model, expected, description in test_cases:
        result = _infer_max_tokens_by_pattern(model)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
            print(f"{status} {description:30} | {model:35} => {result}")
        else:
            failed += 1
            print(
                f"{status} {description:30} | {model:35} => {result} (expected {expected})"
            )

    print("-" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


def test_provider_prefix_stripping():
    """Test that provider prefixes are correctly stripped."""
    print("\n" + "=" * 70)
    print("Testing Provider Prefix Stripping")
    print("=" * 70)

    test_cases = [
        ("ark/deepseek-v3-2", 8192, "ARK prefix"),
        ("deepseek-ai/deepseek-r1", 8192, "DeepSeek AI prefix"),
        ("silicon/deepseek-chat", 8192, "Silicon prefix"),
        ("qwen/qwen-max", 8192, "Qwen prefix"),
        ("ernie/ernie-4.0-8k", 4096, "ERNIE prefix"),
        ("openai/gpt-4", None, "OpenAI prefix (no match)"),
        ("volcengine/doubao-seed-1-6", 4096, "Volcengine prefix"),
        # Nested prefixes
        ("provider/sub/deepseek-chat", 8192, "Nested prefix"),
    ]

    passed = 0
    failed = 0

    for model, expected, description in test_cases:
        result = _infer_max_tokens_by_pattern(model)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(
            f"{status} {description:25} | {model:40} => {result} (expected {expected})"
        )

    print("-" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


def test_case_insensitivity():
    """Test that pattern matching is case-insensitive."""
    print("\n" + "=" * 70)
    print("Testing Case Insensitivity")
    print("=" * 70)

    test_cases = [
        ("DeepSeek-V3-2", 8192),
        ("DEEPSEEK-CHAT", 8192),
        ("Qwen-Max", 8192),
        ("QWEN-PLUS", 8192),
        ("GLM-4", 4096),
        ("Glm-4-Flash", 4096),
        ("ERNIE-4.0-8K", 4096),
        ("Doubao-Seed-1-6-THINKING", 16384),
    ]

    passed = 0
    failed = 0

    for model, expected in test_cases:
        result = _infer_max_tokens_by_pattern(model)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status} {model:35} => {result} (expected {expected})")

    print("-" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


def test_pattern_priority():
    """Test that more specific patterns match before general ones."""
    print("\n" + "=" * 70)
    print("Testing Pattern Priority (specific before general)")
    print("=" * 70)

    test_cases = [
        # ERNIE: 128k should match first (4096), then general ERNIE (4096)
        ("ernie-4.0-128k", 4096, "ERNIE 128K specific rule"),
        ("ernie-4.0-8k", 4096, "ERNIE general rule"),
        # GLM: thinking should match first (4096), then general GLM (4096)
        ("glm-4-thinking", 4096, "GLM thinking specific rule"),
        ("glm-4", 4096, "GLM general rule"),
        # Doubao: thinking should match first (16384), then general Doubao (4096)
        ("doubao-seed-1-6-thinking", 16384, "Doubao thinking specific rule"),
        ("doubao-seed-1-6", 4096, "Doubao general rule"),
        # Kimi: k2 should match first (8192), then general Kimi (4096)
        ("kimi-k2", 8192, "Kimi K2 specific rule"),
        ("kimi-1.5", 4096, "Kimi general rule"),
    ]

    passed = 0
    failed = 0

    for model, expected, description in test_cases:
        result = _infer_max_tokens_by_pattern(model)
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(
            f"{status} {description:35} | {model:30} => {result} (expected {expected})"
        )

    print("-" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


def show_all_pattern_rules():
    """Display all configured pattern rules."""
    print("\n" + "=" * 70)
    print("Configured MAX_TOKENS_PATTERN_RULES")
    print("=" * 70)

    for i, (pattern, max_tokens) in enumerate(MAX_TOKENS_PATTERN_RULES, 1):
        print(f"{i:2}. Pattern: {pattern.pattern:40} => max_tokens: {max_tokens}")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("MAX_TOKENS_PATTERN_RULES Test Suite")
    print("=" * 70 + "\n")

    # Show configuration
    show_all_pattern_rules()

    # Run tests
    results = []
    results.append(("Pattern Rules", test_pattern_rules()))
    results.append(("Provider Prefix Stripping", test_provider_prefix_stripping()))
    results.append(("Case Insensitivity", test_case_insensitivity()))
    results.append(("Pattern Priority", test_pattern_priority()))

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    all_passed = True
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status}: {name}")
        if not passed:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1


if __name__ == "__main__":
    exit(main())
