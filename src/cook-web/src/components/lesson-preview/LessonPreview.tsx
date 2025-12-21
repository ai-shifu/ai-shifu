'use client';

import React from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import ScrollText from './ScrollText.svg';
import Image from 'next/image';
import ContentBlock from '@/app/c/[[...id]]/Components/ChatUi/ContentBlock';
import InteractionBlock from '@/app/c/[[...id]]/Components/ChatUi/InteractionBlock';
import {
  ChatContentItem,
  ChatContentItemType,
} from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';
import { OnSendContentParams } from 'markdown-flow-ui';
import VariableList from './VariableList';
import {
  getStoredPreviewVariables,
  type PreviewVariablesMap,
} from './variableStorage';
import styles from './LessonPreview.module.scss';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';

interface LessonPreviewProps {
  loading: boolean;
  errorMessage?: string | null;
  items: ChatContentItem[];
  variables?: PreviewVariablesMap;
  shifuBid: string;
  onRefresh: (generatedBlockBid: string) => void;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onVariableChange?: (name: string, value: string) => void;
  variableOrder?: string[];
  reGenerateConfirm?: {
    open: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  };
}

const noop = () => {};

const LessonPreview: React.FC<LessonPreviewProps> = ({
  loading,
  items = [],
  variables,
  shifuBid,
  onRefresh,
  onSend,
  onVariableChange,
  variableOrder,
  reGenerateConfirm,
}) => {
  const { t } = useTranslation();
  const confirmButtonText = t('module.renderUi.core.confirm');
  const copyButtonText = t('module.renderUi.core.copyCode');
  const copiedButtonText = t('module.renderUi.core.copied');
  const [variablesCollapsed, setVariablesCollapsed] = React.useState(false);

  const showEmpty = !loading && items.length === 0;

  const fallbackVariables = React.useMemo(() => {
    if (!shifuBid) return {} as PreviewVariablesMap;
    const stored = getStoredPreviewVariables(shifuBid);
    return {
      ...(stored.system || {}),
      ...(stored.custom || {}),
    } as PreviewVariablesMap;
  }, [shifuBid]);

  const resolvedVariables = React.useMemo(() => {
    const candidates = [variables, items[0]?.variables];
    for (const candidate of candidates) {
      if (candidate && Object.keys(candidate).length) return candidate;
    }
    return Object.keys(fallbackVariables).length
      ? fallbackVariables
      : undefined;
  }, [fallbackVariables, items, variables]);

  return (
    <div className={cn(styles.lessonPreview, 'text-sm')}>
      <div className='flex flex-nowrap items-baseline gap-2 pt-[4px]'>
        <h2 className='text-base font-semibold text-foreground'>
          {t('module.shifu.previewArea.title')}
        </h2>
        <p className='text-xs text-[rgba(0,0,0,0.45)] truncate'>
          {t('module.shifu.previewArea.description')}
        </p>
      </div>

      <div className={styles.previewArea}>
        {!showEmpty && (
          <div className={styles.variableListWrapper}>
            <VariableList
              variables={resolvedVariables}
              collapsed={variablesCollapsed}
              onToggle={() => setVariablesCollapsed(prev => !prev)}
              onChange={onVariableChange}
              variableOrder={variableOrder}
            />
          </div>
        )}

        <div className={styles.previewAreaContent}>
          {loading && items.length === 0 && (
            <div className='flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground'>
              <Loader2 className='h-6 w-6 animate-spin text-muted-foreground' />
              <span>{t('module.shifu.previewArea.loading')}</span>
            </div>
          )}

          {showEmpty && !loading && (
            <div className='h-full flex flex-col items-center justify-center gap-[13px] px-8 text-center text-[14px] leading-5 text-[rgba(10,10,10,0.45)]'>
              <Image
                src={ScrollText.src}
                alt='scroll-text'
                width={64}
                height={64}
              />
              <span>{t('module.shifu.previewArea.empty')}</span>
            </div>
          )}

          {!showEmpty &&
            items.map((item, idx) => {
              if (item.type === ChatContentItemType.LIKE_STATUS) {
                return (
                  <div
                    key={`${idx}-like`}
                    className='p-0'
                    style={{ maxWidth: '100%' }}
                  >
                    <InteractionBlock
                      shifu_bid={shifuBid}
                      generated_block_bid={item.parent_block_bid || ''}
                      like_status={item.like_status}
                      onRefresh={onRefresh}
                      onToggleAskExpanded={noop}
                      disableAskButton
                      disableInteractionButtons
                    />
                  </div>
                );
              }

              return (
                <div
                  key={`${idx}-content`}
                  className='p-0 relative'
                  style={{
                    maxWidth: '100%',
                    margin: !idx ? '0' : '40px 0 0 0',
                  }}
                >
                  <ContentBlock
                    item={item}
                    mobileStyle={false}
                    blockBid={item.generated_block_bid}
                    confirmButtonText={confirmButtonText}
                    copyButtonText={copyButtonText}
                    copiedButtonText={copiedButtonText}
                    onSend={onSend}
                  />
                </div>
              );
            })}
        </div>
      </div>

      <Dialog
        open={reGenerateConfirm?.open ?? false}
        onOpenChange={open => !open && reGenerateConfirm?.onCancel?.()}
      >
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>{t('module.chat.regenerateConfirmTitle')}</DialogTitle>
            <DialogDescription>
              {t('module.chat.regenerateConfirmDescription')}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className='flex gap-2 sm:gap-2'>
            <button
              type='button'
              onClick={reGenerateConfirm?.onCancel}
              className='px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50'
            >
              {t('common.core.cancel')}
            </button>
            <button
              type='button'
              onClick={reGenerateConfirm?.onConfirm}
              className='px-4 py-2 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-lighter'
            >
              {t('common.core.ok')}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default LessonPreview;
