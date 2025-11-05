"""
Shifu utils

This module contains utility functions for shifu.

Author: yfge
Date: 2025-08-07
"""

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
