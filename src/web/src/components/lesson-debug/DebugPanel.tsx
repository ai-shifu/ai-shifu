'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import ScrollText from './scroll-text.svg';
import Image from 'next/image';
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import type { AudioCompleteData } from '@/api/learning';
import ContentBlock from '@/components/chat/ContentBlock';
import InteractionBlock from '@/components/chat/InteractionBlock';
import { ChatContentItem, ChatContentItemType } from '@/types/chat-ui';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { getAudioTrackByPosition } from '@/lib/audio-utils';
import DebugVariablesPanel from './DebugVariablesPanel';
import DebugContentCopyButton from './DebugContentCopyButton';
import { type DebugVariableValues } from '@/types/debug-session';
import styles from './DebugPanel.module.scss';
import { cn } from '@/lib/utils';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { useAlert } from '@/components/ui/AlertProvider';
import { BILLING_PACKAGES_HREF } from '@/lib/billing-navigation';
import {
  type CreditInsufficientAudience,
  isCreditInsufficientBusinessCode,
} from '@/lib/credit-insufficient-toast';
import { Button } from '@/components/ui/Button';
import { TooltipProvider } from '@/components/ui/Tooltip';
import {
  buildVisibleDebugItems,
  normalizeDebugTypewriterContent,
  shouldEnableDebugTypewriter,
  syncDebugTypewriterCache,
  type DebugTypewriterCache,
} from './debug-typewriter-gate';

interface DebugPanelProps {
  isLoading: boolean;
  errorMessage?: string | null;
  items: ChatContentItem[];
  creditInsufficientAudience?: CreditInsufficientAudience;
  variableValues?: DebugVariableValues;
  shifuBid: string;
  onRegenerate: (elementBid: string) => void;
  onSubmitInteraction: (
    content: OnSendContentParams,
    elementBid: string,
  ) => void;
  onRequestElementAudio?: (params: {
    shifuBid: string;
    elementBid: string;
    text: string;
  }) => Promise<AudioCompleteData | null>;
  onVariableChange?: (name: string, value: string) => void;
  variableOrder?: string[];
  systemVariableKeys?: string[];
  regenerationConfirmation?: {
    open: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  };
  hiddenVariableKeys?: string[];
  onApplyVariableVisibilityAction?: () => void;
  variableVisibilityAction?: 'hide' | 'restore';
  isVariableVisibilityActionDisabled?: boolean;
  courseVariableKeys?: string[];
  unusedVariableKeys?: string[];
  onHideVariable?: (name: string) => void;
  showRegenerateAction?: boolean;
}

const noop = () => {};
const ENABLE_DEBUG_TYPEWRITER = false;

const isRegeneratableDebugParent = (
  item?: ChatContentItem,
): item is ChatContentItem => {
  if (!item) {
    return false;
  }

  const itemBid = item.element_bid || item.generated_block_bid || '';
  const generatedBlockBid = item.generated_block_bid || '';
  if (
    !itemBid ||
    !generatedBlockBid ||
    itemBid === 'loading' ||
    generatedBlockBid === 'loading'
  ) {
    return false;
  }

  return (
    item.type === ChatContentItemType.CONTENT && item.element_type === 'text'
  );
};

const shouldPreferGeneratedBlockItem = (
  currentItem: ChatContentItem,
  nextItem: ChatContentItem,
): boolean => {
  if (isRegeneratableDebugParent(currentItem)) {
    return false;
  }
  if (isRegeneratableDebugParent(nextItem)) {
    return true;
  }
  return false;
};

const resolveDebugItemIdentity = (item: ChatContentItem, index?: number) =>
  item.element_bid ||
  item.generated_block_bid ||
  item.parent_element_bid ||
  item.parent_block_bid ||
  (index !== undefined ? `idx-${index}` : '');

const resolveDebugItemTypeKey = (item: ChatContentItem) => {
  if (item.type === ChatContentItemType.LIKE_STATUS) {
    return 'like';
  }

  if (item.type === ChatContentItemType.ERROR) {
    return 'error';
  }

  if (item.type === ChatContentItemType.INTERACTION) {
    return 'interaction';
  }

  if (item.type === ChatContentItemType.ASK) {
    return 'ask';
  }

  return 'content';
};

export const resolveDebugItemKey = (item: ChatContentItem, index?: number) =>
  `${resolveDebugItemTypeKey(item)}:${resolveDebugItemIdentity(item, index)}`;

