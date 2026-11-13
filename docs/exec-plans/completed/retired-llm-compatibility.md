---
title: Remove retired model compatibility from the LLM gateway
---

## Purpose / Big Picture

Remove provider-specific request overrides and synthetic catalog entries for
model IDs that AI-Shifu has retired or that the serving provider has shut down.
Keep discovery, numbered course routing, and request preparation for active
models working through the existing gateway.

## Progress

- [x] 2026-11-13 12:27 CST: Verified the upgrade PR base, reviewed provider
  lifecycle evidence, and checked current course slot bindings in both regions.
- [x] 2026-11-13 12:29 CST: Removed the model-specific entries and updated
  targeted gateway tests.
- [x] 2026-11-13 12:34 CST: Passed 659 focused tests with LiteLLM 1.109.1 and
  the repository-wide pre-commit checks.
- [x] 2026-11-13 12:39 CST: Ran the full backend suite with local Redis.
  It finished with 16,313 passing and 20 skipped.

## Surprises & Discoveries

- BigModel documents the January 30 retirement of
  [GLM-4.5-Flash](https://docs.bigmodel.cn/cn/guide/models/free/glm-4.5-flash)
  and forwards requests using that ID to GLM-4.7-Flash. Its
  [GLM-4.5 page](https://docs.bigmodel.cn/cn/guide/models/text/glm-4.5)
  gives no exact cutoff for the base and X IDs. The
  [domestic catalog](https://docs.bigmodel.cn/cn/guide/start/model-overview)
  still lists Air and AirX. Other deployments can still offer the series,
  including [OpenRouter](https://openrouter.ai/z-ai/glm-4.5-air/providers).
- DeepSeek shut down the direct API aliases `deepseek-chat` and
  `deepseek-reasoner` on July 24 at 15:59 UTC.
  [DeepSeek's announcement](https://api-docs.deepseek.com/news/news260424/)
  and [current catalog](https://api-docs.deepseek.com/quick_start/pricing/)
  document the transition. The
  [September update](https://api-docs.deepseek.com/updates/#date-2026-09-10)
  says `deepseek-v4-flash` still forwards to V4.1 Flash.
- Model Studio shut down its bare `deepseek-r1` and `deepseek-v3` IDs on
  October 10 at 00:00 UTC+08. Provider-qualified IDs still appear in the
  catalog. The same notice retires Model Studio's GLM-4.6 and GLM-4.7
  IDs. The BigModel routes use a different endpoint.
  [Model Studio notice](https://www.alibabacloud.com/en/notice/model_studio_notice_on_the_postponed_retirement_of_selected_legacy_models_7d0?_p_lc=1)
  [Model Studio catalog](https://help.aliyun.com/zh/model-studio/model-list-text-generation)

## Decision Log

- Remove the six BigModel GLM-4.5 exact-model thinking overrides under the
  confirmed AI-Shifu retirement decision. A direct request still using a
  discovered GLM-4.5 ID will follow the normal SDK capability path. That
  path may omit the disabled-thinking field, including when the provider
  forwards the old Flash ID.
- Remove the two unavailable DeepSeek API aliases from fallback discovery.
  Include current `deepseek-flash` and keep the working `deepseek-v4-flash`
  alias and `deepseek-v4-pro`. Stop unconditionally advertising the two
  retired Model Studio IDs and let DashScope discovery supply its catalog.
- Keep the shared rules for DashScope, SiliconFlow, and Ark, and keep the
  active BigModel tests. Preserve Gemini 3.7 Flash because its ID still
  forwards, Gemini 2.5 Pro because existing Developer API access remains
  supported on the audit date, and the OpenAI Pro aliases, snapshots, and
  Astra request rules because no completed shutdown was established.
  The published GPT-5 Pro alias and snapshot shutdown is December 11.
  [Gemini lifecycle](https://aistudio.google.com/docs/deprecations)
  [OpenAI lifecycle](https://developers.openai.com/api/docs/deprecations)

## Outcomes & Retrospective

The 659 focused tests passed with the real SDK imported before pytest
collection, which keeps the existing unit-test stub from taking precedence.
Provider contract tests used simulated HTTP. The admission tests used local
Redis. Production checks read catalogs, deployment configuration, and rate
identities. The development deployment runs an earlier revision and no
authorized smoke path for the changed build was established.

## Context and Orientation

`src/api/flaskr/api/llm/__init__.py` owns provider discovery, fallback IDs,
and request preparation. `model_selection.py` in the same directory resolves
numbered text course selections. Current China and US course slot bindings
and active rate rows showed no affected IDs. Historical physical text model
selections fall back to slot 1. Direct physical-model gateway calls and
historical usage were outside the deployment readback.

## Plan of Work

Stack this change on [the LiteLLM upgrade PR](https://github.com/ai-shifu/ai-shifu/pull/3400)
while it is open so reviewers see the retirement diff separately. After the
upgrade lands, replay the cleanup commit onto the resulting main revision and
retarget the cleanup PR to main before it is considered for merge.

## Concrete Steps

Prune the provider-scoped rows in the gateway. Remove the GLM-4.5-only
assertions, use the configured Qwen snapshot for the shared DashScope request
contract, and verify that provider discovery preserves namespaced model IDs.

## Validation and Acceptance

Run the provider-boundary, LLM, and LiteLLM contract tests with the pinned
SDK. The contract tests intercept HTTP and inspect requests, response
streams, and usage. They use dummy credentials. Run the repository checks
before committing. Verify that the PR shows only retirement-related changes.

## Idempotence and Recovery

If a deployment still relies on a removed override, identify the exact
provider and ID before restoring it. This change has no configuration
migration or data migration.

## Interfaces and Dependencies

The cleanup uses the LiteLLM 1.109.1 behavior established in the
[upgrade plan](./litellm-1-109-upgrade.md). Provider configuration keys,
course selections, and public API DTOs keep their existing contracts.
