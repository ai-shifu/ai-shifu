import React, { useCallback, useEffect, useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { RadioGroup, RadioGroupItem } from '@/components/ui/RadioGroup';
import { Label } from '@/components/ui/Label';
import { Textarea } from '@/components/ui/Textarea';
import api from '@/api';
import { LEARNING_PERMISSION, LearningPermission } from '@/c-api/studyV2';
import Loading from '../loading';
import { useTranslation } from 'react-i18next';
import { useShifu } from '@/store';
import { useTracking } from '@/c-common/hooks/useTracking';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { TITLE_MAX_LENGTH } from '@/c-constants/uiConstants';

type ChapterSettingsDialogProps = {
  outlineBid?: string;
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  variant?: 'chapter' | 'lesson';
  footerActionLabel?: string;
  onFooterAction?: (data: {
    learningPermission: LearningPermission;
    isHidden: boolean;
    systemPrompt: string;
    name: string;
  }) => void;
  onDeleteRequest?: () => void;
  deleteButtonLabel?: string;
};

const ChapterSettingsDialog = ({
  outlineBid,
  open,
  onOpenChange,
  variant = 'lesson',
  footerActionLabel,
  onFooterAction,
  onDeleteRequest,
  deleteButtonLabel,
}: ChapterSettingsDialogProps) => {
  const isChapter = variant === 'chapter';
  const isLesson = !isChapter;
  const { currentShifu } = useShifu();
  const { trackEvent } = useTracking();
  const { t } = useTranslation();
  const [learningPermission, setLearningPermission] =
    useState<LearningPermission>(LEARNING_PERMISSION.NORMAL);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [hideChapter, setHideChapter] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [title, setTitle] = useState('');

  const fetchOutlineInfo = useCallback(async () => {
    if (!outlineBid) {
      setLearningPermission(LEARNING_PERMISSION.NORMAL);
      setSystemPrompt('');
      setHideChapter(false);
      setIsDirty(false);
      setTitle('');
      return;
    }
    setLoading(true);
    try {
      const result = await api.getOutlineInfo({
        outline_bid: outlineBid,
        shifu_bid: currentShifu?.bid,
      });
      if (!result) {
        return;
      }

      setLearningPermission(result.type || LEARNING_PERMISSION.NORMAL);
      setSystemPrompt(result.system_prompt ?? '');
      const normalizedHidden = result.is_hidden ?? false;
      setHideChapter(normalizedHidden);
      setIsDirty(false);
      setTitle(result.name ?? '');
    } finally {
      setLoading(false);
    }
  }, [outlineBid, currentShifu?.bid]);

  const onConfirm = useCallback(
    async (needClose = true, saveType: 'auto' | 'manual' = 'manual') => {
      try {
        if (currentShifu?.readonly) {
          onOpenChange?.(false);
          return;
        }
        if (!outlineBid) {
          if (needClose) {
            onOpenChange?.(false);
          }
          return;
        }

        const trimmedTitle = title.trim();
        if (!trimmedTitle) {
          return;
        }

        const payload: Record<string, unknown> = {
          outline_bid: outlineBid,
          shifu_bid: currentShifu?.bid,
          system_prompt: systemPrompt,
          name: trimmedTitle,
          description: trimmedTitle,
        };
        let eventName: 'creator_outline_setting_save' | 'creator_outline_prompt_save' =
          'creator_outline_setting_save';

        if (isLesson) {
          const isPaid = learningPermission === LEARNING_PERMISSION.NORMAL;
          const requiresLogin =
            learningPermission !== LEARNING_PERMISSION.GUEST;
          Object.assign(payload, {
            type: learningPermission,
            is_hidden: hideChapter,
            is_paid: isPaid,
            require_login: requiresLogin,
            need_login: requiresLogin,
            login_required: requiresLogin,
          });
        } else {
          eventName = 'creator_outline_prompt_save';
        }

        await api.modifyOutline(payload);

        if (isLesson) {
          trackEvent(eventName, {
            outline_bid: outlineBid,
            shifu_bid: currentShifu?.bid,
            save_type: saveType,
            variant,
            learning_permission: learningPermission,
            hide_chapter: hideChapter,
            system_prompt: systemPrompt,
          });
        } else {
          trackEvent(eventName, {
            outline_bid: outlineBid,
            shifu_bid: currentShifu?.bid,
            system_prompt: systemPrompt,
            save_type: saveType,
          });
        }
        setIsDirty(false);
        if (needClose) {
          onOpenChange?.(false);
        }
      } catch {}
    },
    [
      outlineBid,
      learningPermission,
      hideChapter,
      systemPrompt,
      currentShifu?.bid,
      onOpenChange,
      currentShifu?.readonly,
      trackEvent,
      isLesson,
      variant,
      title,
    ],
  );

  useEffect(() => {
    if (!open) {
      setIsDirty(false);
    } else {
      fetchOutlineInfo();
    }
    onOpenChange?.(open);
  }, [open, outlineBid, onOpenChange, fetchOutlineInfo]);

  useEffect(() => {
    if (!open || loading || !isDirty) {
      return;
    }
    if (currentShifu?.readonly) {
      return;
    }
    const timer = setTimeout(() => {
      onConfirm(false, 'auto');
    }, 3000);

    return () => clearTimeout(timer);
  }, [
    open,
    loading,
    isDirty,
    learningPermission,
    hideChapter,
    systemPrompt,
    onConfirm,
    currentShifu?.readonly,
    title,
  ]);

  return (
    <Sheet
      open={open}
      onOpenChange={newOpen => {
        onOpenChange?.(newOpen);
      }}
    >
      <SheetContent
        side='right'
        className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[360px] md:w-[420px] lg:w-[480px]'
        onInteractOutside={() => {
          onConfirm(true, 'manual');
        }}
        onCloseIconClick={() => {
          onConfirm(true, 'manual');
        }}
      >
        <div className='border-b border-border px-6 py-5 pr-12'>
          <SheetHeader className='space-y-1 text-left'>
            <SheetTitle className='text-lg font-medium text-foreground'>
              {isChapter
                ? t('module.chapterSetting.chapterSettingsTitle')
                : t('module.chapterSetting.lessonSettingsTitle')}
            </SheetTitle>
          </SheetHeader>
        </div>
        {loading ? (
          <div className='flex flex-1 items-center justify-center'>
            <Loading />
          </div>
        ) : (
          <div className='flex-1 overflow-y-auto px-6 py-6'>
            <div className='space-y-8'>
              <div className='space-y-2'>
                <div className='text-sm font-medium text-foreground'>
                  {isChapter
                    ? t('module.chapterSetting.chapterName')
                    : t('module.chapterSetting.lessonName')}
                </div>
                <Input
                  value={title}
                  maxLength={TITLE_MAX_LENGTH}
                  placeholder={
                    isChapter
                      ? t('module.chapterSetting.chapterNamePlaceholder')
                      : t('module.chapterSetting.lessonNamePlaceholder')
                  }
                  disabled={currentShifu?.readonly}
                  onChange={event => {
                    setTitle(event.target.value);
                    setIsDirty(true);
                  }}
                />
              </div>
              {isLesson && (
                <div className='space-y-3'>
                  <div className='text-sm font-medium text-foreground'>
                    {t('module.chapterSetting.learningPermission')}
                  </div>
                  <RadioGroup
                    disabled={currentShifu?.readonly}
                    value={learningPermission}
                    onValueChange={value => {
                      setLearningPermission(value as LearningPermission);
                      setIsDirty(true);
                    }}
                    className='flex flex-row flex-wrap gap-x-10 gap-y-2'
                  >
                    <div className='flex items-center gap-2'>
                      <RadioGroupItem
                        value={LEARNING_PERMISSION.GUEST}
                        id='chapter-guest'
                      />
                      <Label
                        htmlFor='chapter-guest'
                        className='text-sm font-normal text-foreground'
                      >
                        {t('module.chapterSetting.guest')}
                      </Label>
                    </div>
                    <div className='flex items-center gap-2'>
                      <RadioGroupItem
                        value={LEARNING_PERMISSION.TRIAL}
                        id='chapter-trial'
                      />
                      <Label
                        htmlFor='chapter-trial'
                        className='text-sm font-normal text-foreground'
                      >
                        {t('module.chapterSetting.free')}
                      </Label>
                    </div>
                    <div className='flex items-center gap-2'>
                      <RadioGroupItem
                        value={LEARNING_PERMISSION.NORMAL}
                        id='chapter-normal'
                      />
                      <Label
                        htmlFor='chapter-normal'
                        className='text-sm font-normal text-foreground'
                      >
                        {t('module.chapterSetting.paid')}
                      </Label>
                    </div>
                  </RadioGroup>
                </div>
              )}

              {isLesson && (
                <div className='space-y-3'>
                  <div className='text-sm font-medium text-foreground'>
                    {t('module.chapterSetting.isHidden')}
                  </div>
                  <RadioGroup
                    disabled={currentShifu?.readonly}
                    value={hideChapter ? 'hidden' : 'visible'}
                    onValueChange={value => {
                      setHideChapter(value === 'hidden');
                      setIsDirty(true);
                    }}
                    className='flex flex-row flex-wrap gap-x-10 gap-y-2'
                  >
                    <div className='flex items-center gap-2'>
                      <RadioGroupItem
                        value='visible'
                        id='chapter-visible'
                      />
                      <Label
                        htmlFor='chapter-visible'
                        className='text-sm font-normal text-foreground'
                      >
                        {t('module.chapterSetting.visible')}
                      </Label>
                    </div>
                    <div className='flex items-center gap-2'>
                      <RadioGroupItem
                        value='hidden'
                        id='chapter-hidden'
                      />
                      <Label
                        htmlFor='chapter-hidden'
                        className='text-sm font-normal text-foreground'
                      >
                        {t('module.chapterSetting.hidden')}
                      </Label>
                    </div>
                  </RadioGroup>
                </div>
              )}

              <div className='space-y-2'>
                <div className='text-sm font-medium text-foreground'>
                  {isChapter
                    ? t('module.chapterSetting.chapterPrompt')
                    : t('module.chapterSetting.lessonPrompt')}
                </div>
                <div className='text-xs text-muted-foreground'>
                  {isChapter
                    ? t('module.chapterSetting.chapterPromptHint')
                    : t('module.chapterSetting.lessonPromptHint')}
                </div>
                <Textarea
                  value={systemPrompt}
                  onChange={event => {
                    setSystemPrompt(event.target.value);
                    setIsDirty(true);
                  }}
                  disabled={currentShifu?.readonly}
                  maxLength={20000}
                  minRows={3}
                  maxRows={30}
                  placeholder={
                    isChapter
                      ? t('module.chapterSetting.promptPlaceholder')
                      : t('module.chapterSetting.lessonPromptPlaceholder')
                  }
                  className='min-h-[220px]'
                />
                {/* <div className='text-xs text-muted-foreground text-right'>
                  {systemPrompt.length}/10000
                </div> */}
              </div>
            </div>
          </div>
        )}
        {(footerActionLabel && onFooterAction) || onDeleteRequest ? (
          <div className='border-t border-border px-6 py-4 flex justify-end gap-3'>
            {onDeleteRequest && outlineBid && (
              <Button
                type='button'
                variant='outline'
                className='text-red-500 border-red-500 hover:bg-red-50'
                onClick={onDeleteRequest}
                disabled={currentShifu?.readonly}
              >
                {deleteButtonLabel ?? t('component.outlineTree.delete')}
              </Button>
            )}
            {footerActionLabel && onFooterAction && (
              <Button
                type='button'
                onClick={() =>
                  onFooterAction({
                    learningPermission,
                    isHidden: hideChapter,
                    systemPrompt,
                    name: title.trim(),
                  })
                }
                disabled={currentShifu?.readonly || !title.trim()}
              >
                {footerActionLabel}
              </Button>
            )}
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
};

export default ChapterSettingsDialog;
