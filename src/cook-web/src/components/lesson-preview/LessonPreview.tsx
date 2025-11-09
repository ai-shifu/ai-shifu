'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import { FileText, Loader2 } from 'lucide-react';
import ContentBlock from '@/app/c/[[...id]]/Components/ChatUi/ContentBlock';
import {
  ChatContentItem,
  ChatContentItemType,
} from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';
import { OnSendContentParams } from 'markdown-flow-ui';

export type PreviewMessage = {
  id: string;
  type: 'content' | 'interaction' | 'error';
  content: string;
  variable?: string;
};

interface LessonPreviewProps {
  loading: boolean;
  isStreaming?: boolean;
  errorMessage?: string | null;
  messages: PreviewMessage[];
}

const noop = () => {};
const noopSend = (_content: OnSendContentParams, _blockBid: string) => {};
const LessonPreview: React.FC<LessonPreviewProps> = ({
  loading,
  isStreaming = false,
  errorMessage,
  messages,
}) => {
  const { t } = useTranslation();
  const showEmpty = !loading && messages.length === 0;

  const renderMessage = (message: PreviewMessage) => {
    if (message.type === 'error') {
      return (
        <div
          key={message.id}
          className='rounded-xl border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive'
        >
          {message.content}
        </div>
      );
    }

    const chatItem: ChatContentItem = {
      content: message.content,
      generated_block_bid: message.id,
      type: ChatContentItemType.CONTENT,
      readonly: false,
    };

    return (
      <div key={message.id} className='rounded-2xl'>
        <ContentBlock
          key={`${message.id}-block`}
          item={chatItem}
          mobileStyle={false}
          blockBid={message.id}
          confirmButtonText={t('module.renderUi.core.confirm')}
          onClickCustomButtonAfterContent={noop}
          onSend={noopSend}
        />
      </div>
    );
  };

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
        {loading && messages.length === 0 ? (
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
          <div className='bg-white flex h-full flex-col gap-3 overflow-y-auto px-4 py-4'>
            {messages.map(message => renderMessage(message))}
            {/* {isStreaming ? (
              <div className='flex items-center gap-2 text-xs text-muted-foreground'>
                <Loader2 className='h-3.5 w-3.5 animate-spin' />
                <span>{t('module.shifu.previewArea.loading')}</span>
              </div>
            ) : null} */}
          </div>
        )}
      </div>
      {errorMessage ? (
        <p className='mt-3 text-xs text-destructive'>{errorMessage}</p>
      ) : null}
    </div>
  );
};

export default LessonPreview;
