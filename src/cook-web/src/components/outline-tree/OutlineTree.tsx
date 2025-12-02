'use client';
import {
  SortableTree,
  SimpleTreeItemWrapper,
  TreeItemComponentProps,
  TreeItems,
} from '../dnd-kit-sortable-tree';
import React, { useMemo, useState } from 'react';
import { Outline } from '@/types/shifu';
import { cn } from '@/lib/utils';
import {
  Trash2,
  Edit,
  SlidersHorizontal,
  MoreVertical,
} from 'lucide-react';
import { InlineInput } from '../inline-input';
import { useShifu } from '@/store/useShifu';
import Loading from '../loading';
import { ItemChangedReason } from '../dnd-kit-sortable-tree/types';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/AlertDialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '../ui/DropdownMenu';
import { Button } from '@/components/ui/Button';
import { useTranslation } from 'react-i18next';
import { useAlert } from '@/components/ui/UseAlert';
import ChapterSettingsDialog, {
  ChapterPromptSetting,
} from '../chapter-setting';
import './OutlineTree.css';

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

CataTree.displayName = 'CataTree';

export type TreeItemProps = {
  currentNode?: Outline;
  onChange?: (node: Outline, value: string) => void;
  onChapterSelect?: () => void;
};

const MinimalTreeItemComponent = React.forwardRef<
  HTMLDivElement,
  TreeItemComponentProps<Outline> & TreeItemProps
>((props, ref) => {
  const { focusId, actions, cataData, currentNode, currentShifu } = useShifu();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [settingsDialogOpen, setSettingsDialogOpen] = useState(false);
  const [chapterSettingsOpen, setChapterSettingsOpen] = useState(false);
  const [addLessonDialogOpen, setAddLessonDialogOpen] = useState(false);
  const { t } = useTranslation();
  const outlineVariant = (props.item?.depth ?? 0) <= 0 ? 'chapter' : 'lesson';
  const alert = useAlert();
  const isChapterNode = (props.item?.depth || 0) === 0;
  const isPlaceholderNode = props.item.id === 'new_chapter';
  const isSelectedChapter =
    isChapterNode && currentNode?.id === props.item.id;
  const shouldHighlight =
    (!isChapterNode && currentNode?.id == props.item.id) || isPlaceholderNode;
  const showChapterMeta = isChapterNode && !isPlaceholderNode;
  const lessonCount = props.item?.children?.length || 0;
  const lessonCountLabel = t('component.outlineTree.lessonCount', {
    count: lessonCount,
  });
  const chapterName = cataData[props.item.id!]?.name || '';
  const onNodeChange = async (value: string) => {
    if (!value || value.trim() === '') {
      alert.showAlert({
        title: t('component.outlineTree.nameRequired'),
        description: '',
        confirmText: t('common.core.confirm'),
        onConfirm() {
          actions.removeOutline({
            parent_bid: props.item.parentId,
            ...props.item,
          });
          actions.setFocusId('');
        },
      });
      return;
    }
    await actions.createOutline({
      shifu_bid: currentShifu?.bid || '',
      id: props.item.id,
      parent_bid: props.item.parent_bid || '',
      bid: props.item.bid,
      name: value,
      children: [],
      position: '',
    });
  };
  const handleChapterSettingsClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSettingsDialogOpen(true);
  };
  const handleAddSectionClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setAddLessonDialogOpen(true);
  };
  const handleConfirmAddLesson = ({
    title,
  }: {
    title: string;
  }) => {
    onAddNodeClick(props.item, title);
    setAddLessonDialogOpen(false);
  };
  const onAddNodeClick = (node: Outline, name = '') => {
    if (node.depth && node.depth >= 1) {
      actions.addSiblingOutline(node, name);
    } else {
      actions.addSubOutline(node, name);
    }
  };
  const removeNode = async e => {
    e.stopPropagation();
    setShowDeleteDialog(true);
  };
  const editNode = e => {
    e.stopPropagation();
    actions.setFocusId(props.item.id || '');
  };
  const onSelect = async () => {
    if (props.item.id == 'new_chapter') {
      return;
    }

    if (currentNode?.id === props.item.id) {
      return;
    }

    if (props.item.depth == 0) {
      await actions.setCurrentNode(props.item);
      actions.setBlocks([]);
      props.onChapterSelect?.();
      return;
    }

    // Flush pending autosave with the latest snapshot before switching
    actions.flushAutoSaveBlocks();

    await actions.setCurrentNode(props.item);
    await actions.loadMdflow(props.item.bid || '', currentShifu?.bid || '');
    // await actions.loadBlocks(props.item.bid || '', currentShifu?.bid || '');
  };

  const handleConfirmDelete = async () => {
    await actions.removeOutline({
      ...props.item,
      parent_bid: props.item.parentId,
    });
    setShowDeleteDialog(false);
  };

  return (
    <>
      <SimpleTreeItemWrapper
        {...props}
        ref={ref}
        disableCollapseOnItemClick={false}
        chapterMeta={
          showChapterMeta
            ? {
                label: lessonCountLabel,
                onSettingsClick: handleChapterSettingsClick,
                onAddClick: handleAddSectionClick,
              }
            : undefined
        }
      >
        <div
          id={props.item.id}
          className={cn(
            'outline-tree_node flex items-center flex-1 justify-between w-full group p-2 rounded-md',
            (props.item?.children?.length || 0) > 0 ? 'pl-0' : 'pl-10',
            shouldHighlight ? 'bg-gray-200' : '',
            // isSelectedChapter ? 'select' : '',
          )}
          onClick={onSelect}
        >
          <span
            className='outline-tree_title flex flex-row items-center flex-1 min-w-0'
            title={chapterName}
          >
            {chapterName}
          </span>
        </div>
      </SimpleTreeItemWrapper>
      <ChapterSettingsDialog
        outlineBid={props.item.bid}
        open={settingsDialogOpen}
        onOpenChange={setSettingsDialogOpen}
        variant={outlineVariant}
      />
      {outlineVariant === 'chapter' && props.item.id !== 'new_chapter' && (
        <ChapterPromptSetting
          outlineBid={props.item.bid}
          open={chapterSettingsOpen}
          onOpenChange={setChapterSettingsOpen}
        />
      )}
      {showChapterMeta && (
        <ChapterSettingsDialog
          outlineBid=''
          open={addLessonDialogOpen}
          onOpenChange={setAddLessonDialogOpen}
          variant='lesson'
          footerActionLabel={t('module.chapterSetting.addLesson')}
          onFooterAction={({ title }) =>
            handleConfirmAddLesson({
              title,
            })
          }
        />
      )}
      <AlertDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('component.outlineTree.confirmDelete')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('component.outlineTree.confirmDeleteDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t('component.outlineTree.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction onClick={handleConfirmDelete}>
              {t('component.outlineTree.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
});

MinimalTreeItemComponent.displayName = 'MinimalTreeItemComponent';

export default CataTree;
