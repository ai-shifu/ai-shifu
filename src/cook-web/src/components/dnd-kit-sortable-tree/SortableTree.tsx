/* eslint-disable @typescript-eslint/no-unused-vars */
'use client'
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Announcements,
  closestCenter,
  defaultDropAnimation,
  DndContext,
  DragEndEvent,
  DragMoveEvent,
  DragOverEvent,
  DragStartEvent,
  DropAnimation,
  Modifier,
  PointerSensor,
  PointerSensorOptions,
  UniqueIdentifier,
  useSensor,
  useSensors
} from '@dnd-kit/core'
import { CSS } from '@dnd-kit/utilities'
import {
  arrayMove,
  SortableContext,
  UseSortableArguments
} from '@dnd-kit/sortable'

import {
  buildTree,
  findItemDeep,
  flattenTree,
  getProjection,
  removeChildrenOf,
  removeItem,
  setProperty
} from './utilities'
import type {
  FlattenedItem,
  ItemChangedReason,
  SensorContext,
  TreeItemComponentType,
  TreeItems
} from './types'
import { SortableTreeItem } from './SortableTreeItem'
import { customListSortingStrategy } from './SortingStrategy'

export type SortableTreeProps<
  TData extends Record<string, any>,
  TElement extends HTMLElement
> = {
  items: TreeItems<TData>
  onItemsChanged(
    items: TreeItems<TData>,
    reason: ItemChangedReason<TData>
  ): void
  TreeItemComponent: TreeItemComponentType<TData, TElement>
  indentationWidth?: number
  indicator?: boolean
  pointerSensorOptions?: PointerSensorOptions
  disableSorting?: boolean
  dropAnimation?: DropAnimation | null
  dndContextProps?: React.ComponentProps<typeof DndContext>
  sortableProps?: Omit<UseSortableArguments, 'id'>
  keepGhostInPlace?: boolean
  canRootHaveChildren?: boolean | ((dragItem: FlattenedItem<TData>) => boolean)
}
const defaultPointerSensorOptions: PointerSensorOptions = {
  activationConstraint: {
    distance: 3
  }
}

export const dropAnimationDefaultConfig: DropAnimation = {
  keyframes ({ transform }) {
    return [
      { opacity: 1, transform: CSS.Transform.toString(transform.initial) },
      {
        opacity: 0,
        transform: CSS.Transform.toString({
          ...transform.final,
          x: transform.final.x + 5,
          y: transform.final.y + 5
        })
      }
    ]
  },
  easing: 'ease-out',
  sideEffects ({ active }) {
    active.node.animate([{ opacity: 0 }, { opacity: 1 }], {
      duration: defaultDropAnimation.duration,
      easing: defaultDropAnimation.easing
    })
  }
}

export function SortableTree<
  TreeItemData extends Record<string, any>,
  TElement extends HTMLElement = HTMLDivElement
