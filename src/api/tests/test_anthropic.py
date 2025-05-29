def test_llm_anthropic(app):
    from flaskr.api.llm import invoke_llm
    from flaskr.api.langfuse import langfuse_client

    msg = "Hello, can you help me with a simple Python question?"

    res = invoke_llm(
        app,
        "test_user",
        langfuse_client.span(),
        model="anthropic/claude-sonnet-4-20250514",
        message=msg,
        temperature="0.5",
    )
    for message in res:
        print(message)
    pass
