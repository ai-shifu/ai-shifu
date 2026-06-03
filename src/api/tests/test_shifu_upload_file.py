from types import SimpleNamespace

from flaskr.dao import db
from flaskr.service.resource.models import Resource
from flaskr.service.shifu import funcs


def test_upload_file_creates_resource_when_resource_id_is_missing(app, monkeypatch):
    class DummyFile:
        filename = "avatar.png"

    uploaded = SimpleNamespace(
        bucket="bucket",
        object_key="missing-resource-id",
        url="https://example.test/avatar.png",
    )

    monkeypatch.setattr(funcs, "get_image_content_type", lambda _filename: "image/png")
    monkeypatch.setattr(funcs, "upload_to_storage", lambda *args, **kwargs: uploaded)

    with app.app_context():
        db.session.query(Resource).filter_by(resource_id="missing-resource-id").delete()
        db.session.commit()

        result = funcs.upload_file(app, "user-1", "missing-resource-id", DummyFile())

        resource = Resource.query.filter_by(resource_id="missing-resource-id").first()
        assert result == uploaded.url
        assert resource is not None
        assert resource.name == "avatar.png"
        assert resource.oss_bucket == uploaded.bucket
        assert resource.oss_name == uploaded.object_key
        assert resource.url == uploaded.url
        assert resource.created_by == "user-1"
        assert resource.updated_by == "user-1"
