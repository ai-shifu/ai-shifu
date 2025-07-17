def migrate_shifu_draft_to_shifu_draft_v2(app, shifu_bid: str):
    with app.app_context():
        from flaskr.framework.plugin.plugin_manager import plugin_manager

        plugin_manager.is_enabled = False

        plugin_manager.is_enabled = True
