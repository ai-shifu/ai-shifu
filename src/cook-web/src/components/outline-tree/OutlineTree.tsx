'use client';
import {
  SortableTree,
  TreeItemComponentProps,
  TreeItems,
} from '../dnd-kit-sortable-tree';
import React, { useMemo } from 'react';
import { Outline } from '@/types/shifu';
import { useShifu } from '@/store/useShifu';
import { ItemChangedReason } from '../dnd-kit-sortable-tree/types';
import './OutlineTree.css';
import MinimalTreeItemComponent from './MinimalTreeItem';

interface ICataTreeProps {
  currentNode?: Outline;
  items: TreeItems<Outline>;
  onChange?: (data: TreeItems<Outline>) => void;
  onAddNodeClick?: (node: Outline) => void;
  onChapterSelect?: () => void;
}

const getReorderOutlineDto = (items: TreeItems<Outline>) => {
  return items.map(item => {
    return {
      bid: item.bid,
      children: getReorderOutlineDto(item?.children || []),
    };
  });
};

export const CataTree = React.memo((props: ICataTreeProps) => {
  const { items, onChange, onChapterSelect } = props;
  const { actions, focusId } = useShifu();
  const TreeItemWithSelect = useMemo(() => {
    const ForwardRefComponent = React.forwardRef<
      HTMLDivElement,
      TreeItemComponentProps<Outline>
    >((minimalProps, ref) => (
      <MinimalTreeItemComponent
        {...minimalProps}
        ref={ref}
        onChapterSelect={onChapterSelect}
      />
    ));
    ForwardRefComponent.displayName = 'TreeItemWithSelect';
    return ForwardRefComponent;
  }, [onChapterSelect]);

  const onItemsChanged = async (
    data: TreeItems<Outline>,
    reason: ItemChangedReason<Outline>,
  ) => {
    if (reason.type == 'dropped') {
      const reorderOutlineDtos = getReorderOutlineDto(data);
      await actions.reorderOutlineTree(reorderOutlineDtos);
    }

    onChange?.(data);
  };

  return (
    <SortableTree
      disableSorting={!!focusId}
      items={items}
      indentationWidth={20}
      onItemsChanged={onItemsChanged}
      TreeItemComponent={TreeItemWithSelect}
      dropAnimation={null}
    />
  );
});

export default CataTree;
CataTree.displayName = 'CataTree';
