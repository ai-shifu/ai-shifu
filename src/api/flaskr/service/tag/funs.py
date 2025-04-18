import uuid
from flask import Flask
from .models import Tag
from ...dao import db

tag_type_list = [
    {
        "tag_domain": "rag",
        "tag_type": "knowledge_base",
    },
    {
        "tag_domain": "rag",
        "tag_type": "file",
    },
]


def get_tag_type_list(app: Flask):
    with app.app_context():
        return tag_type_list


def get_tag_list(app: Flask):
    with app.app_context():
        return [
            {
                "tag_id": tag.tag_id,
                "tag_domain": tag.tag_domain,
                "tag_type": tag.tag_type,
                "tag_name": tag.tag_name,
            }
            for tag in Tag.query.all()
        ]


def tag_add(
    app: Flask,
    tag_domain: str,
    tag_type: str,
    tag_name: str,
    user_id: str,
):
    with app.app_context():
        if Tag.query.filter_by(tag_name=tag_name).first():
            app.logger.error(f"Tag with tag_name {tag_name} already exists")
            return False
        tag_id = str(uuid.uuid4()).replace("-", "")
        tag_item = Tag(
            tag_id=tag_id,
            tag_domain=tag_domain,
            tag_type=tag_type,
            tag_name=tag_name,
            created_user_id=user_id,
        )
        db.session.add(tag_item)
        db.session.commit()
        return True


def tag_update(app: Flask, tag_id: str, tag_name: str, user_id: str):
    with app.app_context():
        tag_item = Tag.query.filter_by(tag_id=tag_id).first()
        if not tag_item:
            return False
        tag_item.tag_name = tag_name
        tag_item.updated_user_id = user_id
        db.session.commit()
        return True


def tag_drop(app: Flask, tag_id_list: list):
    with app.app_context():
        tags_to_delete = Tag.query.filter(Tag.tag_id.in_(tag_id_list)).all()
        if not tags_to_delete:
            return False
        for tag in tags_to_delete:
            db.session.delete(tag)
        db.session.commit()
        return True
