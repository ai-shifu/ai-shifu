# from ...dao import db
# from .models import Resource, ResourceUsage


# def create_resource(
#     app, user_id: str, name: str, type: int, oss_bucket: str, oss_name: str, url: str
# ):
#     resource = Resource(
#         user_id=user_id,
#         name=name,
#         type=type,
#         oss_bucket=oss_bucket,
#         oss_name=oss_name,
#         url=url,
#     )
#     db.session.add(resource)
#     db.session.commit()
#     return resource


# def get_resource(app, user_id: str, resource_id: str):
#     resource = Resource.query.filter_by(
#         user_id=user_id, resource_id=resource_id
#     ).first()
