'use client';
import {
  SimpleTreeItemWrapper,
  TreeItemComponentProps,
} from '../dnd-kit-sortable-tree';
import React, { useEffect, useState } from 'react';
import { LessonCreationSettings, Outline } from '@/types/shifu';
import { LearningPermission } from '@/c-api/studyV2';
import guestIcon from '../chapter-setting/icons/svg-guest.svg';
import trialIcon from '../chapter-setting/icons/svg-trial.svg';
import normalIcon from '../chapter-setting/icons/svg-normal.svg';
import hiddenIcon from '../chapter-setting/icons/svg-hidden.svg';
import { cn } from '@/lib/utils';
import { useShifu } from '@/store/useShifu';
import { Loader2 } from 'lucide-react';
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
import ChapterSettingsDialog from '../chapter-setting';
import './OutlineTree.css';
import { LEARNING_PERMISSION } from '@/c-api/studyV2';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Input } from '../ui/Input';

export type TreeItemProps = {
  currentNode?: Outline;
  onChange?: (node: Outline, value: string) => void;
  onChapterSelect?: () => void;
};

const MinimalTreeItemComponent = React.forwardRef<
  HTMLDivElement,
  TreeItemComponentProps<Outline> & TreeItemProps
>((props, ref) => {
  const { actions, cataData, currentNode, currentShifu } = useShifu();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [settingsDialogOpen, setSettingsDialogOpen] = useState(false);
  const [addLessonDialogOpen, setAddLessonDialogOpen] = useState(false);
  const { t } = useTranslation();
  const outlineVariant = (props.item?.depth ?? 0) <= 0 ? 'chapter' : 'lesson';
  const isChapterNode = (props.item?.depth || 0) === 0;
  const isPlaceholderNode =
    props.item.id === 'new_chapter' || props.item.id === 'new_lesson';
  const shouldHighlight =
    !isPlaceholderNode && !isChapterNode && currentNode?.id == props.item.id;
  const showChapter = isChapterNode && !isPlaceholderNode;
  const showLessonSettings = !isChapterNode && !isPlaceholderNode;
  const lesson = cataData[props.item.id!] || props.item;
  const chapterName = lesson?.name || '';
  const shouldShowMeta = showChapter || showLessonSettings;
  const renderLessonBadges = () => {
    if (isChapterNode) {
      return null;
    }
    const badges: Array<{ icon: string; label: string; className?: string }> =
      [];
    const lessonType =
      (lesson?.type as LearningPermission | undefined) ??
      LEARNING_PERMISSION.TRIAL;
    const lessonHidden = !!lesson?.is_hidden;
    if (lessonType === LEARNING_PERMISSION.GUEST) {
      badges.push({
        icon: guestIcon.src,
        label: t('module.chapterSetting.guest'),
        className: 'opacity-50',
      });
    } else if (lessonType === LEARNING_PERMISSION.TRIAL) {
      badges.push({
        icon: trialIcon.src,
        label: t('module.chapterSetting.free'),
        className: 'opacity-50',
      });
    } else if (lessonType === LEARNING_PERMISSION.NORMAL) {
      badges.push({
        icon: normalIcon.src,
        label: t('module.chapterSetting.paid'),
        className: 'opacity-50',
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
    return (
      <TooltipProvider delayDuration={200}>
        {badges.map(({ icon, label, className = '' }) => (
          <Tooltip key={`${label}-${icon}`}>
            <TooltipTrigger asChild>
              <span className={cn('outline-tree_badge ml-1', className)}>
                <img
                  src={icon}
                  alt={label}
                />
              </span>
            </TooltipTrigger>
            <TooltipContent
              side='top'
              className='bg-[#0A0A0A] text-white border-transparent text-xs'
            >
              {label}
            </TooltipContent>
          </Tooltip>
        ))}
      </TooltipProvider>
    );
  };

  const [inputValue, setInputValue] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const placeholderText = isChapterNode
    ? t('module.chapterSetting.chapterNamePlaceholder')
    : t('module.chapterSetting.lessonNamePlaceholder');
  const placeholderParentKey =
    (props.parent?.id as string) ||
    (props.item.parentId as string) ||
    (props.item.parent_bid as string) ||
    '';

  useEffect(() => {
    if (isPlaceholderNode) {
      // Reset placeholder input when switching target chapter
      setInputValue('');
    }
  }, [isPlaceholderNode, placeholderParentKey]);

  const handleChapterSettingsClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSettingsDialogOpen(true);
  };
  const handleAddSectionClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    actions.insertPlaceholderLesson(props.item);
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
  const flushCurrentLessonSnapshot = () => {
    if (!currentShifu?.bid || !currentNode?.bid || currentNode.depth === 0) {
      return;
    }
    const latestMdflow = actions?.getCurrentMdflow?.() || '';
    if (!actions.hasUnsavedMdflow(currentNode.bid, latestMdflow)) {
      return;
    }
    actions.flushAutoSaveBlocks({
      shifu_bid: currentShifu.bid,
      outline_bid: currentNode.bid,
      data: latestMdflow,
    });
  };

  const onSelect = async (event?: React.MouseEvent<HTMLDivElement>) => {
    if (!isChapterNode) {
      event?.preventDefault();
      event?.stopPropagation();
    }
    if (isPlaceholderNode) {
      return;
    }

    if (currentNode?.id === props.item.id) {
      return;
    }
    
    flushCurrentLessonSnapshot();

    if (props.item.depth == 0) {
      await actions.setCurrentNode(props.item);
      actions.setBlocks([]);
      props.onChapterSelect?.();
      return;
    }

    await actions.setCurrentNode(props.item);
    await actions.loadMdflow(props.item.bid || '', currentShifu?.bid || '');
  };

  const handleConfirmDelete = async () => {
    await actions.removeOutline({
      ...props.item,
      parent_bid: props.item.parentId,
    });
    setShowDeleteDialog(false);
  };

  const handleCreate = async () => {
    if (!isPlaceholderNode) return;

    const value = inputValue.trim();
    setInputValue(value);

    if (value === '') {
      actions.removePlaceholderOutline(props.item);
      return;
    }

    setIsSaving(true);

    try {
      await actions.createOutline({
        shifu_bid: currentShifu?.bid || '',
        id: props.item.id,
        parent_bid: props.item.parent_bid || '',
        bid: props.item.bid,
        name: value,
        children: [],
        position: '',
      });

      actions.setFocusId('');
    } catch (e) {
      console.error(e);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
      <SimpleTreeItemWrapper
        {...props}
        readonly={currentShifu?.readonly || false}
        ref={ref}
        disableCollapseOnItemClick={!isChapterNode}
        className={cn(shouldHighlight && !isChapterNode && 'select')}
        onItemClick={onSelect}
        chapter={
          shouldShowMeta
            ? {
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
            'outline-tree_node flex items-center flex-1 justify-between w-full group rounded-md min-w-0 ',
            isChapterNode ? 'pl-0' : 'pl-2',
            shouldHighlight ? 'bg-gray-200' : '',
          )}
        >
          <div className='flex flex-row items-center flex-1 min-w-0'>
            {isPlaceholderNode ? (
              <div className='flex items-center w-full'>
                {isSaving ? (
                  <>
                    <span className='outline-none px-2 py-1 mr-1 h-[26px] rounded bg-white text-sm border border-gray-300 w-full text-left flex items-center'>
                      {inputValue || placeholderText}
                    </span>
                    <Loader2 className='animate-spin ml-2 h-4 w-4 text-primary' />
                  </>
                ) : (
                  <Input
                    ref={inputRef}
                    className='outline-none px-2 py-1 mr-1 h-[26px] rounded bg-white text-sm border border-gray-300 w-full'
                    placeholder={placeholderText}
                    autoFocus
                    value={inputValue}
                    onChange={e => setInputValue(e.target.value)}
                    onKeyDown={async e => {
                      if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                        await handleCreate();
                      }
                    }}
                    onBlur={async () => {
                      await handleCreate();
                    }}
                  />
                )}
              </div>
            ) : (
              <>
                <span
                  className='outline-tree_title truncate'
                  title={chapterName}
                >
                  {chapterName}
                </span>

                {!isChapterNode && (
                  <div className='outline-tree_badges flex items-center flex-shrink-0'>
                    {renderLessonBadges()}
                  </div>
                )}
              </>
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
