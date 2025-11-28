import React, { useCallback, useEffect, useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/Sheet';
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
      if (result) {
        setSystemPrompt(result.system_prompt ?? '');
        setIsDirty(false);
      }
    } finally {
      setLoading(false);
    }
  }, [outlineBid, currentShifu?.bid]);

  const onConfirm = useCallback(
    async (needClose = true) => {
      try {
        if (currentShifu?.readonly) {
          onOpenChange?.(false);
          return;
        }
        if (!outlineBid) {
          return;
        }

        await api.modifyOutline({
          outline_bid: outlineBid,
          shifu_bid: currentShifu?.bid,
          system_prompt: systemPrompt,
        });
        setIsDirty(false);
        if (needClose) {
          onOpenChange?.(false);
        }
      } catch {}
    },
    [
      outlineBid,
      currentShifu?.bid,
      systemPrompt,
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
    if (!open || loading || !isDirty || currentShifu?.readonly) {
      return;
    }

    const timer = setTimeout(() => {
      onConfirm(false);
    }, 3000);

    return () => clearTimeout(timer);
  }, [open, loading, isDirty, systemPrompt, onConfirm, currentShifu?.readonly]);

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
              {t('module.chapterSetting.chapterSettingsTitle')}
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
                {t('module.chapterSetting.chapterPrompt')}
              </div>
              <div className='text-xs text-muted-foreground'>
                {t('module.chapterSetting.chapterPromptHint')}
              </div>
              <Textarea
                disabled={currentShifu?.readonly}
                value={systemPrompt}
                onChange={event => {
                  setSystemPrompt(event.target.value);
                  setIsDirty(true);
                }}
                maxLength={20000}
                minRows={6}
                maxRows={30}
                placeholder={t(
                  'module.chapterSetting.chapterPromptPlaceholder',
                )}
                className='min-h-[220px]'
              />
              {/* <div className='text-xs text-muted-foreground text-right'>
                {systemPrompt.length}/10000
              </div> */}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
};

export default ChapterPromptSetting;
