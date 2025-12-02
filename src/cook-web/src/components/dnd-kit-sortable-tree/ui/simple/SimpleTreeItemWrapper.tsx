/* eslint-disable react/display-name */
/* eslint-disable @typescript-eslint/no-empty-object-type */
/* eslint-disable @typescript-eslint/no-unused-vars */
import clsx from 'clsx';
import { ChevronDown, ChevronRight, Plus, Settings } from 'lucide-react';
import React, { forwardRef } from 'react';
import type { TreeItemComponentProps } from '../../types';
import './SimpleTreeItemWrapper.css';

interface SimpleTreeItemWrapperProps<T = {}> extends TreeItemComponentProps<T> {
  onChapterSelect?: () => void;
  chapterMeta?: {
    label: string;
    onSettingsClick?: React.MouseEventHandler<HTMLButtonElement>;
    onAddClick?: React.MouseEventHandler<HTMLButtonElement>;
  };
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
    chapterMeta,
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
        className={clsx(
          'dnd-sortable-tree_simple_tree-item group',
          contentClassName,
        )}
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
        {chapterMeta && (
          <div className='outline-tree_actions ml-2'>
            <span className='outline-tree_section-count group-hover:hidden'>
              {chapterMeta.label}
            </span>
            <div className='outline-tree_action-buttons hidden group-hover:flex'>
              <button
                type='button'
                className='outline-tree_action-button mr-1'
                onClick={chapterMeta.onSettingsClick}
                aria-label='chapter-settings'
              >
                <Settings size={16} />
              </button>
              <button
                type='button'
                className='outline-tree_action-button'
                onClick={chapterMeta.onAddClick}
                aria-label='chapter-add-section'
              >
                <Plus size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </li>
  );
}) as <T>(
  p: React.PropsWithChildren<
    SimpleTreeItemWrapperProps<T> & React.RefAttributes<HTMLDivElement>
  >,
) => React.ReactElement;
