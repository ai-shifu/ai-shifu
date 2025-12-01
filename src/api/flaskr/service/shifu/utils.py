"""
Shifu utils

This module contains utility functions for shifu.

Author: yfge
Date: 2025-08-07
"""

from typing import Optional

from flask import Flask

from flaskr.service.resource.models import Resource


def get_shifu_res_url(res_bid: str):
    """
    Get the URL of a resource.

    Args:
        res_bid: The ID of the resource

    Returns:
        str: The URL of the resource
    """
    res = Resource.query.filter_by(resource_id=res_bid).first()
    if res:
        return res.url
    return ""


def get_shifu_res_url_dict(res_bids: list[str]) -> dict[str, str]:
    """
    Get the URL of a resource.

    Args:
        res_bids: The IDs of the resources

    Returns:
        dict[str, str]: The URL of the resource
    """
    res_url_map = {}
    res = Resource.query.filter(Resource.resource_id.in_(res_bids)).all()
    for r in res:
        res_url_map[r.resource_id] = r.url
    return res_url_map


def parse_shifu_res_bid(res_url: str):
    """
    Parse the resource ID from a URL.

    Args:
        res_url: The URL of the resource

    Returns:
        str: The resource ID
    """
    if res_url:
        return res_url.split("/")[-1]
    return ""


def get_shifu_creator_bid(app: Flask, shifu_bid: str) -> Optional[str]:
    """
    Resolve the creator user business identifier for a given shifu.

    Args:
        app: Flask application instance
        shifu_bid: Shifu business identifier

    Returns:
        Optional[str]: Creator user business identifier if found, otherwise None
    """
    from flaskr.service.shifu.models import DraftShifu, PublishedShifu

    with app.app_context():
        draft = (
            DraftShifu.query.filter(
                DraftShifu.shifu_bid == shifu_bid,
                DraftShifu.deleted == 0,
            )
            .order_by(DraftShifu.id.desc())
            .first()
        )
        if draft and draft.created_user_bid:
            return draft.created_user_bid

        published = (
            PublishedShifu.query.filter(
                PublishedShifu.shifu_bid == shifu_bid,
                PublishedShifu.deleted == 0,
            )
            .order_by(PublishedShifu.id.desc())
            .first()
        )
        if published and published.created_user_bid:
            return published.created_user_bid

    return None
