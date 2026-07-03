"""Canonical ask-provider constants.

These constants identify the external providers that can answer learner
follow-up questions and the modes controlling how provider answers combine
with the LLM. They are keyed off by both registry halves:

- runtime dispatch: ``flaskr/service/learn/ask_provider_adapters/registry.py``
- config/schema: ``flaskr/service/shifu/ask_provider_registry.py``

``flaskr/service/shifu/shifu_draft_funcs.py`` (their historical home)
re-exports them during a deprecation window so existing importers keep
working.
"""

ASK_PROVIDER_LLM = "llm"
ASK_PROVIDER_DIFY = "dify"
ASK_PROVIDER_COZE = "coze"
ASK_PROVIDER_COZE_WORKFLOW = "coze_workflow"
ASK_PROVIDER_VOLC_KNOWLEDGE = "volc_knowledge"
ASK_PROVIDER_MODE_PROVIDER_ONLY = "provider_only"
ASK_PROVIDER_MODE_PROVIDER_THEN_LLM = "provider_then_llm"

SUPPORTED_ASK_PROVIDERS = {
    ASK_PROVIDER_LLM,
    ASK_PROVIDER_DIFY,
    ASK_PROVIDER_COZE,
    ASK_PROVIDER_COZE_WORKFLOW,
    ASK_PROVIDER_VOLC_KNOWLEDGE,
}
SUPPORTED_ASK_PROVIDER_MODES = {
    ASK_PROVIDER_MODE_PROVIDER_ONLY,
    ASK_PROVIDER_MODE_PROVIDER_THEN_LLM,
}
