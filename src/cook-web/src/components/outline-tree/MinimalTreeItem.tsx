'use client';
import {
  SimpleTreeItemWrapper,
  TreeItemComponentProps,
} from '../dnd-kit-sortable-tree';
import React, { useMemo, useState } from 'react';
import { LessonCreationSettings, Outline } from '@/types/shifu';
import { LearningPermission } from '@/c-api/studyV2';
import guestIcon from '../chapter-setting/icons/svg-guest.svg';
import trialIcon from '../chapter-setting/icons/svg-trial.svg';
import normalIcon from '../chapter-setting/icons/svg-normal.svg';
import hiddenIcon from '../chapter-setting/icons/svg-hidden.svg';
import { cn } from '@/lib/utils';
import { useShifu } from '@/store/useShifu';
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
import { useTranslation } from 'react-i18next';
import { useAlert } from '@/components/ui/UseAlert';
import ChapterSettingsDialog from '../chapter-setting';
import './OutlineTree.css';
import { LEARNING_PERMISSION } from '@/c-api/studyV2';

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
  const [settingsDialogOpen, setSettingsDialogOpen] = useState(false);
  const [addLessonDialogOpen, setAddLessonDialogOpen] = useState(false);
  const { t } = useTranslation();
  const outlineVariant = (props.item?.depth ?? 0) <= 0 ? 'chapter' : 'lesson';
  const alert = useAlert();
  const isChapterNode = (props.item?.depth || 0) === 0;
  const isPlaceholderNode = props.item.id === 'new_chapter';
  const shouldHighlight =
    (!isChapterNode && currentNode?.id == props.item.id) || isPlaceholderNode;
  const showChapter = isChapterNode && !isPlaceholderNode;
  const showLessonSettings = !isChapterNode && !isPlaceholderNode;
  const lessonCount = props.item?.children?.length || 0;
  const lessonCountLabel = t('component.outlineTree.lessonCount', {
    count: lessonCount,
  });
  const lesson = cataData[props.item.id!] || props.item;
  const chapterName = lesson?.name || '';
  const shouldShowMeta = showChapter || showLessonSettings;
  const renderLessonBadges = () => {
    if (isChapterNode) {
      return null;
    }
    const badges: Array<{ icon: string; label: string; className?: string }> = [];
    const lessonType = lesson?.type as LearningPermission | undefined;
    const lessonHidden = lesson?.is_hidden;
    if (lessonType === LEARNING_PERMISSION.GUEST) {
      badges.push({
        icon: guestIcon.src,
        label: t('module.chapterSetting.guest'),
        className: 'opacity-50'
      });
    } else if (lessonType === LEARNING_PERMISSION.TRIAL) {
      badges.push({
        icon: trialIcon.src,
        label: t('module.chapterSetting.free'),
        className: 'opacity-50'
      });
    } else if (lessonType === LEARNING_PERMISSION.NORMAL) {
      badges.push({
        icon: normalIcon.src,
        label: t('module.chapterSetting.paid'),
        className: 'opacity-50'
      });
    }
    if (lessonHidden) {
      badges.push({
        icon: hiddenIcon.src,
        label: t('module.chapterSetting.hidden'),
      });
    }
    if (!badges.length) {
      return null;
    }
    return badges.map(({ icon, label, className = '' }) => (
      <span className={cn('outline-tree_badge', className)} key={label} title={label}>
        <img src={icon} alt={label} />
      </span>
    ));
  };
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
  const handleSettingsDeleteRequest = () => {
    setSettingsDialogOpen(false);
    setShowDeleteDialog(true);
  };
  const handleSettingsChange = ({
    name,
    isHidden,
    learningPermission,
  }: {
    name: string;
    isHidden: boolean;
    learningPermission: LearningPermission;
  }) => {
    if (!props.item.id) {
      return;
    }
    const current = lesson || props.item;
    const updatedOutline: Outline = {
      ...current,
      name,
      is_hidden: isHidden,
      type: learningPermission,
    };
    actions.updateOutline(props.item.id, updatedOutline);
    // props.onChange?.(updatedOutline);
  };
  const handleConfirmAddLesson = async (settings: LessonCreationSettings) => {
    try {
      await onAddNodeClick(props.item, settings);
      setAddLessonDialogOpen(false);
    } catch (error) {
      console.error(error);
    }
  };
  const onAddNodeClick = async (
    node: Outline,
    settings: LessonCreationSettings,
  ) => {
    if (node.depth && node.depth >= 1) {
      await actions.addSiblingOutline(node, settings);
    } else {
      await actions.addSubOutline(node, settings);
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
        className={cn(
          shouldHighlight && !isChapterNode && 'select',
        )}
        chapter={
          shouldShowMeta
            ? {
                label: showChapter ? lessonCountLabel : undefined,
                onSettingsClick: handleChapterSettingsClick,
                onAddClick: showChapter ? handleAddSectionClick : undefined,
                showAdd: showChapter,
              }
            : undefined
        }
      >
        <div
          id={props.item.id}
          className={cn(
            'outline-tree_node flex items-center flex-1 justify-between w-full group p-2 rounded-md',
            isChapterNode ? 'pl-0' : 'pl-2',
            shouldHighlight ? 'bg-gray-200' : '',
          )}
          onClick={onSelect}
        >
          <div className='flex flex-row items-center flex-1 min-w-0 gap-2'>
            <span
              className='outline-tree_title flex flex-row items-center flex-1 min-w-0'
              title={chapterName}
            >
              {chapterName}
            </span>
            {!isChapterNode && (
              <div className='outline-tree_badges flex items-center gap-2'>
                {renderLessonBadges()}
              </div>
            )}
          </div>
        </div>
      </SimpleTreeItemWrapper>
      {/* edit lesson settings dialog */}
      <ChapterSettingsDialog
        outlineBid={props.item.bid}
        open={settingsDialogOpen}
        onOpenChange={setSettingsDialogOpen}
        variant={outlineVariant}
        onDeleteRequest={handleSettingsDeleteRequest}
        deleteButtonLabel={t('component.outlineTree.delete')}
        onChange={handleSettingsChange}
      />
      {/* add lesson dialog */}
      {showChapter && (
        <ChapterSettingsDialog
          outlineBid=''
          open={addLessonDialogOpen}
          onOpenChange={setAddLessonDialogOpen}
          variant='lesson'
          footerActionLabel={t('module.chapterSetting.addLesson')}
          onFooterAction={handleConfirmAddLesson}
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

export default MinimalTreeItemComponent;