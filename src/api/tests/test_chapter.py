def test_get_outline_tree(app):
    from flaskr.service.scenario.chapter_funcs import get_outline_tree
    from flaskr.route.common import make_common_response

    app.logger.info("test_get_outline_tree")

    user_id = "ab769989275a4eddbdf589558b9df089"
    scenario_id = "3bed65b7e700477bb878aacf95b616bd"
    outline_tree = get_outline_tree(app, user_id, scenario_id)
    app.logger.info(make_common_response(outline_tree))
