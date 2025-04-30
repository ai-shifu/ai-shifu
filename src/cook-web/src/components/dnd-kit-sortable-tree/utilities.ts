/* eslint-disable @typescript-eslint/no-unused-vars */
import { arrayMove } from '@dnd-kit/sortable';

import type { FlattenedItem, TreeItem, TreeItems } from './types';
import { UniqueIdentifier } from '@dnd-kit/core';

export const iOS =
  typeof window !== 'undefined'
    ? /iPad|iPhone|iPod/.test(navigator.platform)
    : false;

function getDragDepth(offset: number, indentationWidth: number) {
  return Math.round(offset / indentationWidth);
}

let _revertLastChanges = () => {};
export function getProjection<T>(
  items: FlattenedItem<T>[],
  activeId: UniqueIdentifier | null,
  overId: UniqueIdentifier | null,
  dragOffset: number,
  indentationWidth: number,
  keepGhostInPlace: boolean,
  canRootHaveChildren?: boolean | ((dragItem: FlattenedItem<T>) => boolean),
): {
  depth: number;
  parentId: UniqueIdentifier | null;
  parent: FlattenedItem<T> | null;
  isLast: boolean;
} | null {
  _revertLastChanges();
  _revertLastChanges = () => {};
  if (!activeId || !overId) return null;

  const overItemIndex = items.findIndex(({ id }) => id === overId);
  const activeItemIndex = items.findIndex(({ id }) => id === activeId);
  const activeItem = items[activeItemIndex];
  if (!activeItem) {
    return null;
  }
  if (keepGhostInPlace) {
    let parent: FlattenedItem<T> | null | undefined = items[overItemIndex];
    parent = findParentWhichCanHaveChildren(
      parent,
      activeItem,
      canRootHaveChildren,
    );
    if (parent === undefined) return null;
    return {
      depth: parent?.depth ?? 0 + 1,
      parentId: parent?.id ?? null,
      parent: parent,
      isLast: !!parent?.isLast,
    };
  }
  const newItems = arrayMove(items, activeItemIndex, overItemIndex);
  const previousItem = newItems[overItemIndex - 1];
  const nextItem = newItems[overItemIndex + 1];
  // Keep the same depth as the original item for same-level-only dragging
  const depth = activeItem.depth;

  // Find the parent based on the original item's depth
  const parent =
    previousItem && previousItem.depth === depth
      ? previousItem.parent
      : activeItem.parent;
  const isLast = (nextItem?.depth ?? -1) < depth;

  if (parent && parent.isLast) {
    _revertLastChanges = () => {
      parent!.isLast = true;
    };
    parent.isLast = false;
  }
  return {
    depth,
    parentId: getParentId(),
    parent,
    isLast,
  };

  function findParentWithDepth(depth: number, previousItem: FlattenedItem<T>) {
    if (!previousItem) return null;
    while (depth < previousItem.depth) {
      if (previousItem.parent === null) return null;
      previousItem = previousItem.parent;
    }
    return previousItem;
  }
  function findParentWhichCanHaveChildren(
    parent: FlattenedItem<T> | null,
    dragItem: FlattenedItem<T>,
    canRootHaveChildren?: boolean | ((dragItem: FlattenedItem<T>) => boolean),
  ): FlattenedItem<T> | null | undefined {
    if (!parent) {
      const rootCanHaveChildren =
        typeof canRootHaveChildren === 'function'
          ? canRootHaveChildren(dragItem)
          : canRootHaveChildren;
      if (rootCanHaveChildren === false) return undefined;
      return parent;
    }
    const canHaveChildren =
      typeof parent.canHaveChildren === 'function'
        ? parent.canHaveChildren(dragItem)
        : parent.canHaveChildren;
    if (canHaveChildren === false)
      return findParentWhichCanHaveChildren(
        parent.parent,
        activeItem,
        canRootHaveChildren,
      );
    return parent;
  }

  function getParentId() {
    // Keep the same parent ID for same-level dragging
    return activeItem.parentId;
  }
}

