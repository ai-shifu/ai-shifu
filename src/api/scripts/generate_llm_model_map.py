#!/usr/bin/env python3
"""
Generate a local, version-controlled model map for token limit resolution.

This script is intended to be run manually after configuring provider API keys.
It discovers available models from OpenAI-compatible providers (GET /models) and
ARK endpoints (ListEndpoints), then compares them against LiteLLM's registry.

Outputs a JSON file with 2 sections:
  - aliases: map non-canonical ids to canonical ids
  - max_tokens: map canonical ids to max_tokens

Note:
  Providers often do NOT expose max token limits via list-model APIs. For any
  model that LiteLLM cannot resolve, this script will record it as "missing"
  and (optionally) add a placeholder entry if --write-placeholders is enabled.

Usage:
  cd src/api
  conda activate py311 && source .venv/bin/activate
  python scripts/generate_llm_model_map.py --write-placeholders
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote

import requests

# Add parent directory to path for importing shared model rules
sys.path.insert(0, str(Path(__file__).parent.parent))
from flaskr.common.llm_model_rules import (
    LITELLM_CANONICAL_RULES,
    infer_max_tokens_by_pattern,
)


@dataclass(frozen=True)
class Provider:
    key: str
    prefix: str
    api_key_env: str
    base_url_env: Optional[str] = None
    default_base_url: Optional[str] = None


PROVIDERS: List[Provider] = [
    Provider(
        key="openai",
        prefix="",
        api_key_env="OPENAI_API_KEY",
        base_url_env="OPENAI_BASE_URL",
        default_base_url="https://api.openai.com/v1",
    ),
    Provider(
        key="qwen",
        prefix="qwen/",
        api_key_env="QWEN_API_KEY",
        base_url_env="QWEN_API_URL",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    Provider(
        key="silicon",
        prefix="silicon/",
        api_key_env="SILICON_API_KEY",
        base_url_env="SILICON_API_URL",
        default_base_url="https://api.siliconflow.cn/v1",
    ),
    Provider(
        key="deepseek",
        prefix="",
        api_key_env="DEEPSEEK_API_KEY",
        base_url_env="DEEPSEEK_API_URL",
        default_base_url="https://api.deepseek.com",
    ),
    Provider(
        key="ernie_v2",
        prefix="ernie/",
        api_key_env="ERNIE_API_KEY",
        base_url_env=None,
        default_base_url="https://qianfan.baidubce.com/v2",
    ),
    Provider(
        key="glm",
        prefix="glm/",
        api_key_env="BIGMODEL_API_KEY",
        base_url_env=None,
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
    ),
    Provider(
        key="gemini",
        prefix="",
        api_key_env="GEMINI_API_KEY",
        base_url_env="GEMINI_API_URL",
        default_base_url=None,  # special handling
    ),
]


# ---------------------------------------------------------------------------
# ARK signing (copied from flaskr/api/ark/sign.py to avoid import dependencies)
# ---------------------------------------------------------------------------
ARK_SERVICE = "ark"
ARK_VERSION = "2024-01-01"
ARK_REGION = "cn-beijing"
ARK_HOST = "open.volcengineapi.com"
ARK_CONTENT_TYPE = "application/json"


def _ark_norm_query(params: Dict[str, Any]) -> str:
    query = ""
    for key in sorted(params.keys()):
        if isinstance(params[key], list):
            for k in params[key]:
                query = (
                    query + quote(key, safe="-_.~") + "=" + quote(k, safe="-_.~") + "&"
                )
        else:
            query = (
                query
                + quote(key, safe="-_.~")
                + "="
                + quote(str(params[key]), safe="-_.~")
                + "&"
            )
    query = query[:-1]
    return query.replace("+", "%20")


def _ark_hmac_sha256(key: bytes, content: str) -> bytes:
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()


def _ark_hash_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _ark_request(
    method: str,
    date: datetime,
    query: Dict,
    header: Dict,
    ak: str,
    sk: str,
    action: str,
    body: Optional[str],
) -> Dict:
    credential = {
        "access_key_id": ak,
        "secret_access_key": sk,
        "service": ARK_SERVICE,
        "region": ARK_REGION,
    }
    request_param = {
        "body": body or "",
        "host": ARK_HOST,
        "path": "/",
        "method": method,
        "content_type": ARK_CONTENT_TYPE,
        "date": date,
        "query": {"Action": action, "Version": ARK_VERSION, **query},
    }
    x_date = request_param["date"].strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]
    x_content_sha256 = _ark_hash_sha256(request_param["body"])
    sign_result = {
        "Host": request_param["host"],
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
        "Content-Type": request_param["content_type"],
    }
    signed_headers_str = ";".join(
        ["content-type", "host", "x-content-sha256", "x-date"]
    )
    canonical_request_str = "\n".join(
        [
            request_param["method"].upper(),
            request_param["path"],
            _ark_norm_query(request_param["query"]),
            "\n".join(
                [
                    "content-type:" + request_param["content_type"],
                    "host:" + request_param["host"],
                    "x-content-sha256:" + x_content_sha256,
                    "x-date:" + x_date,
                ]
            ),
            "",
            signed_headers_str,
            x_content_sha256,
        ]
    )
    hashed_canonical_request = _ark_hash_sha256(canonical_request_str)
    credential_scope = "/".join(
        [short_x_date, credential["region"], credential["service"], "request"]
    )
    string_to_sign = "\n".join(
        ["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request]
    )
    k_date = _ark_hmac_sha256(
        credential["secret_access_key"].encode("utf-8"), short_x_date
    )
    k_region = _ark_hmac_sha256(k_date, credential["region"])
    k_service = _ark_hmac_sha256(k_region, credential["service"])
    k_signing = _ark_hmac_sha256(k_service, "request")
    signature = _ark_hmac_sha256(k_signing, string_to_sign).hex()
    sign_result["Authorization"] = (
        "HMAC-SHA256 Credential={}, SignedHeaders={}, Signature={}".format(
            credential["access_key_id"] + "/" + credential_scope,
            signed_headers_str,
            signature,
        )
    )
    header = {**header, **sign_result}
    r = requests.request(
        method=method,
        url="https://{}{}".format(request_param["host"], request_param["path"]),
        headers=header,
        params=request_param["query"],
        data=request_param["body"],
        timeout=30,
    )
    return r.json()


def _fetch_ark_endpoints(ak: str, sk: str) -> List[Tuple[str, str]]:
    """
    Returns list of (foundation_model_name, endpoint_id).
    """
    try:
        resp = _ark_request(
            "POST", datetime.now(), {}, {}, ak, sk, "ListEndpoints", None
        )
        items = resp.get("Result", {}).get("Items", [])
        results: List[Tuple[str, str]] = []
        for item in items:
            endpoint_id = item.get("Id", "")
            model_name = (
                item.get("ModelReference", {})
                .get("FoundationModel", {})
                .get("Name", "")
            )
            if endpoint_id and model_name:
                results.append((model_name, endpoint_id))
        return results
    except Exception as exc:
        print(f"[warn] ark: failed to list endpoints: {exc}")
        return []


# ---------------------------------------------------------------------------
# Gemini model listing (uses v1beta/models API)
# ---------------------------------------------------------------------------
def _fetch_gemini_models(api_key: str, base_url: Optional[str]) -> List[str]:
    google_base = base_url or "https://generativelanguage.googleapis.com"
    url = f"{google_base.rstrip('/')}/v1beta/models?key={api_key}"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        models: List[str] = []
        for item in data.get("models", []):
            name = item.get("name", "") or ""
            if name.startswith("models/"):
                name = name.split("/", 1)[1]
            methods = item.get("supportedGenerationMethods", []) or []
            if methods and "generateContent" not in methods:
                continue
            if name:
                models.append(name)
        return models
    except Exception as exc:
        print(f"[warn] gemini: failed to list models: {exc}")
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _read_env(key: str) -> str:
    return (os.environ.get(key) or "").strip()


def _build_models_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/models"


def _fetch_openai_compatible_models(api_key: str, base_url: str) -> List[str]:
    if not api_key:
        return []
    url = _build_models_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return [item.get("id", "") for item in data.get("data", []) if item.get("id")]


def _canonicalize(model: str) -> str:
    """Normalize model id: lowercase, strip prefix, replace . with -"""
    model = (model or "").strip().lower()
    model = re.sub(r"[._]", "-", model)
    model = re.sub(r"-+", "-", model)
    while "/" in model:
        _, model = model.split("/", 1)
    return model.strip("-")


def _get_litellm_canonical(model: str) -> Optional[str]:
    """Get LiteLLM-recognized key using LITELLM_CANONICAL_RULES."""
    normalized = _canonicalize(model)
    for pattern, litellm_key in LITELLM_CANONICAL_RULES:
        if pattern.search(normalized):
            return litellm_key
    return None


def _load_existing(path: Path) -> Dict:
    if not path.exists():
        return {"aliases": {}, "max_tokens": {}}
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return {"aliases": {}, "max_tokens": {}}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("model map must be a JSON object")
    data.setdefault("aliases", {})
    data.setdefault("max_tokens", {})
    if not isinstance(data["aliases"], dict) or not isinstance(
        data["max_tokens"], dict
    ):
        raise ValueError("model map must contain object fields: aliases, max_tokens")
    return data


def _resolve_max_tokens(model: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Resolve max_tokens. Priority: 1) LiteLLM  2) Pattern rules
    Returns (max_tokens, source) or (None, None) if not found.
    """
    canonical = _canonicalize(model)

    # 1) Try LiteLLM with canonical key
    litellm_key = _get_litellm_canonical(canonical)
    try:
        from litellm import get_max_tokens

        for key in [litellm_key, canonical] if litellm_key else [canonical]:
            if key:
                try:
                    return int(get_max_tokens(key)), f"litellm:{key}"
                except Exception:
                    pass
    except Exception:
        pass

    # 2) Pattern-based inference (shared rules)
    mt = infer_max_tokens_by_pattern(canonical)
    if mt is not None:
        return mt, f"pattern:{canonical}"

    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate model-map.json for LLM token limit resolution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan all configured providers and show what's missing
  python scripts/generate_llm_model_map.py

  # Write placeholder entries for missing models
  python scripts/generate_llm_model_map.py --write-placeholders

  # Only scan specific providers
  python scripts/generate_llm_model_map.py --providers openai,qwen,ark
