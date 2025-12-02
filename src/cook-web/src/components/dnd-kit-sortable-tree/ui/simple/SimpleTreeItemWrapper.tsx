/* eslint-disable react/display-name */
/* eslint-disable @typescript-eslint/no-empty-object-type */
/* eslint-disable @typescript-eslint/no-unused-vars */
import clsx from 'clsx';
import { ChevronDown, ChevronRight } from 'lucide-react';
import React, { forwardRef } from 'react';
import type { TreeItemComponentProps } from '../../types';
import './SimpleTreeItemWrapper.css';

interface SimpleTreeItemWrapperProps<T = {}> extends TreeItemComponentProps<T> {
  onChapterSelect?: () => void;
}

export const SimpleTreeItemWrapper = forwardRef<
  HTMLDivElement,
  React.PropsWithChildren<SimpleTreeItemWrapperProps<{}>>
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
    hideCollapseButton,
    childCount,
    manualDrag,
    showDragHandle,
    disableCollapseOnItemClick,
    isLast,
    parent,
    className,
    contentClassName,
    isOver,
    isOverParent,
    onChapterSelect,
    ...rest
  } = props;

  return (
    <li
      ref={wrapperRef}
      {...rest}
      className={clsx(
        'dnd-sortable-tree_simple_wrapper',
        clone && 'dnd-sortable-tree_simple_clone',
        ghost && 'dnd-sortable-tree_simple_ghost',
        disableSelection && 'dnd-sortable-tree_simple_disable-selection',
        disableInteraction && 'dnd-sortable-tree_simple_disable-interaction',
        className,
      )}
      style={{
        ...style,
        // paddingLeft: clone ? indentationWidth : indentationWidth * depth,
      }}
    >
      <div
        className={clsx('dnd-sortable-tree_simple_tree-item', contentClassName)}
        ref={ref}
        {...(manualDrag ? undefined : handleProps)}
        onClick={disableCollapseOnItemClick ? undefined : onCollapse}
      >
        {!disableSorting && showDragHandle !== false && (
          <div
            className={'dnd-sortable-tree_simple_handle'}
            {...handleProps}
          />
        )}
        {!manualDrag && !hideCollapseButton && !!onCollapse && !!childCount && (
          <button
            type="button"
            onClick={e => {
              if (!disableCollapseOnItemClick) {
                return;
              }
              e.preventDefault();
              onCollapse?.();
            }}
            className={clsx(
              'dnd-sortable-tree_simple_tree-item-collapse_button',
            )}
          >
            {collapsed ? (
              <ChevronRight size={16} />
            ) : (
              <ChevronDown size={16} />
            )}
          </button>
        )}
        {props.children}
      </div>
    </li>
  );
}) as <T>(
  p: React.PropsWithChildren<
    SimpleTreeItemWrapperProps<T> & React.RefAttributes<HTMLDivElement>
  >,
) => React.ReactElement;
