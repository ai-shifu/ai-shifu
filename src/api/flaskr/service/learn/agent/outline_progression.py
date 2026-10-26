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


def _leaves(struct: OutlineNode) -> list[list[OutlineNode]]:
    """List every lesson in the outline, in order, each with the path that leads to it.

    Every lesson, not only the visible ones: the lesson that just ended is looked up here too, and
    an author may have hidden it while the learner was in it. Whether a lesson can be handed to is
    a separate question, answered by `_reachable`.
    """
    leaves: list[list[OutlineNode]] = []
    stack = [(struct, [])]
    while stack:
        node, above = stack.pop()
        path = [*above, node]
        if _is_leaf(node):
            leaves.append(path)
            continue
        stack.extend(
            (child, path)
            for child in reversed(node.children)
            if child.type == "outline"
        )
    return leaves


def _reachable(path: list[OutlineNode], hidden: dict[str, bool]) -> bool:
    """Whether a learner can be handed to the lesson at the end of `path`.

    Every item on the way down has to be visible, the root aside: a visible lesson inside a
    hidden chapter is not in the outline the learner was served. An item missing from `hidden`
    is treated as hidden, for the same reason -- advancing them onto something that was never
    shown would be worse than stopping.
    """
    return all(not hidden.get(node.bid, True) for node in path[1:])


def plan_lesson_completion(
    struct: OutlineNode,
    outline_bid: str,
    hidden: dict[str, bool],
    titles: dict[str, str],
) -> list[OutlineItemUpdateDTO]:
    """Describe the outline changes a finished lesson causes, in the order they happen.

    The lesson is marked complete. Every chapter the learner has now left is marked complete with
    it, and every chapter they have to enter to reach the next lesson is marked as in progress,
    followed by that lesson.

    Which chapters those are falls out of comparing two paths: a chapter the finished lesson sat
    in and the next one does not is a chapter that has ended, and the other way round is one being
    entered. Nothing has to be counted, and a chapter with nothing visible in it cannot be landed
    on because it holds no lesson to land on.

    An unknown lesson changes nothing. A lesson that was the last one in the course still
    completes, along with everything it closed; there is simply nowhere to go.

    The lesson that ended need not be visible itself. An author can hide a lesson while a learner
    is partway through it, and the learner still finishes it; they are handed on to the next
    lesson they can see, exactly as if nothing had been hidden. Requiring the ended lesson to be
    visible used to hand such a learner nowhere and close the chapter over lessons they had not
    yet reached.
    """
    path = _path_to(struct, outline_bid)
    if not path:
        return []
    onward = _next_reachable_lesson(struct, outline_bid, hidden)
    left_behind = {node.bid for node in path[1:-1]}
    ahead = {node.bid for node in onward[1:-1]}
    updates = [_completed(path[-1], titles)]
    # Innermost first: the chapter the lesson sat in ends before the one holding that chapter.
    updates.extend(
        _completed(node, titles)
        for node in reversed(path[1:-1])
        if node.bid not in ahead
    )
    # Outermost first: a chapter is entered before the chapter inside it.
    updates.extend(
        _in_progress(node, titles, has_children=True)
        for node in onward[1:-1]
        if node.bid not in left_behind
    )
    if onward:
        updates.append(_in_progress(onward[-1], titles, has_children=False))
    return updates


def _next_reachable_lesson(
    struct: OutlineNode, outline_bid: str, hidden: dict[str, bool]
) -> list[OutlineNode]:
    """Return the path to the first lesson after `outline_bid` a learner can be handed to.

    Position is taken from the whole outline, so the ended lesson is found whether or not it is
    still visible. Only what comes after it has to be reachable. Nothing is returned when
    `outline_bid` is a chapter rather than a lesson, or when no reachable lesson follows.

    Searched over the whole list rather than stepping from one sibling to the next: a chapter
    whose lessons are all hidden is nothing a learner can be handed to, and stepping would stop
    at it and hand them nowhere. Here it simply contributes no reachable lesson and the search
    carries on.
    """
    leaves = _leaves(struct)
    position = next(
        (index for index, leaf in enumerate(leaves) if leaf[-1].bid == outline_bid),
        None,
    )
    if position is None:
        return []
    return next(
        (leaf for leaf in leaves[position + 1 :] if _reachable(leaf, hidden)), []
    )


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