""",
    )
    parser.add_argument(
        "--output",
        default="src/api/flaskr/api/llm/model-map.json",
        help="Output JSON path (relative to repo root)",
    )
    parser.add_argument(
        "--providers",
        default="openai,qwen,silicon,deepseek,ernie_v2,glm,gemini,ark",
        help="Comma-separated provider keys to scan (use 'ark' to include ARK endpoints)",
    )
    parser.add_argument(
        "--write-placeholders",
        action="store_true",
        help="Write placeholder max_tokens=0 entries for models missing in LiteLLM",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed matching info",
    )
    args = parser.parse_args()

    # Script is at src/api/scripts/, so parents[2] is src/, parents[3] is repo root
    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[3]  # ai-shifu/
    output_path = (repo_root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    enabled: Set[str] = {
        p.strip().lower() for p in str(args.providers).split(",") if p.strip()
    }
    providers = [p for p in PROVIDERS if p.key in enabled]

    data = _load_existing(output_path)
    aliases: Dict[str, str] = dict(data.get("aliases", {}))
    max_tokens: Dict[str, int] = {
        k: int(v) for k, v in data.get("max_tokens", {}).items()
    }

    # Clean up user-specific ARK endpoint aliases (ep-xxx) from model-map.json
    # These should be resolved at runtime by llm/__init__.py via _load_ark_models()
    ep_keys = [k for k in aliases if k.startswith("ep-")]
    for k in ep_keys:
        del aliases[k]
    if ep_keys:
        print(
            f"[info] removed {len(ep_keys)} user-specific ARK endpoint aliases (ep-xxx)"
        )

    # (display, canonical, provider_key, extra_info)
    discovered: List[Tuple[str, str, str, str]] = []

    # ---------------------------------------------------------------------------
    # Scan OpenAI-compatible providers
    # ---------------------------------------------------------------------------
    for p in providers:
        api_key = _read_env(p.api_key_env)
        if not api_key:
            print(f"[skip] {p.key}: {p.api_key_env} not set")
            continue

        # Special handling for Gemini
        if p.key == "gemini":
            base_url = _read_env(p.base_url_env) if p.base_url_env else ""
            try:
                model_ids = _fetch_gemini_models(api_key, base_url or None)
                print(f"[ok] {p.key}: found {len(model_ids)} models")
            except Exception as exc:
                print(f"[warn] {p.key}: failed to list models: {exc}")
                continue
        else:
            base_url = _read_env(p.base_url_env) if p.base_url_env else ""
            base_url = base_url or (p.default_base_url or "")
            if not base_url:
                print(f"[skip] {p.key}: no base_url available")
                continue
            try:
                model_ids = _fetch_openai_compatible_models(api_key, base_url)
                print(f"[ok] {p.key}: found {len(model_ids)} models")
            except Exception as exc:
                print(f"[warn] {p.key}: failed to list models: {exc}")
                continue

        for mid in model_ids:
            display = f"{p.prefix}{mid}" if p.prefix else mid
            canon = _canonicalize(display)
            discovered.append((display, canon, p.key, ""))

    # ---------------------------------------------------------------------------
    # Scan ARK endpoints
    # ---------------------------------------------------------------------------
    if "ark" in enabled:
        ark_ak = _read_env("ARK_ACCESS_KEY_ID")
        ark_sk = _read_env("ARK_SECRET_ACCESS_KEY")
        if ark_ak and ark_sk:
            endpoints = _fetch_ark_endpoints(ark_ak, ark_sk)
            print(f"[ok] ark: found {len(endpoints)} endpoints")
            for model_name, endpoint_id in endpoints:
                display = f"ark/{model_name}"
                canon = _canonicalize(display)
                discovered.append((display, canon, "ark", f"ep={endpoint_id}"))
                # NOTE: Do NOT add ep-xxx aliases to model-map.json
                # ARK endpoint IDs are user-specific and should be resolved
                # at runtime by llm/__init__.py via _load_ark_models()
        else:
            print("[skip] ark: ARK_ACCESS_KEY_ID or ARK_SECRET_ACCESS_KEY not set")

    # ---------------------------------------------------------------------------
    # Resolve max_tokens for discovered models
    # ---------------------------------------------------------------------------
    missing: Set[str] = set()
    matched: Dict[str, str] = {}

    for display, canon, provider, extra in discovered:
        if canon in max_tokens and max_tokens[canon] > 0:
            continue

        mt, source = _resolve_max_tokens(canon)
        if mt is not None:
            max_tokens[canon] = mt
            matched[canon] = source or canon
            if args.verbose:
                print(f"  [match] {canon} -> {source} (max_tokens={mt})")
        else:
            missing.add(canon)
            if args.write_placeholders and canon not in max_tokens:
                max_tokens[canon] = 0

    # ---------------------------------------------------------------------------
    # Build aliases: display -> LiteLLM-recognized key (or canonical as fallback)
    # ---------------------------------------------------------------------------
    for display, canon, provider, extra in discovered:
        key = _canonicalize(display)

        # Determine the best target: prefer LiteLLM-recognized key
        litellm_key = _get_litellm_canonical(canon)
        target = litellm_key if litellm_key else canon

        # Always update if we have a better LiteLLM target (override old values)
        if key != target:
            if litellm_key:
                # Always prefer LiteLLM key
                aliases[key] = target
            elif key not in aliases:
                # Only set if not already present
                aliases[key] = target

        # Also add canon -> litellm_key mapping if different
        if litellm_key and canon != litellm_key:
            aliases[canon] = litellm_key

    # ---------------------------------------------------------------------------
    # Output: Clean up redundant max_tokens entries
    # ---------------------------------------------------------------------------
    # Remove max_tokens entries that can be inferred by:
    # 1. aliases -> LiteLLM key (e.g., deepseek-v3-1 -> deepseek-chat)
    # 2. pattern rules (e.g., qwen-max-0919 -> 8192 via qwen pattern)
    litellm_keys = {"deepseek-chat", "deepseek-reasoner"}  # Keys LiteLLM recognizes
    redundant_keys = []

    for key in list(max_tokens.keys()):
        # 1. If this key maps to a LiteLLM key via aliases, it's redundant
        if key in aliases and aliases[key] in litellm_keys:
            redundant_keys.append(key)
            continue
        # 2. If this key can be inferred via LiteLLM canonical rules
        if key not in litellm_keys and _get_litellm_canonical(key) in litellm_keys:
            redundant_keys.append(key)
            continue
        # 3. If this key can be inferred via pattern rules, and the inferred value matches
        inferred = infer_max_tokens_by_pattern(key)
        if inferred is not None and max_tokens[key] == inferred:
            redundant_keys.append(key)
            continue

    for key in redundant_keys:
        del max_tokens[key]
    if redundant_keys:
        print(
            f"[info] removed {len(redundant_keys)} redundant max_tokens entries (can be inferred)"
        )

    # Remove zero-value placeholders (non-LLM models like embedding, image, audio)
    # unless --write-placeholders is specified
    if not args.write_placeholders:
        zero_keys = [k for k, v in max_tokens.items() if v == 0]
        for key in zero_keys:
            del max_tokens[key]
        if zero_keys:
            print(
                f"[info] removed {len(zero_keys)} zero-value placeholders (non-LLM models)"
            )

    # ---------------------------------------------------------------------------
    # Output
    # ---------------------------------------------------------------------------
    output = {
        "aliases": dict(sorted(aliases.items())),
        "max_tokens": dict(sorted(max_tokens.items())),
    }
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n[ok] wrote: {output_path}")
    print(f"[info] discovered models: {len(discovered)}")
    print(f"[info] aliases: {len(aliases)}")
    print(f"[info] max_tokens entries: {len(max_tokens)}")

    if matched and args.verbose:
        print(
            f"\n[info] successfully matched {len(matched)} models via smart matching:"
        )
        for canon, litellm_key in sorted(matched.items())[:20]:
            print(f"  {canon} -> {litellm_key}")
        if len(matched) > 20:
            print("  ...")

    if missing:
        print(
            f"\n[warn] {len(missing)} models missing in LiteLLM (please fill max_tokens manually):"
        )
        for m in sorted(list(missing))[:50]:
            print(f"  - {m}")
        if len(missing) > 50:
            print("  ...")
        print(
            "\nHint: Edit model-map.json and set proper max_tokens values for missing models."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