> ({
  items,
  indicator,
  indentationWidth = 30,
  onItemsChanged,
  TreeItemComponent,
  pointerSensorOptions,
  disableSorting,
  dropAnimation,
  dndContextProps,
  sortableProps,
  keepGhostInPlace,
  canRootHaveChildren,
  ...rest
}: SortableTreeProps<TreeItemData, TElement>) {
  const [activeId, setActiveId] = useState<UniqueIdentifier | null>(null)
  const [overId, setOverId] = useState<UniqueIdentifier | null>(null)
  const [offsetLeft, setOffsetLeft] = useState(0)
  const [currentPosition, setCurrentPosition] = useState<{
    parentId: UniqueIdentifier | null
    overId: UniqueIdentifier
  } | null>(null)

  const flattenedItems = useMemo(() => {
    const flattenedTree = flattenTree(items)
    const collapsedItems = flattenedTree.reduce<UniqueIdentifier[]>(
      (acc, { children, collapsed, id }) =>
        collapsed && children?.length ? [...acc, id] : acc,
      []
    )

    const result = removeChildrenOf(
      flattenedTree,
      activeId ? [activeId, ...collapsedItems] : collapsedItems
    )
    return result
  }, [activeId, items])
  const projected = getProjection(
    flattenedItems,
    activeId,
    overId,
    offsetLeft,
    indentationWidth,
    keepGhostInPlace ?? false,
    canRootHaveChildren
  )
  const sensorContext: SensorContext<TreeItemData> = useRef({
    items: flattenedItems,
    offset: offsetLeft
  })
  const sensors = useSensors(
    useSensor(
      PointerSensor,
      pointerSensorOptions ?? defaultPointerSensorOptions
    )
  )

  const sortedIds = useMemo(
    () => flattenedItems.map(({ id }) => id),
    [flattenedItems]
  )
  const activeItem = activeId
    ? flattenedItems.find(({ id }) => id === activeId)
    : null

  useEffect(() => {
    sensorContext.current = {
      items: flattenedItems,
      offset: offsetLeft
    }
  }, [flattenedItems, offsetLeft])

  const itemsRef = useRef(items)
  itemsRef.current = items
  const handleRemove = useCallback(
    (id: string) => {
      const item = findItemDeep(itemsRef.current, id)!
      onItemsChanged(removeItem(itemsRef.current, id), {
        type: 'removed',
        item
      })
    },
    [onItemsChanged]
  )

  const handleCollapse = useCallback(
    function handleCollapse (id: string) {
      const item = findItemDeep(itemsRef.current, id)!
      onItemsChanged(
        setProperty(itemsRef.current, id, 'collapsed', ((value: boolean) => {
          return !value
        }) as any),
        {
          type: item.collapsed ? 'collapsed' : 'expanded',
          item: item
        }
      )
    },
    [onItemsChanged]
  )

  const announcements: Announcements = useMemo(
    () => ({
      onDragStart ({ active }) {
        return `Picked up ${active.id}.`
      },
      onDragMove ({ active, over }) {
        return getMovementAnnouncement('onDragMove', active.id, over?.id)
      },
      onDragOver ({ active, over }) {
        return getMovementAnnouncement('onDragOver', active.id, over?.id)
      },
      onDragEnd ({ active, over }) {
        return getMovementAnnouncement('onDragEnd', active.id, over?.id)
      },
      onDragCancel ({ active }) {
        return `Moving was cancelled. ${active.id} was dropped in its original position.`
      }
    }),
    []
  )

  const strategyCallback = useCallback(() => {
    return !!projected
  }, [projected])
  return (
    <DndContext
      accessibility={{ announcements }}
      sensors={disableSorting ? undefined : sensors}
      modifiers={indicator ? modifiersArray : undefined}
      collisionDetection={closestCenter}
      onDragStart={disableSorting ? undefined : handleDragStart}
      onDragMove={disableSorting ? undefined : handleDragMove}
      onDragOver={disableSorting ? undefined : handleDragOver}
      onDragEnd={disableSorting ? undefined : handleDragEnd}
      onDragCancel={disableSorting ? undefined : handleDragCancel}
      {...dndContextProps}
    >
      <SortableContext
        items={sortedIds}
        strategy={
          disableSorting
            ? undefined
            : customListSortingStrategy(strategyCallback)
        }
      >
        {flattenedItems.map(item => {
          return (
            <SortableTreeItem
              {...rest}
              key={item.id}
              id={item.id as any}
              item={item}
              childCount={item.children?.length}
              depth={
                item.id === activeId && projected && !keepGhostInPlace
                  ? projected?.depth
                  : item?.depth
              }
              indentationWidth={indentationWidth}
              indicator={indicator}
              collapsed={Boolean(item.collapsed && item.children?.length)}
              onCollapse={item.children?.length ? handleCollapse : undefined}
              onRemove={handleRemove}
              isLast={
                item.id === activeId && projected
                  ? projected.isLast
                  : item.isLast
              }
              parent={
                item.id === activeId && projected
                  ? projected.parent
                  : item.parent
              }
              TreeItemComponent={TreeItemComponent}
              disableSorting={disableSorting}
              sortableProps={sortableProps}
              keepGhostInPlace={keepGhostInPlace}
            />
          )
        })}
      </SortableContext>
    </DndContext>
  )

  function handleDragStart ({ active: { id: activeId } }: DragStartEvent) {
    setActiveId(activeId)
    setOverId(activeId)

    const activeItem = flattenedItems.find(({ id }) => id === activeId)

    if (activeItem) {
      setCurrentPosition({
        parentId: activeItem.parentId,
        overId: activeId
      })
    }

    document.body.style.setProperty('cursor', 'grabbing')
  }

  function handleDragMove ({ delta }: DragMoveEvent) {
    setOffsetLeft(delta.x)
  }

  function handleDragOver ({ over }: DragOverEvent) {
    setOverId(over?.id ?? null)
  }

  function handleDragEnd ({ active, over, delta }: DragEndEvent) {
    resetState()

    if (projected && over) {
      // const { depth, parentId } = projected
      if (keepGhostInPlace && over.id === active.id) return
      const clonedItems: FlattenedItem<TreeItemData>[] = flattenTree(items)
      const overIndex = clonedItems.findIndex(({ id }) => id === over.id)
      const activeIndex = clonedItems.findIndex(({ id }) => id === active.id)
      const activeTreeItem = clonedItems[activeIndex]

      let droppedToParent
      droppedToParent = !activeTreeItem.parent
        ? null
        : clonedItems.find(({ id }) => id === over.id)
      if (droppedToParent?.parentId) {
        droppedToParent = clonedItems.find(
          ({ id }) => id === droppedToParent?.parentId
        )
      }
      if (
        delta.y < 0 &&
        overIndex > 0 &&
        droppedToParent?.id === activeTreeItem?.parentId
      ) {
        const prevItem = clonedItems[overIndex - 1]
        droppedToParent = prevItem.parent
          ? clonedItems.find(({ id }) => id === prevItem.parentId)
          : prevItem
      }

      if (droppedToParent?.id === activeTreeItem.id) {
        droppedToParent = null
      }
      const draggedFromParent = activeTreeItem.parent
      const sortedItems = arrayMove(clonedItems, activeIndex, overIndex)
      if (droppedToParent?.id) {
        sortedItems[overIndex] = {
          ...sortedItems[overIndex],
          parentId: droppedToParent.id,
          parent: droppedToParent
        }
      }else{
        sortedItems[overIndex] = {
         ...sortedItems[overIndex],
          parentId: null,
          parent: null
        }
      }
      const newItems = buildTree(sortedItems)
      const newActiveItem = sortedItems.find(x => x.id === active.id)!
      // const currentParent = newActiveItem.parentId
      //   ? sortedItems.find((x) => x.id === newActiveItem.parentId)!
      //   : null;

      // removing setTimeout leads to an unwanted scrolling
      // Use case:
      //   There are a lot of items in a tree (so that the scroll exists).
      //   You take the node from the bottom and move it to the top
      //   Without `setTimeout` when you drop the node the list gets scrolled to the bottom.
      setTimeout(() =>
        onItemsChanged(newItems, {
          type: 'dropped',
          draggedItem: newActiveItem,
          draggedFromParent: draggedFromParent,
          droppedToParent: droppedToParent || null
        })
      )
    }
  }

  function handleDragCancel () {
    resetState()
  }

  function resetState () {
    setOverId(null)
    setActiveId(null)
    setOffsetLeft(0)
    setCurrentPosition(null)

    document.body.style.setProperty('cursor', '')
  }

  function getMovementAnnouncement (
    eventName: string,
    activeId: UniqueIdentifier,
    overId?: UniqueIdentifier
  ) {
    if (overId && projected) {
      if (eventName !== 'onDragEnd') {
        if (
          currentPosition &&
          projected.parentId === currentPosition.parentId &&
          overId === currentPosition.overId
        ) {
          return
        } else {
          setCurrentPosition({
            parentId: projected.parentId,
            overId
          })
        }
      }

      const clonedItems: FlattenedItem<TreeItemData>[] = flattenTree(items)
      const overIndex = clonedItems.findIndex(({ id }) => id === overId)
      const activeIndex = clonedItems.findIndex(({ id }) => id === activeId)
      const sortedItems = arrayMove(clonedItems, activeIndex, overIndex)

      const previousItem = sortedItems[overIndex - 1]

      let announcement
      const movedVerb = eventName === 'onDragEnd' ? 'dropped' : 'moved'
      const nestedVerb = eventName === 'onDragEnd' ? 'dropped' : 'nested'

      if (!previousItem) {
        const nextItem = sortedItems[overIndex + 1]
        announcement = `${activeId} was ${movedVerb} before ${nextItem.id}.`
      } else {
        if (projected?.depth > previousItem?.depth) {
          announcement = `${activeId} was ${nestedVerb} under ${previousItem.id}.`
        } else {
          let previousSibling: FlattenedItem<TreeItemData> | undefined =
            previousItem
          while (previousSibling && projected?.depth < previousSibling?.depth) {
            const parentId: UniqueIdentifier | null = previousSibling.parentId
            previousSibling = sortedItems.find(({ id }) => id === parentId)
          }

          if (previousSibling) {
            announcement = `${activeId} was ${movedVerb} after ${previousSibling.id}.`
          }
        }
      }

      return announcement
    }

    return
  }
}

const adjustTranslate: Modifier = ({ transform }) => {
  return {
    ...transform,
    y: transform.y - 25
  }
}
const modifiersArray = [adjustTranslate]