function flatten<T extends Record<string, any>>(
  items: TreeItems<T>,
  parentId: UniqueIdentifier | null = null,
  depth = 0,
  parent: FlattenedItem<T> | null = null,
): FlattenedItem<T>[] {
  return items?.reduce<FlattenedItem<T>[]>((acc, item, index) => {
    const flattenedItem: FlattenedItem<T> = {
      ...item,
      parentId,
      depth,
      index,
      isLast: items.length === index + 1,
      parent: parent,
    };
    return [
      ...acc,
      flattenedItem,
      ...flatten(item.children ?? [], item.id, depth + 1, flattenedItem),
    ];
  }, []);
}

export function flattenTree<T extends Record<string, any>>(
  items: TreeItems<T>,
): FlattenedItem<T>[] {
  return flatten(items);
}

export function buildTree<T extends Record<string, any>>(
  flattenedItems: FlattenedItem<T>[],
): TreeItems<T> {
  const root: TreeItem<T> = { id: 'root', children: [] } as any;
  const nodes: Record<string, TreeItem<T>> = { [root.id]: root };
  const items = flattenedItems.map((item) => ({ ...item, children: [] }));

  for (const item of items) {
    const { id } = item;
    const parentId = item.parentId ?? root.id;
    const parent = nodes[parentId] ?? findItem(items, parentId);
    item.parent = null;
    nodes[id] = item;
    parent?.children?.push(item);
  }

  return root.children ?? [];
}

export function findItem<T>(items: TreeItem<T>[], itemId: UniqueIdentifier) {
  return items.find(({ id }) => id === itemId);
}

export function findItemDeep<T extends Record<string, any>>(
  items: TreeItems<T>,
  itemId: UniqueIdentifier,
): TreeItem<T> | undefined {
  for (const item of items) {
    const { id, children } = item;

    if (id === itemId) {
      return item;
    }

    if (children?.length) {
      const child = findItemDeep(children, itemId);

      if (child) {
        return child;
      }
    }
  }

  return undefined;
}

export function removeItem<T extends Record<string, any>>(
  items: TreeItems<T>,
  id: string,
) {
  const newItems = [];

  for (const item of items) {
    if (item.id === id) {
      continue;
    }

    if (item.children?.length) {
      item.children = removeItem(item.children, id);
    }

    newItems.push(item as never);
  }

  return newItems;
}

export function setProperty<
  TData extends Record<string, any>,
  T extends keyof TreeItem<TData>,
>(
  items: TreeItems<TData>,
  id: string,
  property: T,
  setter: (value: TreeItem<TData>[T]) => TreeItem<TData>[T],
) {
  for (const item of items) {
    if (item.id === id) {
      item[property] = setter(item[property]);
      continue;
    }

    if (item.children?.length) {
      item.children = setProperty(item.children, id, property, setter);
    }
  }

  return [...items];
}

function countChildren<T>(items: TreeItem<T>[], count = 0): number {
  return items.reduce((acc, { children }) => {
    if (children?.length) {
      return countChildren(children, acc + 1);
    }

    return acc + 1;
  }, count);
}

export function getChildCount<T extends Record<string, any>>(
  items: TreeItems<T>,
  id: UniqueIdentifier,
) {
  if (!id) {
    return 0;
  }

  const item = findItemDeep(items, id);

  return item ? countChildren(item.children ?? []) : 0;
}

export function removeChildrenOf<T>(
  items: FlattenedItem<T>[],
  ids: UniqueIdentifier[],
) {
  const excludeParentIds = [...ids];

  return items.filter((item) => {
    if (item.parentId && excludeParentIds.includes(item.parentId)) {
      if (item.children?.length) {
        excludeParentIds.push(item.id);
      }
      return false;
    }

    return true;
  });
}

export function getIsOverParent<T>(
  parent: FlattenedItem<T> | null,
  overId: UniqueIdentifier,
): boolean {
  if (!parent || !overId) return false;
  if (parent.id === overId) return true;
  return getIsOverParent(parent.parent, overId);
}
