'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import ScrollText from './ScrollText.svg';
import Image from 'next/image';
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import type { AudioCompleteData } from '@/api/studyV2';
import ContentBlock from '@/components/ChatUi/ContentBlock';
import InteractionBlock from '@/components/ChatUi/InteractionBlock';
import { ChatContentItem, ChatContentItemType } from '@/types/chatUi';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { getAudioTrackByPosition } from '@/lib/audio-utils';
import VariableList from './VariableList';
import DebugCopyButton from './DebugCopyButton';
import { type DebugVariablesMap } from './variableStorage';
import styles from './LessonDebug.module.scss';
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
import { BILLING_PACKAGES_HREF } from '@/lib/billingNavigation';
import {
  type CreditInsufficientAudience,
  isCreditInsufficientBusinessCode,
} from '@/lib/creditInsufficientToast';
import { Button } from '@/components/ui/Button';
import { TooltipProvider } from '@/components/ui/tooltip';
import {
  buildVisibleDebugItems,
  normalizeDebugTypewriterContent,
  shouldEnableDebugTypewriter,
  syncDebugTypewriterCache,
  type DebugTypewriterCache,
} from './debugTypewriterGate';

interface LessonDebugProps {
  loading: boolean;
  errorMessage?: string | null;
  items: ChatContentItem[];
  creditInsufficientAudience?: CreditInsufficientAudience;
  variables?: DebugVariablesMap;
  shifuBid: string;
  onRefresh: (elementBid: string) => void;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onRequestAudioForBlock?: (params: {
    shifuBid: string;
    blockId: string;
    text: string;
  }) => Promise<AudioCompleteData | null>;
  onVariableChange?: (name: string, value: string) => void;
  variableOrder?: string[];
  systemVariableKeys?: string[];
  reGenerateConfirm?: {
    open: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  };
  hiddenVariableKeys?: string[];
  onHideOrRestore?: () => void;
  actionType?: 'hide' | 'restore';
  actionDisabled?: boolean;
  customVariableKeys?: string[];
  unusedVariableKeys?: string[];
  onHideVariable?: (name: string) => void;
  showGenerateBtn?: boolean;
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

const resolveLessonDebugItemIdentity = (
  item: ChatContentItem,
  index?: number,
) =>
  item.element_bid ||
  item.generated_block_bid ||
  item.parent_element_bid ||
  item.parent_block_bid ||
  (index !== undefined ? `idx-${index}` : '');

const resolveLessonDebugItemTypeKey = (item: ChatContentItem) => {
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

export const resolveLessonDebugItemKey = (
  item: ChatContentItem,
  index?: number,
) =>
  `${resolveLessonDebugItemTypeKey(item)}:${resolveLessonDebugItemIdentity(
    item,
    index,
  )}`;

const resolveLessonDebugContentRenderKey = (
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
    resolveLessonDebugItemTypeKey(item),
    item.element_bid || item.generated_block_bid || '',
    item.element_type || '',
    enableStreamingTypewriter || hasStreamingTypewriterIntent
      ? 'typing'
      : 'static',
  ].join(':');
};

const LessonDebug: React.FC<LessonDebugProps> = ({
  loading,
  errorMessage,
  items = [],
  creditInsufficientAudience = 'teacher-collaborator',
  variables,
  shifuBid,
  onRefresh,
  onSend,
  onRequestAudioForBlock,
  onVariableChange,
  variableOrder,
  systemVariableKeys,
  reGenerateConfirm,
  hiddenVariableKeys,
  onHideOrRestore,
  actionType,
  actionDisabled,
  customVariableKeys,
  unusedVariableKeys,
  onHideVariable,
  showGenerateBtn = false,
}) => {
  const { t } = useTranslation();
  const router = useRouter();
  const [variablesCollapsed, setVariablesCollapsed] = React.useState(false);

  const showEmpty = !loading && items.length === 0;
  const [debugTypewriterCache, setDebugTypewriterCache] =
    React.useState<DebugTypewriterCache>({});

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
    return Object.entries(resolvedVariables).reduce<DebugVariablesMap>(
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

  const handleHideVariableConfirm = React.useCallback(
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
    (blockBid: string, content: string) => {
      if (!blockBid) {
        return;
      }

      const resolvedItem = items.find(item => item.element_bid === blockBid);
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
    <div className={cn(styles.lessonDebug, 'text-sm')}>
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
          <div className={styles.variableListWrapper}>
            <VariableList
              variables={visibleVariables}
              collapsed={variablesCollapsed}
              onToggle={() => setVariablesCollapsed(prev => !prev)}
              onChange={onVariableChange}
              variableOrder={variableOrder}
              systemVariableKeys={systemVariableKeys}
              actionType={actionType}
              onAction={handleActionConfirm}
              actionDisabled={actionDisabled}
              customVariableKeys={customVariableKeys}
              unusedVariableKeys={unusedVariableKeys}
              onHideVariable={handleHideVariableConfirm}
            />
          </div>
        )}

        <TooltipProvider delayDuration={150}>
          <div className={styles.debugAreaContent}>
            {loading && items.length === 0 && (
              <div className='flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground'>
                <Loader2 className='h-6 w-6 animate-spin text-muted-foreground' />
                <span>{t('module.shifu.previewArea.loading')}</span>
              </div>
            )}

            {showEmpty && !loading && (
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
                  const parentElementBid = item.parent_element_bid || '';
                  const parentBlockBid = item.parent_block_bid || '';
                  const parentContentItem =
                    (parentElementBid
                      ? itemByElementBid.get(parentElementBid)
                      : undefined) ||
                    (parentBlockBid
                      ? itemByElementBid.get(parentBlockBid) ||
                        itemByGeneratedBlockBid.get(parentBlockBid)
                      : undefined);
                  const parentActionBid =
                    parentContentItem?.element_bid ||
                    parentElementBid ||
                    parentBlockBid;
                  const isTextParent =
                    parentContentItem?.type === ChatContentItemType.CONTENT &&
                    parentContentItem?.element_type === 'text';
                  // Hide preview audio action when backend marks this element as non-speakable.
                  const shouldRenderAudioAction =
                    isTextParent && parentContentItem?.is_speakable !== false;
                  const parentPrimaryTrack = getAudioTrackByPosition(
                    parentContentItem?.audioTracks ?? [],
                  );
                  const shouldRenderGenerateAction = Boolean(
                    showGenerateBtn &&
                    isRegeneratableDebugParent(parentContentItem) &&
                    parentActionBid,
                  );
                  const hasDebugAudioCapability = Boolean(
                    onRequestAudioForBlock && parentActionBid,
                  );
                  if (
                    !shouldRenderGenerateAction &&
                    (!shouldRenderAudioAction || !hasDebugAudioCapability)
                  ) {
                    return null;
                  }
                  return (
                    <div
                      key={resolveLessonDebugItemKey(item, idx)}
                      className='p-0'
                      style={{ maxWidth: '100%' }}
                    >
                      <InteractionBlock
                        shifu_bid={shifuBid}
                        element_bid={parentActionBid}
                        onRefresh={onRefresh}
                        onToggleAskExpanded={noop}
                        disableAskButton
                        disableInteractionButtons
                        showGenerateBtn={shouldRenderGenerateAction}
                        extraActions={
                          onRequestAudioForBlock && shouldRenderAudioAction ? (
                            <AudioPlayer
                              audioUrl={parentPrimaryTrack?.audioUrl}
                              streamingSegments={
                                parentPrimaryTrack?.audioSegments
                              }
                              isStreaming={Boolean(
                                parentPrimaryTrack?.isAudioStreaming,
                              )}
                              alwaysVisible={true}
                              onRequestAudio={() =>
                                onRequestAudioForBlock({
                                  shifuBid,
                                  blockId: parentActionBid,
                                  text: parentContentItem?.content || '',
                                })
                              }
                              className='interaction-icon-btn'
                              size={16}
                            />
                          ) : undefined
                        }
                      />
                    </div>
                  );
                }

                if (item.type === ChatContentItemType.ERROR) {
                  const isCreditInsufficient = isCreditInsufficientBusinessCode(
                    item.business_code,
                  );
                  return (
                    <div
                      key={resolveLessonDebugItemKey(item, idx)}
                      className='p-0 relative'
                      style={{ maxWidth: '100%' }}
                    >
                      <ContentBlock
                        item={item}
                        mobileStyle={false}
                        blockBid={
                          item.element_bid || item.generated_block_bid || ''
                        }
                        contentRenderKey={resolveLessonDebugContentRenderKey(
                          item,
                          false,
                        )}
                        onSend={onSend}
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

                return (
                  <div
                    key={resolveLessonDebugItemKey(item, idx)}
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
                          contentRenderKey={resolveLessonDebugContentRenderKey(
                            item,
                            enableStreamingTypewriter,
                          )}
                          enableStreamingTypewriter={enableStreamingTypewriter}
                          onSend={onSend}
                          onTypeFinished={
                            ENABLE_DEBUG_TYPEWRITER
                              ? handleDebugTypeFinished
                              : undefined
                          }
                        />
                      );
                    })()}
                    {item.type === ChatContentItemType.CONTENT ? (
                      <DebugCopyButton content={item.content || ''} />
                    ) : null}
                  </div>
                );
              })}
          </div>
        </TooltipProvider>
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

export default LessonDebug;
