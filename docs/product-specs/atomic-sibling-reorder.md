---
title: Atomic Sibling Reorder
status: implemented
owner_surface: api
last_reviewed: 2026-09-28
canonical: true
---

# Atomic Sibling Reorder

`PATCH /api/shifu/shifus/<shifu_bid>/outlines/reorder` requires course edit
permission and accepts exactly one of two request modes:

- `{"order": ["lesson-b", "lesson-a"]}` reorders one complete sibling group.
  The nonempty list must contain unique, nonblank string BIDs for every current
  child of one parent, or every root item. Unknown, deleted, cross-parent, and
  partial groups are rejected without writes. This mode cannot move parents or
  delete nodes.
- `{"outlines": [...]}` retains the existing full-tree editing contract used
  by the web editor. Supplying both keys is rejected, including null values.

The response remains the common envelope with boolean `data: true` on success.

For `order`, the service acquires the existing course outline lock, then uses
locking current reads with refreshed ORM state. It selects the newest row per
outline BID before removing deleted nodes, validates the parent tree, and merges
only the requested sibling order. It preserves other groups' current order and
positions, except descendant positions that must follow a moved ancestor.
Content, access settings, and node identity are preserved in cloned revisions.
The complete tree history is saved in the same transaction, using a current read
to retain root metadata and legacy block children. Invalid parent graphs fail
closed rather than losing or silently reparenting nodes.

These guarantees cover this mode merging the latest committed structure under
the existing course lock. This change does not retrofit locking or optimistic
concurrency into every other course editor or the legacy full-tree mode.

The companion Course Creator CLI must send only the requested `order`. Deploy
this backend capability before the CLI change. An older backend rejects the
missing legacy `outlines`; the CLI must report that failure and must not retry
with a client-assembled full tree.
