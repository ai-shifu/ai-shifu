"""Fixture: in-service import of a moved memory alias."""

from flaskr.service.profile.funcs import update_user_profile_with_lable


def caller() -> object:
    return update_user_profile_with_lable
