import React, { useCallback, useEffect, useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { Button } from '@/components/button';
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
}: {
  outlineBid: string;
  open: boolean;
  onOpenChange?: (open: boolean) => void;
}) => {
  const { currentShifu } = useShifu();
  const { t } = useTranslation();
  const [learningPermission, setLearningPermission] =
    useState<LearningPermission>(LEARNING_PERMISSION.NORMAL);
  const [systemPrompt, setSystemPrompt] = useState('');
  const [hideChapter, setHideChapter] = useState(false);
  const [loading, setLoading] = useState(false);

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
    } finally {
      setLoading(false);
    }
  }, [outlineBid, currentShifu?.bid]);

  const onConfirm = async () => {
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
    onOpenChange?.(false);
  };

  useEffect(() => {
    if (!open) {
      setLearningPermission(LEARNING_PERMISSION.NORMAL);
      setSystemPrompt('');
      setHideChapter(false);
    } else {
      fetchOutlineInfo();
    }
    onOpenChange?.(open);
  }, [open, outlineBid, onOpenChange, fetchOutlineInfo]);

  return (
    <Sheet
      open={open}
      onOpenChange={newOpen => {
        if (
          document.activeElement?.tagName === 'INPUT' ||
          document.activeElement?.tagName === 'TEXTAREA' ||
          document.activeElement?.getAttribute('role') === 'radio'
        ) {
          return;
        }
        onOpenChange?.(newOpen);
      }}
    >
      <SheetContent
        side='right'
        className='flex w-full flex-col overflow-hidden border-l border-border bg-white p-0 sm:w-[360px] md:w-[420px] lg:w-[480px]'
        onPointerDown={event => {
          event.stopPropagation();
        }}
      >
        <div className='border-b border-border px-6 py-5 pr-12'>
          <SheetHeader className='space-y-1 text-left'>
            <SheetTitle className='text-lg font-medium text-foreground'>
              {t('chapterSetting.title')}
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
                  {t('chapterSetting.learningPermission')}
                </div>
                <RadioGroup
                  value={learningPermission}
                  onValueChange={value =>
                    setLearningPermission(value as LearningPermission)
                  }
                  className='flex flex-row flex-wrap gap-x-10 gap-y-2'
                >
                  <div className='flex items-center gap-2'>
                    <RadioGroupItem
                      value={LEARNING_PERMISSION.NORMAL}
                      id='chapter-normal'
                    />
                    <Label
                      htmlFor='chapter-normal'
                      className='text-sm font-normal text-foreground'
                    >
                      {t('chapterSetting.paidChapter')}
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
                      {t('chapterSetting.freeChapter')}
                    </Label>
                  </div>
                  <div className='flex items-center gap-2'>
                    <RadioGroupItem
                      value={LEARNING_PERMISSION.GUEST}
                      id='chapter-guest'
                    />
                    <Label
                      htmlFor='chapter-guest'
                      className='text-sm font-normal text-foreground'
                    >
                      {t('chapterSetting.guestChapter')}
                    </Label>
                  </div>
                </RadioGroup>
              </div>

              <div className='space-y-3'>
                <div className='text-sm font-medium text-foreground'>
                  {t('chapterSetting.isHidden')}
                </div>
                <RadioGroup
                  value={hideChapter ? 'hidden' : 'visible'}
                  onValueChange={value => setHideChapter(value === 'hidden')}
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
                      {t('chapterSetting.visibleChapter')}
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
                      {t('chapterSetting.hideChapter')}
                    </Label>
                  </div>
                </RadioGroup>
              </div>

              <div className='space-y-2'>
                <div className='text-sm font-medium text-foreground'>
                  {t('chapterSetting.systemPrompt')}
                </div>
                {/* <div className='text-xs text-muted-foreground'>
                  {t('chapterSetting.promptHint')}
                </div> */}
                <Textarea
                  value={systemPrompt}
                  onChange={event => setSystemPrompt(event.target.value)}
                  // maxLength={1000}
                  rows={6}
                  // placeholder={t('chapterSetting.promptHint')}
                  className='min-h-[220px]'
                />
                {/* <div className='text-xs text-muted-foreground text-right'>
                  {systemPrompt.length}/1000
                </div> */}
              </div>
            </div>
          </div>
        )}
        <SheetFooter className='border-t border-border bg-white px-6 py-4 sm:flex-row sm:justify-end sm:space-x-4'>
          <Button
            variant='outline'
            onClick={() => onOpenChange?.(false)}
          >
            {t('common.cancel')}
          </Button>
          <Button
            disabled={loading}
            onClick={onConfirm}
          >
            {t('common.confirm')}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
};

export default ChapterSettingsDialog;
