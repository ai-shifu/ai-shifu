def test_run_script(app):
    from flaskr.service.study.runscript import run_script

    run_script(
        app,
        "8ad420c61a664cc09ebbb0352e7163b2",
        "3bed65b7e700477bb878aacf95b616bd",
        "8c788a0987f8461ebb025d50072d3c4e",
        "都不算清楚",
        "text",
    )
