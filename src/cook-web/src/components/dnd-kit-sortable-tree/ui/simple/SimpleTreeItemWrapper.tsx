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
  chapter?: {
    label?: string;
    onSettingsClick?: React.MouseEventHandler<HTMLButtonElement>;
    onAddClick?: React.MouseEventHandler<HTMLButtonElement>;
    showAdd?: boolean;
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
    chapter,
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
        {!manualDrag && !hideCollapseButton && !!onCollapse && !!childCount ? (
          <button
            type='button'
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
            {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          </button>
        ) : (
          <div
            className='dnd-sortable-tree_simple_tree-item-collapse_button spacer'
            aria-hidden='true'
          />
        )}
        {props.children}
        {chapter && (
          <div className='outline-tree_actions'>
            {chapter.label ? (
              <span className='outline-tree_section-count group-hover:hidden'>
                {chapter.label}
              </span>
            ) : null}
            <div className='outline-tree_action-buttons hidden group-hover:flex mx-2'>
              {chapter.onSettingsClick && (
                <button
                  type='button'
                  className='outline-tree_action-button mr-1'
                  onClick={chapter.onSettingsClick}
                  aria-label='chapter-settings'
                >
                  <Settings size={16} />
                </button>
              )}
              {chapter.showAdd !== false && chapter.onAddClick && (
                <button
                  type='button'
                  className='outline-tree_action-button'
                  onClick={chapter.onAddClick}
                  aria-label='chapter-add-section'
                >
                  <Plus size={16} />
                </button>
              )}
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
