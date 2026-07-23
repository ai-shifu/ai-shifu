from flaskr.service.shifu.consts import STATUS_PUBLISHED
from flaskr.service.shifu.dtos import ShifuDto


def test_shifu_dto_json_includes_state():
    dto = ShifuDto(
        shifu_id="course-1",
        shifu_name="Course 1",
        shifu_description="description",
        shifu_avatar="avatar",
        shifu_state=STATUS_PUBLISHED,
        is_favorite=False,
        archived=False,
        created_user_bid="owner-1",
    )

    assert dto.__json__()["state"] == STATUS_PUBLISHED
