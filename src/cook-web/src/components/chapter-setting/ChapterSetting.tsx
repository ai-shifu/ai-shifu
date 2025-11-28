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

const ChapterSettingsDialog = ({
  outlineBid,
  open,
  onOpenChange,
  variant = 'lesson',
}: {
  outlineBid: string;
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  variant?: 'chapter' | 'lesson';
}) => {
  const isChapter = variant === 'chapter';
  const { currentShifu } = useShifu();
  const { t } = useTranslation();
  const [learningPermission, setLearningPermission] =
    useState<LearningPermission>(LEARNING_PERMISSION.NORMAL);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [hideChapter, setHideChapter] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isDirty, setIsDirty] = useState(false);

  const fetchOutlineInfo = useCallback(async () => {
    if (!outlineBid) {
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
    } finally {
      setLoading(false);
    }
  }, [outlineBid, currentShifu?.bid]);

  const onConfirm = useCallback(
    async (needClose = true) => {
      try{
        if (!outlineBid) {
          return;
        }
  
        const isPaid = learningPermission === LEARNING_PERMISSION.NORMAL;
        const requiresLogin = learningPermission !== LEARNING_PERMISSION.GUEST;
  
        await api.modifyOutline({
          outline_bid: outlineBid,
          shifu_bid: currentShifu?.bid,
          type: learningPermission,
          is_hidden: hideChapter,
          system_prompt: systemPrompt,
          is_paid: isPaid,
          require_login: requiresLogin,
          need_login: requiresLogin,
          login_required: requiresLogin,
        });
  
        setIsDirty(false);
        if (needClose) {
          onOpenChange?.(false);
        }
      }catch{
        if(currentShifu?.readonly){
          onOpenChange?.(false);
        }
      }
    },
    [
      outlineBid,
      learningPermission,
      hideChapter,
      systemPrompt,
      currentShifu?.bid,
      onOpenChange,
      currentShifu?.readonly,
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

    const timer = setTimeout(() => {
      onConfirm(false);
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
          onConfirm();
        }}
        onCloseIconClick={() => {
          onConfirm();
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
              <div className='space-y-3'>
                <div className='text-sm font-medium text-foreground'>
                  {t('module.chapterSetting.learningPermission')}
                </div>
                <RadioGroup
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

              <div className='space-y-3'>
                <div className='text-sm font-medium text-foreground'>
                  {t('module.chapterSetting.isHidden')}
                </div>
                <RadioGroup
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

              <div className='space-y-2'>
                <div className='text-sm font-medium text-foreground'>
                  {isChapter
                    ? t('module.chapterSetting.chapterPrompt')
                    : t('module.chapterSetting.lessonPrompt')}
                </div>
                {!isChapter && (
                  <div className='text-xs text-muted-foreground'>
                    {t('module.chapterSetting.lessonPromptHint')}
                  </div>
                )}
                <Textarea
                  value={systemPrompt}
                  onChange={event => {
                    setSystemPrompt(event.target.value);
                    setIsDirty(true);
                  }}
                  maxLength={20000}
                  minRows={3}
                  maxRows={30}
                  placeholder={
                    !isChapter
                      ? t('module.chapterSetting.lessonPromptPlaceholder')
                      : t('module.chapterSetting.promptPlaceholder')
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
      </SheetContent>
    </Sheet>
  );
};

export default ChapterSettingsDialog;
