import React, { useCallback, useEffect, useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
import { Button } from '@/components/button';
import { Textarea } from '@/components/ui/Textarea';
import api from '@/api';
import Loading from '../loading';
import { useTranslation } from 'react-i18next';
import { useShifu } from '@/store';

const ChapterPromptSetting = ({
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
  const [systemPrompt, setSystemPrompt] = useState('');
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
      if (result) {
        setSystemPrompt(result.system_prompt ?? '');
      }
    } finally {
      setLoading(false);
    }
  }, [outlineBid, currentShifu?.bid]);

  const onConfirm = async () => {
    await api.modifyOutline({
      outline_bid: outlineBid,
      shifu_bid: currentShifu?.bid,
      system_prompt: systemPrompt,
    });
    onOpenChange?.(false);
  };

  useEffect(() => {
    if (!open) {
      setSystemPrompt('');
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
          document.activeElement?.tagName === 'TEXTAREA'
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
              {t('chapterSetting.chapterTitle')}
            </SheetTitle>
          </SheetHeader>
        </div>
        {loading ? (
          <div className='flex flex-1 items-center justify-center'>
            <Loading />
          </div>
        ) : (
          <div className='flex-1 overflow-y-auto px-6 py-6'>
            <div className='space-y-3'>
              <div className='text-sm font-medium text-foreground'>
                {t('chapterSetting.systemPrompt')}
              </div>
              <div className='text-xs text-muted-foreground'>
                {t('chapterSetting.promptHint')}
              </div>
              <Textarea
                value={systemPrompt}
                onChange={event => setSystemPrompt(event.target.value)}
                maxLength={1000}
                rows={6}
                placeholder={t('chapterSetting.promptHint')}
                className='min-h-[220px]'
              />
              <div className='text-xs text-muted-foreground text-right'>
                {systemPrompt.length}/1000
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

export default ChapterPromptSetting;
