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
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import type { AudioCompleteData } from '@/c-api/studyV2';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import VariableList from './VariableList';
import { type PreviewVariablesMap } from './variableStorage';
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
import { useAlert } from '@/components/ui/UseAlert';

interface LessonPreviewProps {
  loading: boolean;
  errorMessage?: string | null;
  items: ChatContentItem[];
  variables?: PreviewVariablesMap;
  shifuBid: string;
  onRefresh: (generatedBlockBid: string) => void;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onRequestAudioForBlock?: (params: {
    shifuBid: string;
    blockId: string;
    text: string;
  }) => Promise<AudioCompleteData | null>;
  onVariableChange?: (name: string, value: string) => void;
  variableOrder?: string[];
  reGenerateConfirm?: {
    open: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  };
  hiddenVariableKeys?: string[];
  onHideOrRestore?: () => void;
  actionType?: 'hide' | 'restore';
  actionDisabled?: boolean;
}

const noop = () => {};

const LessonPreview: React.FC<LessonPreviewProps> = ({
  loading,
  items = [],
  variables,
  shifuBid,
  onRefresh,
  onSend,
  onRequestAudioForBlock,
  onVariableChange,
  variableOrder,
  reGenerateConfirm,
  hiddenVariableKeys,
  onHideOrRestore,
  actionType,
  actionDisabled,
}) => {
  const { t } = useTranslation();
  const confirmButtonText = t('module.renderUi.core.confirm');
  const copyButtonText = t('module.renderUi.core.copyCode');
  const copiedButtonText = t('module.renderUi.core.copied');
  const [variablesCollapsed, setVariablesCollapsed] = React.useState(false);

  const showEmpty = !loading && items.length === 0;

  const resolvedVariables = React.useMemo(() => {
    if (variables && Object.keys(variables).length) {
      return variables;
    }
    return undefined;
  }, [variables]);

  const hiddenSet = React.useMemo(
    () => new Set(hiddenVariableKeys || []),
    [hiddenVariableKeys],
  );

  const visibleVariables = React.useMemo(() => {
    if (!resolvedVariables) return undefined;
    if (!hiddenSet.size) return resolvedVariables;
    return Object.entries(resolvedVariables).reduce<PreviewVariablesMap>(
      (acc, [key, value]) => {
        if (hiddenSet.has(key)) {
          return acc;
        }
        acc[key] = value;
        return acc;
      },
      {},
    );
  }, [hiddenSet, resolvedVariables]);

  const itemByGeneratedBid = React.useMemo(() => {
    const map = new Map<string, ChatContentItem>();
    items.forEach(item => {
      if (item.generated_block_bid) {
        map.set(item.generated_block_bid, item);
      }
    });
    return map;
  }, [items]);

  const { showAlert } = useAlert();

  const handleActionConfirm = React.useCallback(() => {
    if (!onHideOrRestore || !actionType) return;
    const isHide = actionType === 'hide';
    showAlert({
      title: isHide
        ? t('module.shifu.previewArea.variablesHideUnusedConfirmTitle')
        : t('module.shifu.previewArea.variablesRestoreHiddenConfirmTitle'),
      description: isHide
        ? t('module.shifu.previewArea.variablesHideUnusedConfirmDesc')
        : t('module.shifu.previewArea.variablesRestoreHiddenConfirmDesc'),
      confirmText: t('common.core.confirm'),
      cancelText: t('common.core.cancel'),
      onConfirm: () => onHideOrRestore(),
    });
  }, [actionType, onHideOrRestore, showAlert, t]);

  return (
    <div className={cn(styles.lessonPreview, 'text-sm')}>
      <div className='flex items-baseline gap-2 pt-[4px]'>
        <h2 className='text-base font-semibold text-foreground whitespace-nowrap shrink-0'>
          {t('module.shifu.previewArea.title')}
        </h2>
        <span
          className='flex-1 min-w-0 text-xs text-[rgba(0,0,0,0.45)] truncate'
          title={t('module.shifu.previewArea.description')}
        >
          {t('module.shifu.previewArea.description')}
        </span>
      </div>

      <div className={styles.previewArea}>
        {!showEmpty && (
          <div className={styles.variableListWrapper}>
            <VariableList
              variables={visibleVariables}
              collapsed={variablesCollapsed}
              onToggle={() => setVariablesCollapsed(prev => !prev)}
              onChange={onVariableChange}
              variableOrder={variableOrder}
              actionType={actionType}
              onAction={handleActionConfirm}
              actionDisabled={actionDisabled}
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
                const parentBlockBid = item.parent_block_bid || '';
                const parentContentItem = parentBlockBid
                  ? itemByGeneratedBid.get(parentBlockBid)
                  : undefined;
                return (
                  <div
                    key={`${idx}-like`}
                    className='p-0'
                    style={{ maxWidth: '100%' }}
                  >
                    <InteractionBlock
                      shifu_bid={shifuBid}
                      generated_block_bid={parentBlockBid}
                      like_status={item.like_status}
                      onRefresh={onRefresh}
                      onToggleAskExpanded={noop}
                      disableAskButton
                      disableInteractionButtons
                      extraActions={
                        <AudioPlayer
                          audioUrl={parentContentItem?.audioUrl}
                          streamingSegments={parentContentItem?.audioSegments}
                          isStreaming={Boolean(
                            parentContentItem?.isAudioStreaming,
                          )}
                          alwaysVisible={true}
                          onRequestAudio={
                            onRequestAudioForBlock
                              ? () =>
                                  onRequestAudioForBlock({
                                    shifuBid,
                                    blockId: parentBlockBid,
                                    text: parentContentItem?.content || '',
                                  })
                              : undefined
                          }
                          className='interaction-icon-btn'
                          size={16}
                        />
                      }
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
