"""Shifu struct utils

This module contains utils for shifu struct.

Author: yfge
Date: 2025-08-07
"""

from typing import Optional

from flaskr.service.shifu.shifu_history_manager import HistoryItem


def find_node_with_parents(
    root: HistoryItem, target_bid: str, current_path: Optional[list[HistoryItem]] = None
) -> Optional[list[HistoryItem]]:
    """Find node with parents
    Args:
        root: Root node
        target_bid: Target bid
        current_path: Current path
    Returns:
        Optional[list[HistoryItem]]: Path to target node
    """
    if current_path is None:
        current_path = []
    current_path.append(root)
    if root.bid == target_bid:
        return current_path.copy()

    for _i, child in enumerate(root.children):
        result = find_node_with_parents(child, target_bid, current_path)
        if result:
            return result
    current_path.pop()
    return None
