"""Work out which outline items change state when a 2.0 lesson ends.

A lesson that ends is not the only thing that changed: its chapter may have ended with it, and
the lesson after it has become the one the learner is on. The browser learns all of this from
`outline_item_update` events, and learns it from nothing else -- the outline in the sidebar, the
tick beside a finished lesson, and the flag that stops the page asking for more content all hang
off them. A 2.0 lesson sent none, so a learner who finished one was left looking at a lesson that
still called itself unfinished, while the page quietly asked for a continuation that did not exist.

What is decided here is only *which* items changed and how. Writing that down, and turning it into
events, belongs to the caller: this walks a tree and returns a list, so it can be tested against
an outline without a database, a learner, or a lesson.

The equivalent for 1.0 lives in `learn/run/state.py` and decides the same thing from a block
position, which 2.0 has no notion of -- its lesson ends when the engine says the lesson is over.
The two should converge once 1.0 is retired; until then this deliberately covers only the endings
a 2.0 lesson produces, rather than reimplementing a state machine that already works.
"""

from __future__ import annotations

from typing import Protocol

from flaskr.service.learn.learn_dtos import LearnStatus, OutlineItemUpdateDTO


class OutlineNode(Protocol):
    """The part of a course outline this needs, whoever built the tree.

    Stated structurally rather than imported: deciding what a finished lesson changed is a walk
    over a tree, and tying it to the course service's own class would drag that service into a
    module whose whole point is that it can be read, and tested, on its own.
    """

    bid: str
    type: str
    children: list[OutlineNode]


def _path_to(root: OutlineNode, target_bid: str) -> list[OutlineNode]:
    """Return the nodes from the root down to `target_bid`, or nothing if it is not there."""
    stack: list[tuple[OutlineNode, list[OutlineNode]]] = [(root, [])]
    while stack:
        node, above = stack.pop()
        path = [*above, node]
        if node.bid == target_bid:
            return path
        stack.extend((child, path) for child in node.children)
    return []


def _is_leaf(item: OutlineNode) -> bool:
    """Whether this item is a lesson rather than a chapter holding lessons."""
    return not (item.children and item.children[0].type == "outline")


def _visible_children(item: OutlineNode, hidden: dict[str, bool]) -> list[OutlineNode]:
    """Return the children a learner can see, in order.

    An item missing from `hidden` is treated as hidden: it is not in the outline the learner was
    served, and advancing them onto something that was never shown would be worse than stopping.
    """
    return [
        child
        for child in item.children
        if child.type == "outline" and not hidden.get(child.bid, True)
    ]


def _first_leaf(item: OutlineNode, hidden: dict[str, bool]) -> OutlineNode | None:
    """Return the first lesson inside this item, descending through chapters."""
    while not _leaf_or_none(item, hidden):
        children = _visible_children(item, hidden)
        if not children:
            return None
        item = children[0]
    return item if not hidden.get(item.bid, True) else None


def _leaf_or_none(item: OutlineNode, hidden: dict[str, bool]) -> bool:
    """Whether descending stops here, either because it is a lesson or because it is empty."""
    return _is_leaf(item) or not _visible_children(item, hidden)


def plan_lesson_completion(
    struct: OutlineNode,
    outline_bid: str,
    hidden: dict[str, bool],
    titles: dict[str, str],
) -> list[OutlineItemUpdateDTO]:
    """Describe the outline changes a finished lesson causes, in the order they happen.

    The lesson is marked complete. Each chapter it was the last visible lesson of is marked
    complete with it, up the tree. Then the next visible lesson, wherever it sits, becomes the
    one in progress, along with the chapters that had to be entered to reach it.

    An unknown lesson, or a lesson that was the last one in the course, yields what it can: the
    completions still stand, there is simply nothing to move on to.
    """
    path = _path_to(struct, outline_bid)
    if not path:
        return []
    updates = [_completed(path[-1], titles)]
    # Walk out through the ancestors: a chapter is over when the lesson that just ended was the
    # last thing in it a learner could see. The first ancestor that still has something after it
    # stops the walk, and is where the next lesson is looked for.
    index = len(path) - 1
    while index > 0:
        parent = path[index - 1]
        siblings = _visible_children(parent, hidden)
        if path[index].bid not in [s.bid for s in siblings]:
            break
        position = [s.bid for s in siblings].index(path[index].bid)
        if position < len(siblings) - 1:
            updates.extend(
                _entering(siblings[position + 1], hidden, titles, path[: index - 1])
            )
            return updates
        if parent is struct:
            break
        updates.append(_completed(parent, titles))
        index -= 1
    return updates


def _entering(
    item: OutlineNode,
    hidden: dict[str, bool],
    titles: dict[str, str],
    _ancestors: list[OutlineNode],
) -> list[OutlineItemUpdateDTO]:
    """Return the item the learner moves on to, and the chapters entered to reach it."""
    updates: list[OutlineItemUpdateDTO] = []
    while not _leaf_or_none(item, hidden):
        updates.append(_in_progress(item, titles, has_children=True))
        children = _visible_children(item, hidden)
        if not children:
            return updates
        item = children[0]
    if hidden.get(item.bid, True):
        return updates
    updates.append(_in_progress(item, titles, has_children=False))
    return updates


def _completed(item: OutlineNode, titles: dict[str, str]) -> OutlineItemUpdateDTO:
    return OutlineItemUpdateDTO(
        outline_bid=item.bid,
        title=titles.get(item.bid, ""),
        status=LearnStatus.COMPLETED,
        has_children=bool(item.children and item.children[0].type == "outline"),
    )


def _in_progress(
    item: OutlineNode, titles: dict[str, str], *, has_children: bool
) -> OutlineItemUpdateDTO:
    return OutlineItemUpdateDTO(
        outline_bid=item.bid,
        title=titles.get(item.bid, ""),
        status=LearnStatus.IN_PROGRESS,
        has_children=has_children,
    )
