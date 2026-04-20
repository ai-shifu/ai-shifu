from flaskr.dao import db
from flaskr.service.resource.models import Resource
from flaskr.service.shifu.models import DraftShifu, PublishedShifu
from flaskr.service.shifu.utils import (
    get_shifu_creator_bid,
    get_shifu_res_url,
    get_shifu_res_url_dict,
    parse_shifu_res_bid,
)


def test_resource_url_helpers(app):
    with app.app_context():
        res = Resource(
            resource_id="res-1",
            name="file",
            type=1,
            oss_bucket="bucket",
            oss_name="obj",
            url="https://example.com/path/res-1",
            status=1,
            is_deleted=0,
            created_by="user-1",
            updated_by="user-1",
        )
        db.session.add(res)
        db.session.commit()

        assert get_shifu_res_url("res-1") == "https://example.com/path/res-1"
        assert get_shifu_res_url_dict(["res-1"]) == {
            "res-1": "https://example.com/path/res-1"
        }
        assert parse_shifu_res_bid("https://example.com/path/res-1") == "res-1"


def test_get_shifu_creator_bid_prefers_draft(app):
    with app.app_context():
        draft = DraftShifu(
            shifu_bid="shifu-1",
            created_user_bid="creator-1",
        )
        published = PublishedShifu(
            shifu_bid="shifu-1",
            created_user_bid="creator-2",
        )
        db.session.add(draft)
        db.session.add(published)
        db.session.commit()

    assert get_shifu_creator_bid(app, "shifu-1") == "creator-1"
