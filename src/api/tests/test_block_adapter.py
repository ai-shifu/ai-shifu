def test_block_adapter(app):
    from flaskr.service.scenario.adapter import convert_dict_to_block_dto
    import json

    test_file = ["test_block1.json", "test_block2.json", "test_block3.json"]
    for file in test_file:
        json_file = open("tests/" + file, "r")
        json_data = json.load(json_file)
        data = json_data.get("data", [])
        for item in data:
            if item.get("type") == "block":
                block_dto = convert_dict_to_block_dto(item)
                app.logger.info(block_dto.__json__())
