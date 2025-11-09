'use client';

import React, { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Loader2 } from 'lucide-react';
import ContentBlock from '@/app/c/[[...id]]/Components/ChatUi/ContentBlock';
import InteractionBlock from '@/app/c/[[...id]]/Components/ChatUi/InteractionBlock';
import {
  ChatContentItem,
  ChatContentItemType,
} from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';
import { OnSendContentParams } from 'markdown-flow-ui';

interface LessonPreviewProps {
  loading: boolean;
  isStreaming?: boolean;
  errorMessage?: string | null;
  items: ChatContentItem[];
  shifuBid: string;
}

const noop = () => {};
const noopSend = (_content: OnSendContentParams, _blockBid: string) => {};

const LessonPreview: React.FC<LessonPreviewProps> = ({
  loading,
  isStreaming = false,
  errorMessage,
  items,
  shifuBid,
}) => {
  const { t } = useTranslation();
  const showEmpty = !loading && items.length === 0;
  console.log('items', items);
  return (
    <div className='flex h-full flex-col text-sm'>
      <div className='flex flex-wrap items-baseline gap-2'>
        <h2 className='text-base font-semibold text-foreground'>
          {t('module.shifu.previewArea.title')}
        </h2>
        <p className='text-xs text-muted-foreground'>
          {t('module.shifu.previewArea.description')}
        </p>
      </div>
      <div className='mt-4 flex-1 overflow-hidden rounded-xl border bg-muted/30'>
        {loading && items.length === 0 ? (
          <div className='flex h-full flex-col items-center justify-center gap-2 p-6 text-xs text-muted-foreground'>
            <Loader2 className='h-6 w-6 animate-spin text-muted-foreground' />
            <span>{t('module.shifu.previewArea.loading')}</span>
          </div>
        ) : showEmpty ? (
          <div className='flex h-full flex-col items-center justify-center gap-3 px-8 text-center text-xs text-muted-foreground'>
            <FileText className='h-8 w-8 text-muted-foreground' />
            <span>{t('module.shifu.previewArea.empty')}</span>
          </div>
        ) : (
          <div className='flex h-full flex-col gap-3 overflow-y-auto px-4 py-4'>
            {items.map((item, idx) => {
              if (item.type === ChatContentItemType.LIKE_STATUS) {
                return (
                  <InteractionBlock
                    key={`${idx}-interaction`}
                    shifu_bid={shifuBid}
                    generated_block_bid={item.parent_block_bid || ''}
                    like_status={item.like_status}
                    readonly
                    onRefresh={noop}
                    onToggleAskExpanded={noop}
                  />
                );
              }
              return (
                <div
                  key={`${idx}-content`}
                  style={{ position: 'relative' }}
                >
                  <ContentBlock
                    item={item}
                    mobileStyle={false}
                    blockBid={item.generated_block_bid}
                    confirmButtonText={t('module.renderUi.core.confirm')}
                    onClickCustomButtonAfterContent={noop}
                    onSend={noopSend}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default LessonPreview;
