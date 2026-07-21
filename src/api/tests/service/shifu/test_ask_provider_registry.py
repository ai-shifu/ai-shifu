from flaskr.service.shifu import ask_provider_registry as module
from flaskr.i18n import set_language


def test_validate_dify_requires_shifu_level_base_url_and_api_key():
    is_valid, field = module.validate_ask_provider_specific_config(
        "dify", {"conversation_id": "conv-1"}
    )

    assert is_valid is False
    assert field == "base_url"


def test_validate_dify_shifu_level_config_success():
    is_valid, field = module.validate_ask_provider_specific_config(
        "dify",
        {
            "base_url": "https://dify.example.com/v1",
            "api_key": "dify-key",
            "conversation_id": "conv-1",
        },
    )

    assert is_valid is True
    assert field is None


def test_validate_coze_requires_api_key_and_bot_id():
    is_valid, field = module.validate_ask_provider_specific_config(
        "coze",
        {
            "api_key": "coze-key",
        },
    )

    assert is_valid is False
    assert field == "bot_id"


def test_validate_coze_workflow_requires_api_key_and_workflow_id():
    is_valid, field = module.validate_ask_provider_specific_config(
        "coze_workflow",
        {
            "api_key": "coze-key",
        },
    )

    assert is_valid is False
    assert field == "workflow_id"


def test_validate_coze_workflow_config_success():
    is_valid, field = module.validate_ask_provider_specific_config(
        "coze_workflow",
        {
            "base_url": "https://api.coze.cn",
            "api_key": "coze-key",
            "workflow_id": "workflow-1",
        },
    )

    assert is_valid is True
    assert field is None


def test_validate_volc_knowledge_requires_account_credentials_and_collection():
    is_valid, field = module.validate_ask_provider_specific_config(
        "volc_knowledge",
        {
            "account_id": "acc-1",
            "ak": "ak-1",
            "sk": "",
            "collection_name": "c1",
        },
    )

    assert is_valid is False
    assert field == "sk"


def test_validate_volc_knowledge_config_success():
    is_valid, field = module.validate_ask_provider_specific_config(
        "volc_knowledge",
        {
            "account_id": "acc-1",
            "ak": "ak-1",
            "sk": "sk-1",
            "collection_name": "c1",
        },
    )

    assert is_valid is True
    assert field is None


def test_validate_get_biji_knowledge_requires_credentials_and_topic():
    is_valid, field = module.validate_ask_provider_specific_config(
        "get_biji_knowledge",
        {
            "api_key": "gk-live-1",
            "client_id": "",
            "topic_id": "topic-1",
        },
    )

    assert is_valid is False
    assert field == "client_id"


def test_validate_get_biji_knowledge_rejects_top_k_out_of_range():
    base_config = {
        "api_key": "gk-live-1",
        "client_id": "cli-1",
        "topic_id": "topic-1",
    }

    for bad_top_k in (0, -3, 11, 12, "999", "abc"):
        is_valid, field = module.validate_ask_provider_specific_config(
            "get_biji_knowledge",
            {**base_config, "top_k": bad_top_k},
        )

        assert is_valid is False, f"top_k={bad_top_k!r} should be rejected"
        assert field == "top_k"


def test_validate_get_biji_knowledge_accepts_top_k_boundaries():
    base_config = {
        "api_key": "gk-live-1",
        "client_id": "cli-1",
        "topic_id": "topic-1",
    }

    for good_top_k in (1, 10, "5", None):
        is_valid, field = module.validate_ask_provider_specific_config(
            "get_biji_knowledge",
            {**base_config, "top_k": good_top_k},
        )

        assert is_valid is True, f"top_k={good_top_k!r} should be accepted"
        assert field is None


def test_validate_get_biji_knowledge_config_success():
    is_valid, field = module.validate_ask_provider_specific_config(
        "get_biji_knowledge",
        {
            "api_key": "gk-live-1",
            "client_id": "cli-1",
            "topic_id": "topic-1",
            "top_k": 5,
        },
    )

    assert is_valid is True
    assert field is None


def test_ask_provider_metadata_contains_shifu_level_defaults():
    metadata = module.get_ask_provider_metadata()
    providers = {item["provider"]: item for item in metadata.get("providers", [])}

    dify = providers.get("dify", {})
    coze = providers.get("coze", {})
    coze_workflow = providers.get("coze_workflow", {})
    volc = providers.get("volc_knowledge", {})
    get_biji = providers.get("get_biji_knowledge", {})

    assert dify.get("default_config", {}) == {
        "base_url": "",
        "api_key": "",
    }
    assert coze.get("default_config", {}) == {
        "api_key": "",
        "bot_id": "",
    }
    assert coze_workflow.get("default_config", {}) == {
        "api_key": "",
        "workflow_id": "",
    }
    assert volc.get("default_config", {}) == {
        "account_id": "",
        "ak": "",
        "sk": "",
        "collection_name": "",
    }
    assert get_biji.get("default_config", {}) == {
        "api_key": "",
        "client_id": "",
        "topic_id": "",
        "top_k": 5,
    }


