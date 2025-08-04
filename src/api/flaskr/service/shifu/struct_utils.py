from typing import Optional
from flaskr.service.shifu.shifu_history_manager import HistoryItem


def find_node_with_parents(
    root: HistoryItem, target_bid: str, current_path: Optional[list[HistoryItem]] = None
) -> Optional[list[HistoryItem]]:
    if current_path is None:
        current_path = []
    current_path.append(root)
    if root.bid == target_bid:
        return current_path.copy()

    for i, child in enumerate(root.children):
        result = find_node_with_parents(child, target_bid, current_path)
        if result:
            return result
    current_path.pop()
    return None