const resolveDebugContentRenderKey = (
  item: ChatContentItem,
  enableStreamingTypewriter: boolean,
) => {
  const hasStreamingTypewriterIntent =
    item.type === ChatContentItemType.CONTENT &&
    item.element_type === 'text' &&
    item.shouldUseTypewriter === true &&
    item.is_final !== true;

  return [
    'preview',
    resolveDebugItemTypeKey(item),
    item.element_bid || item.generated_block_bid || '',
    item.element_type || '',
    enableStreamingTypewriter || hasStreamingTypewriterIntent
      ? 'typing'
      : 'static',
  ].join(':');
};

const DebugPanel: React.FC<DebugPanelProps> = ({
  isLoading,
  errorMessage,
  items = [],
  creditInsufficientAudience = 'teacher-collaborator',
  variableValues,
  shifuBid,
  onRegenerate,
  onSubmitInteraction,
  onRequestElementAudio,
  onVariableChange,
  variableOrder,
  systemVariableKeys,
  regenerationConfirmation,
  hiddenVariableKeys,
  onApplyVariableVisibilityAction,
  variableVisibilityAction,
  isVariableVisibilityActionDisabled,
  courseVariableKeys,
  unusedVariableKeys,
  onHideVariable,
  showRegenerateAction = false,
}) => {
  const { t } = useTranslation();
  const router = useRouter();
  const [areVariablesCollapsed, setAreVariablesCollapsed] =
    React.useState(false);

  const showEmpty = !isLoading && items.length === 0;
  const [debugTypewriterCache, setDebugTypewriterCache] =
    React.useState<DebugTypewriterCache>({});

  const resolvedVariableValues = React.useMemo(() => {
    if (variableValues && Object.keys(variableValues).length) {
      return variableValues;
    }
    return undefined;
  }, [variableValues]);

  const hiddenSet = React.useMemo(
    () => new Set(hiddenVariableKeys || []),
    [hiddenVariableKeys],
  );

  const visibleVariableValues = React.useMemo(() => {
    if (!resolvedVariableValues) return undefined;
    if (!hiddenSet.size) return resolvedVariableValues;
    return Object.entries(resolvedVariableValues).reduce<DebugVariableValues>(
      (acc, [key, value]) => {
        if (hiddenSet.has(key)) {
          return acc;
        }
        acc[key] = value;
        return acc;
      },
      {},
    );
  }, [hiddenSet, resolvedVariableValues]);

  const itemByElementBid = React.useMemo(() => {
    const map = new Map<string, ChatContentItem>();
    items.forEach(item => {
      if (item.element_bid) {
        map.set(item.element_bid, item);
      }
    });
    return map;
  }, [items]);

  const itemByGeneratedBlockBid = React.useMemo(() => {
    const map = new Map<string, ChatContentItem>();
    items.forEach(item => {
      if (item.generated_block_bid) {
        const existing = map.get(item.generated_block_bid);
        if (!existing || shouldPreferGeneratedBlockItem(existing, item)) {
          map.set(item.generated_block_bid, item);
        }
      }
    });
    return map;
  }, [items]);

  const visibleItems = React.useMemo(
    () =>
      ENABLE_DEBUG_TYPEWRITER
        ? buildVisibleDebugItems(items, debugTypewriterCache)
        : items,
    [items, debugTypewriterCache],
  );

  const actionParentKeys = React.useMemo(() => {
    const parentKeys = new Set<string>();
    visibleItems.forEach(item => {
      if (item.type !== ChatContentItemType.LIKE_STATUS) return;
      const parent =
        (item.parent_element_bid
          ? itemByElementBid.get(item.parent_element_bid)
          : undefined) ||
        (item.parent_block_bid
          ? itemByElementBid.get(item.parent_block_bid) ||
            itemByGeneratedBlockBid.get(item.parent_block_bid)
          : undefined);
      if (parent) {
        parentKeys.add(resolveDebugItemKey(parent));
      }
    });
    return parentKeys;
  }, [visibleItems, itemByElementBid, itemByGeneratedBlockBid]);

  const { showAlert } = useAlert();

  const handleVariableVisibilityConfirmation = React.useCallback(() => {
    if (!onApplyVariableVisibilityAction || !variableVisibilityAction) return;
    const isHide = variableVisibilityAction === 'hide';
    showAlert({
      title: isHide
        ? t('module.shifu.previewArea.variablesHideUnusedConfirmTitle')
        : t('module.shifu.previewArea.variablesRestoreHiddenConfirmTitle'),
      description: isHide
        ? t('module.shifu.previewArea.variablesHideUnusedConfirmDesc')
        : t('module.shifu.previewArea.variablesRestoreHiddenConfirmDesc'),
      confirmText: t('common.core.confirm'),
      cancelText: t('common.core.cancel'),
      onConfirm: () => onApplyVariableVisibilityAction(),
    });
  }, [variableVisibilityAction, onApplyVariableVisibilityAction, showAlert, t]);

  const handleHideVariableConfirmation = React.useCallback(
    (name: string) => {
      if (!onHideVariable) return;
      showAlert({
        title: t('module.shifu.previewArea.variablesHideSingleConfirmTitle'),
        description: t(
          'module.shifu.previewArea.variablesHideSingleConfirmDesc',
          { name },
        ),
        confirmText: t('common.core.confirm'),
        cancelText: t('common.core.cancel'),
        onConfirm: () => onHideVariable(name),
      });
    },
    [onHideVariable, showAlert, t],
  );

  const handleGoToBilling = React.useCallback(() => {
    router.push(BILLING_PACKAGES_HREF);
  }, [router]);

  const handleDebugTypeFinished = React.useCallback(
    (elementBid: string, content: string) => {
      if (!elementBid) {
        return;
      }

      const resolvedItem = items.find(item => item.element_bid === elementBid);
      const resolvedCacheKey = resolvedItem?.element_bid || '';
      if (!resolvedCacheKey) {
        return;
      }

      const normalizedContent = normalizeDebugTypewriterContent(content);
      setDebugTypewriterCache(prevCache => {
        const existingEntry = prevCache[resolvedCacheKey];
        if (
          existingEntry?.content === normalizedContent &&
          existingEntry.isFinished === true
        ) {
          return prevCache;
        }

        return {
          ...prevCache,
          [resolvedCacheKey]: {
            content: normalizedContent,
            isFinished: true,
          },
        };
      });
    },
    [items],
  );

  React.useEffect(() => {
    if (!ENABLE_DEBUG_TYPEWRITER) {
      return;
    }
    setDebugTypewriterCache(prevCache =>
      syncDebugTypewriterCache(items, prevCache),
    );
  }, [items]);

  return (
    <div className={cn(styles.debugPanel, 'text-sm')}>
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

      <div className={styles.debugArea}>
        {!showEmpty && (
          <div className={styles.variablesPanelWrapper}>
            <DebugVariablesPanel
              variableValues={visibleVariableValues}
              collapsed={areVariablesCollapsed}
              onToggleCollapsed={() => setAreVariablesCollapsed(prev => !prev)}
              onVariableChange={onVariableChange}
              variableOrder={variableOrder}
              systemVariableKeys={systemVariableKeys}
              variableVisibilityAction={variableVisibilityAction}
              onApplyVisibilityAction={handleVariableVisibilityConfirmation}
              isVisibilityActionDisabled={isVariableVisibilityActionDisabled}
              courseVariableKeys={courseVariableKeys}
              unusedVariableKeys={unusedVariableKeys}
              onHideVariable={handleHideVariableConfirmation}
            />
          </div>
        )}

        <TooltipProvider delayDuration={150}>
          <div className={styles.debugAreaContent}>
            {isLoading && items.length === 0 && (
              <div className='flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground'>
                <Loader2 className='h-6 w-6 animate-spin text-muted-foreground' />
                <span>{t('module.shifu.previewArea.loading')}</span>
              </div>
            )}

            {showEmpty && !isLoading && (
              <>
                {errorMessage ? (
                  <div
                    role='alert'
                    className='mx-auto flex max-w-md flex-col items-center justify-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-6 py-5 text-center text-sm text-amber-900'
                  >
                    <ExclamationTriangleIcon className='h-8 w-8 text-amber-500' />
                    <span>{errorMessage}</span>
                  </div>
                ) : (
                  <div className='h-full flex flex-col items-center justify-center gap-[13px] px-8 text-center text-[14px] leading-5 text-[rgba(10,10,10,0.45)]'>
                    <Image
                      src={ScrollText.src}
                      alt=''
                      width={64}
                      height={64}
                    />
                    <span>{t('module.shifu.previewArea.empty')}</span>
                  </div>
                )}
              </>
            )}

            {!showEmpty &&
              visibleItems.map((item, idx) => {
                if (item.type === ChatContentItemType.LIKE_STATUS) {
                  return null;
                }

                if (item.type === ChatContentItemType.ERROR) {
                  const isCreditInsufficient = isCreditInsufficientBusinessCode(
                    item.business_code,
                  );
                  return (
                    <div
                      key={resolveDebugItemKey(item, idx)}
                      className='p-0 relative'
                      style={{ maxWidth: '100%' }}
                    >
                      <ContentBlock
                        item={item}
                        mobileStyle={false}
                        blockBid={
                          item.element_bid || item.generated_block_bid || ''
                        }
                        contentRenderKey={resolveDebugContentRenderKey(
                          item,
                          false,
                        )}
                        onSend={onSubmitInteraction}
                        onTypeFinished={
                          ENABLE_DEBUG_TYPEWRITER
                            ? handleDebugTypeFinished
                            : undefined
                        }
                      />
                      {isCreditInsufficient &&
                      creditInsufficientAudience === 'teacher' ? (
                        <Button
                          type='button'
                          size='sm'
                          onClick={handleGoToBilling}
                        >
                          {t('module.billing.alerts.actions.checkoutTopup')}
                        </Button>
                      ) : null}
                    </div>
                  );
                }

                const hasActionRow = actionParentKeys.has(
                  resolveDebugItemKey(item),
                );
                const actionBid =
                  item.element_bid || item.generated_block_bid || '';
                const shouldRenderRegenerateAction = Boolean(
                  hasActionRow &&
                  showRegenerateAction &&
                  isRegeneratableDebugParent(item) &&
                  actionBid,
                );
                const shouldRenderAudioAction = Boolean(
                  hasActionRow &&
                  item.type === ChatContentItemType.CONTENT &&
                  item.element_type === 'text' &&
                  item.is_speakable !== false &&
                  onRequestElementAudio &&
                  actionBid,
                );
                const primaryTrack = getAudioTrackByPosition(
                  item.audioTracks ?? [],
                );

                return (
                  <div
                    key={resolveDebugItemKey(item, idx)}
                    className='p-0 relative'
                    style={{
                      maxWidth: '100%',
                      margin: !idx ? '0' : '40px 0 0 0',
                    }}
                  >
                    {(() => {
                      const enableStreamingTypewriter =
                        ENABLE_DEBUG_TYPEWRITER &&
                        shouldEnableDebugTypewriter(
                          item,
                          debugTypewriterCache[item.element_bid || ''],
                        );

                      return (
                        <ContentBlock
                          item={item}
                          mobileStyle={false}
                          blockBid={
                            item.element_bid || item.generated_block_bid || ''
                          }
                          contentRenderKey={resolveDebugContentRenderKey(
                            item,
                            enableStreamingTypewriter,
                          )}
                          enableStreamingTypewriter={enableStreamingTypewriter}
                          onSend={onSubmitInteraction}
                          onTypeFinished={
                            ENABLE_DEBUG_TYPEWRITER
                              ? handleDebugTypeFinished
                              : undefined
                          }
                        />
                      );
                    })()}
                    {item.type === ChatContentItemType.CONTENT &&
                    (item.content ||
                      shouldRenderRegenerateAction ||
                      shouldRenderAudioAction) ? (
                      <div className='mt-2 flex items-center justify-between gap-3'>
                        {shouldRenderRegenerateAction ||
                        shouldRenderAudioAction ? (
                          <InteractionBlock
                            className='interaction-block--no-padding-top'
                            shifu_bid={shifuBid}
                            element_bid={actionBid}
                            onRefresh={onRegenerate}
                            onToggleAskExpanded={noop}
                            disableAskButton
                            disableInteractionButtons
                            showGenerateBtn={shouldRenderRegenerateAction}
                            extraActions={
                              onRequestElementAudio &&
                              shouldRenderAudioAction ? (
                                <AudioPlayer
                                  audioUrl={primaryTrack?.audioUrl}
                                  streamingSegments={
                                    primaryTrack?.audioSegments
                                  }
                                  isStreaming={Boolean(
                                    primaryTrack?.isAudioStreaming,
                                  )}
                                  alwaysVisible={true}
                                  onRequestAudio={() =>
                                    onRequestElementAudio({
                                      shifuBid,
                                      elementBid: actionBid,
                                      text: item.content || '',
                                    })
                                  }
                                  className='interaction-icon-btn'
                                  size={16}
                                />
                              ) : undefined
                            }
                          />
                        ) : null}
                        <DebugContentCopyButton content={item.content || ''} />
                      </div>
                    ) : null}
                  </div>
                );
              })}
          </div>
        </TooltipProvider>
      </div>

      <Dialog
        open={regenerationConfirmation?.open ?? false}
        onOpenChange={open => !open && regenerationConfirmation?.onCancel?.()}
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
              onClick={regenerationConfirmation?.onCancel}
              className='px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50'
            >
              {t('common.core.cancel')}
            </button>
            <button
              type='button'
              onClick={regenerationConfirmation?.onConfirm}
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

export default DebugPanel;
