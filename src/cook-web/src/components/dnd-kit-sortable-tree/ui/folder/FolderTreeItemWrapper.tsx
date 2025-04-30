/* eslint-disable react/display-name */
/* eslint-disable @typescript-eslint/no-empty-object-type */
/* eslint-disable @typescript-eslint/no-unused-vars */
import clsx from 'clsx';
import React, { forwardRef } from 'react';
import type { TreeItemComponentProps, FlattenedItem } from '../../types';
import './FolderTreeItemWrapper.css';

function flattenParents<T>(
  parent: FlattenedItem<T> | null,
): FlattenedItem<T>[] {
  if (!parent) return [];
  return [...flattenParents(parent.parent), parent];
}

export const FolderTreeItemWrapper = forwardRef<
  HTMLDivElement,
  React.PropsWithChildren<TreeItemComponentProps<{}>>
>((props, ref) => {
  const {
    clone,
    depth,
    disableSelection,
    disableInteraction,
    disableSorting,
    ghost,
    handleProps,
    indentationWidth,
    indicator,
    collapsed,
    onCollapse,
    onRemove,
    item,
    wrapperRef,
    style,
    isLast,
    parent,
    hideCollapseButton,
    childCount,
    manualDrag,
    showDragHandle,
    disableCollapseOnItemClick,
    className,
    contentClassName,
    isOver,
    isOverParent,
    ...rest
  } = props;

  const flattenedParents = flattenParents(parent);
  return (
    <li
      {...rest}
      className={clsx(
        'dnd-sortable-tree_folder_wrapper',
        clone && 'dnd-sortable-tree_folder_clone',
        ghost && 'dnd-sortable-tree_folder_ghost',
        disableSelection && 'dnd-sortable-tree_folder_disable-selection',
        disableInteraction && 'dnd-sortable-tree_folder_disable-interaction',
        className,
      )}
      ref={wrapperRef}
      style={style}
    >
      {flattenedParents.map((item) => (
        <div
          key={item.id}
          className={
            item.isLast
              ? 'dnd-sortable-tree_folder_line-last'
              : 'dnd-sortable-tree_folder_line'
          }
        />
      ))}
      <div
        className={
          isLast
            ? 'dnd-sortable-tree_folder_line-to_self-last'
            : 'dnd-sortable-tree_folder_line-to_self'
        }
      />
      {manualDrag && showDragHandle && !disableSorting && (
        <div className={'dnd-sortable-tree_folder_handle'} {...handleProps} />
      )}
      {!manualDrag && !hideCollapseButton && !!onCollapse && !!childCount && (
        <button
          onClick={(e) => {
            e.preventDefault();
            onCollapse?.();
          }}
          className={clsx(
            'dnd-sortable-tree_folder_tree-item-collapse_button',
            collapsed &&
              'dnd-sortable-tree_folder_tree-item-collapse_button-collapsed',
          )}
        />
      )}
      <div
        className={clsx('dnd-sortable-tree_folder_tree-item', contentClassName)}
        ref={ref}
        {...(manualDrag ? undefined : handleProps)}
        onClick={disableCollapseOnItemClick ? undefined : onCollapse}
      >
        {props.children}
      </div>
    </li>
  );
}) as <T>(
  p: React.PropsWithChildren<
    TreeItemComponentProps<T> & React.RefAttributes<HTMLDivElement>
  >,
) => React.ReactElement;