def test_ask_provider_metadata_marks_api_key_as_password():
    metadata = module.get_ask_provider_metadata()
    providers = {item["provider"]: item for item in metadata.get("providers", [])}

    dify_api_key = (
        providers.get("dify", {})
        .get("json_schema", {})
        .get("properties", {})
        .get("api_key", {})
    )
    coze_api_key = (
        providers.get("coze", {})
        .get("json_schema", {})
        .get("properties", {})
        .get("api_key", {})
    )
    coze_workflow_api_key = (
        providers.get("coze_workflow", {})
        .get("json_schema", {})
        .get("properties", {})
        .get("api_key", {})
    )
    volc_ak = (
        providers.get("volc_knowledge", {})
        .get("json_schema", {})
        .get("properties", {})
        .get("ak", {})
    )
    volc_sk = (
        providers.get("volc_knowledge", {})
        .get("json_schema", {})
        .get("properties", {})
        .get("sk", {})
    )
    get_biji_api_key = (
        providers.get("get_biji_knowledge", {})
        .get("json_schema", {})
        .get("properties", {})
        .get("api_key", {})
    )

    assert dify_api_key.get("format") == "password"
    assert coze_api_key.get("format") == "password"
    assert coze_workflow_api_key.get("format") == "password"
    assert volc_ak.get("format") == "password"
    assert volc_sk.get("format") == "password"
    assert get_biji_api_key.get("format") == "password"


def test_ask_provider_metadata_includes_all_providers():
    metadata = module.get_ask_provider_metadata()
    providers = {item["provider"] for item in metadata.get("providers", [])}

    assert metadata.get("feature_enabled") is True
    assert providers == {
        "llm",
        "dify",
        "coze",
        "coze_workflow",
        "volc_knowledge",
        "get_biji_knowledge",
    }


def test_ask_provider_metadata_exposes_minimal_schema_properties():
    metadata = module.get_ask_provider_metadata()
    providers = {item["provider"]: item for item in metadata.get("providers", [])}

    dify_fields = (
        providers.get("dify", {}).get("json_schema", {}).get("properties", {}).keys()
    )
    coze_fields = (
        providers.get("coze", {}).get("json_schema", {}).get("properties", {}).keys()
    )
    coze_workflow_fields = (
        providers.get("coze_workflow", {})
        .get("json_schema", {})
        .get("properties", {})
        .keys()
    )
    volc_fields = (
        providers.get("volc_knowledge", {})
        .get("json_schema", {})
        .get("properties", {})
        .keys()
    )
    get_biji_fields = (
        providers.get("get_biji_knowledge", {})
        .get("json_schema", {})
        .get("properties", {})
        .keys()
    )

    assert set(dify_fields) == {"base_url", "api_key"}
    assert set(coze_fields) == {"api_key", "bot_id"}
    assert set(coze_workflow_fields) == {"api_key", "workflow_id"}
    assert set(volc_fields) == {"account_id", "ak", "sk", "collection_name"}
    assert set(get_biji_fields) == {"api_key", "client_id", "topic_id", "top_k"}


def test_ask_provider_metadata_localizes_text_for_zh_cn(app):
    _ = app
    set_language("zh-CN")
    try:
        metadata = module.get_ask_provider_metadata()
        providers = {item["provider"]: item for item in metadata.get("providers", [])}
        coze = providers["coze"]

        assert coze["title"] == "Coze"
        assert coze["description"] == "用 Coze Bot 回答学员追问。"
        assert coze["json_schema"]["properties"]["api_key"]["title"] == "API 密钥"
        assert (
            coze["json_schema"]["properties"]["bot_id"]["description"]
            == "Coze Bot 标识。"
        )
        get_biji = providers["get_biji_knowledge"]
        assert get_biji["title"] == "Get 笔记知识库"
        assert (
            get_biji["json_schema"]["properties"]["topic_id"]["description"]
            == "Get 笔记知识库 ID。"
        )
    finally:
        # Always restore the default locale so a failed assertion above
        # cannot leak zh-CN into subsequent tests.
        set_language("en-US")
