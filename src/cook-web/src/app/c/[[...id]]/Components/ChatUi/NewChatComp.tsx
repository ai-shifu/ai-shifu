import styles from './ChatComponents.module.scss';
import { ChevronsDown } from 'lucide-react';
import { createPortal } from 'react-dom';
import {
  useContext,
  useRef,
  memo,
  useCallback,
  useState,
  useEffect,
  useMemo,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils';
import { AppContext } from '../AppContext';
import { useChatComponentsScroll } from './ChatComponents/useChatComponentsScroll';
import { useTracking } from '@/c-common/hooks/useTracking';
import { useEnvStore } from '@/c-store/envStore';
import { useUserStore } from '@/store';
import { useCourseStore } from '@/c-store/useCourseStore';
import { toast } from '@/hooks/useToast';
import InteractionBlock from './InteractionBlock';
import useChatLogicHook, { ChatContentItemType } from './useChatLogicHook';
import type { ChatContentItem } from './useChatLogicHook';
import AskBlock from './AskBlock';
import InteractionBlockM from './InteractionBlockM';
import ContentBlock from './ContentBlock';
import ListenModeRenderer from './ListenModeRenderer';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';
import { useSystemStore } from '@/c-store/useSystemStore';

export const NewChatComponents = ({
  className,
  lessonUpdate,
  onGoChapter,
  chapterId,
  lessonId,
  lessonTitle = '',
  onPurchased,
  chapterUpdate,
  updateSelectedLesson,
  getNextLessonId,
  previewMode = false,
}) => {
  const { trackEvent, trackTrailProgress } = useTracking();
  const { t } = useTranslation();
  const confirmButtonText = t('module.renderUi.core.confirm');
  const copyButtonText = t('module.renderUi.core.copyCode');
  const copiedButtonText = t('module.renderUi.core.copied');
  const chatBoxBottomRef = useRef<HTMLDivElement | null>(null);
  const showOutputInProgressToast = useCallback(() => {
    toast({
      title: t('module.chat.outputInProgress'),
    });
  }, [t]);

  const { courseId: shifuBid } = useEnvStore.getState();
  const { refreshUserInfo } = useUserStore(
    useShallow(state => ({
      refreshUserInfo: state.refreshUserInfo,
    })),
  );
  const { mobileStyle } = useContext(AppContext);

  const chatRef = useRef<HTMLDivElement | null>(null);
  const { scrollToLesson } = useChatComponentsScroll({
    chatRef,
    containerStyle: styles.chatComponents,
    messages: [],
    appendMsg: () => {},
    deleteMsg: () => {},
  });

  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);
  // const { scrollToBottom } = useAutoScroll(chatRef as any, {
  //   threshold: 120,
  // });

  const [showScrollDown, setShowScrollDown] = useState(false);

  const scrollToBottom = useCallback(() => {
    chatBoxBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const isNearBottom = useCallback(
    (element?: HTMLElement | Document | null) => {
      if (!element) {
        return true;
      }
      if (element instanceof HTMLElement) {
        const { scrollTop, scrollHeight, clientHeight } = element;
        return (
          scrollHeight <= clientHeight ||
          scrollHeight - scrollTop - clientHeight < 150
        );
      }
      const docEl = document.documentElement;
      const scrollTop = window.scrollY || docEl.scrollTop;
      const { scrollHeight, clientHeight } = docEl;
      return (
        scrollHeight <= clientHeight ||
        scrollHeight - scrollTop - clientHeight < 150
      );
    },
    [],
  );

  const checkScroll = useCallback(() => {
    requestAnimationFrame(() => {
      const containers: Array<HTMLElement | Document> = [];

      if (chatRef.current) {
        containers.push(chatRef.current);
        if (chatRef.current.parentElement) {
          containers.push(chatRef.current.parentElement);
        }
      }

      if (mobileStyle) {
        containers.push(document);
      }

      const shouldShow = containers.some(container => !isNearBottom(container));
      setShowScrollDown(shouldShow);
    });
  }, [isNearBottom, mobileStyle]);

  const { openPayModal, payModalResult } = useCourseStore(
    useShallow(state => ({
      openPayModal: state.openPayModal,
      payModalResult: state.payModalResult,
    })),
  );
  const learningMode = useSystemStore(state => state.learningMode);
  const isListenMode = learningMode === 'listen';

  const onPayModalOpen = useCallback(() => {
    openPayModal();
  }, [openPayModal]);

  useEffect(() => {
    if (payModalResult === 'ok') {
      onPurchased?.();
      refreshUserInfo();
    }
  }, [onPurchased, payModalResult, refreshUserInfo]);

  const [mobileInteraction, setMobileInteraction] = useState({
    open: false,
    position: { x: 0, y: 0 },
    generatedBlockBid: '',
    likeStatus: null as any,
  });
  const [longPressedBlockBid, setLongPressedBlockBid] = useState<string>('');

  // Streaming TTS sequential playback (auto-play next block)
  const [autoPlayAudio] = useState(true);
  const [currentPlayingBlockBid, setCurrentPlayingBlockBid] = useState<
    string | null
  >(null);
  const currentPlayingBlockBidRef = useRef<string | null>(null);
  const playedBlocksRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    currentPlayingBlockBidRef.current = currentPlayingBlockBid;
  }, [currentPlayingBlockBid]);

  const {
    items,
    isLoading,
    onSend,
    onRefresh,
    toggleAskExpanded,
    reGenerateConfirm,
    requestAudioForBlock,
  } = useChatLogicHook({
    onGoChapter,
    shifuBid,
    outlineBid: lessonId,
    lessonId,
    chapterId,
    previewMode,
    isListenMode,
    trackEvent,
    chatBoxBottomRef,
    trackTrailProgress,
    lessonUpdate,
    chapterUpdate,
    updateSelectedLesson,
    getNextLessonId,
    scrollToLesson,
    // scrollToBottom,
    showOutputInProgressToast,
    onPayModalOpen,
  });

  const itemByGeneratedBid = useMemo(() => {
    const mapping = new Map<string, ChatContentItem>();
    items.forEach(item => {
      if (item.generated_block_bid) {
        mapping.set(item.generated_block_bid, item);
      }
    });
    return mapping;
  }, [items]);

  const handleAudioPlayStateChange = useCallback(
    (blockBid: string, isPlaying: boolean) => {
      if (!isPlaying) {
        return;
      }
      currentPlayingBlockBidRef.current = blockBid;
      setCurrentPlayingBlockBid(blockBid);
    },
    [],
  );

  const handleAudioEnded = useCallback((blockBid: string) => {
    if (currentPlayingBlockBidRef.current !== blockBid) {
      return;
    }
    playedBlocksRef.current.add(blockBid);
    currentPlayingBlockBidRef.current = null;
    setCurrentPlayingBlockBid(null);
  }, []);

  useEffect(() => {
    playedBlocksRef.current.clear();
    currentPlayingBlockBidRef.current = null;
    setCurrentPlayingBlockBid(null);
  }, [lessonId]);

  const autoPlayTargetBlockBid = useMemo(() => {
    if (!autoPlayAudio || previewMode) {
      return null;
    }

    if (currentPlayingBlockBid) {
      return currentPlayingBlockBid;
    }

    for (const item of items) {
      if (item.type !== ChatContentItemType.CONTENT) {
        continue;
      }
      if (item.isHistory) {
        continue;
      }
      const blockBid = item.generated_block_bid;
      if (!blockBid || blockBid === 'loading') {
        continue;
      }
      if (playedBlocksRef.current.has(blockBid)) {
        continue;
      }
      const hasAudioContent = Boolean(
        item.isAudioStreaming ||
        (item.audioSegments && item.audioSegments.length > 0),
      );
      const hasOssAudio = Boolean(item.audioUrl);
      if (!hasAudioContent && !hasOssAudio) {
        continue;
      }
      return blockBid;
    }

    return null;
  }, [autoPlayAudio, currentPlayingBlockBid, items, previewMode]);

  // Memoize onSend to prevent new function references
  const memoizedOnSend = useCallback(onSend, [onSend]);

  const handleLongPress = useCallback(
    (event: any, currentBlock: ChatContentItem) => {
      if (currentBlock.type !== ChatContentItemType.CONTENT) {
        return;
      }
      const target = event.target as HTMLElement;
      const rect = target.getBoundingClientRect();
      const interactionItem = items.find(
        item =>
          item.type === ChatContentItemType.LIKE_STATUS &&
          item.parent_block_bid === currentBlock.generated_block_bid,
      );
      // Use requestAnimationFrame to avoid blocking rendering
      requestAnimationFrame(() => {
        setLongPressedBlockBid(currentBlock.generated_block_bid);
        setMobileInteraction({
          open: true,
          position: {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
          },
          generatedBlockBid: interactionItem?.parent_block_bid || '',
          likeStatus: interactionItem?.like_status,
        });
      });
    },
    [items],
  );

  // Close interaction popover when scrolling
  useEffect(() => {
    if (!mobileStyle || !mobileInteraction.open) {
      return;
    }

    const handleScroll = () => {
      // Close popover and clear selection when scrolling
      setMobileInteraction(prev => ({ ...prev, open: false }));
      setLongPressedBlockBid('');
    };

    // Try to find the actual scrolling container
    // Check current element, parent, and window
    const chatContainer = chatRef.current;
    const parentContainer = chatContainer?.parentElement;

    // Add listeners to multiple possible scroll containers
    const listeners: Array<{
      element: EventTarget;
      handler: typeof handleScroll;
    }> = [];

    // Listen to parent container
    if (parentContainer) {
      parentContainer.addEventListener('scroll', handleScroll, {
        passive: true,
      });
      listeners.push({ element: parentContainer, handler: handleScroll });
    }

    return () => {
      // Clean up all listeners
      listeners.forEach(({ element, handler }) => {
        element.removeEventListener('scroll', handler);
      });
    };
  }, [mobileStyle, mobileInteraction.open]);

  // Memoize callbacks to prevent unnecessary re-renders
  const handleClickAskButton = useCallback(
    (blockBid: string) => {
      toggleAskExpanded(blockBid);
    },
    [toggleAskExpanded],
  );

  useEffect(() => {
    const container = chatRef.current;
    const parentContainer = container?.parentElement;
    const listeners: Array<{ element: EventTarget; handler: () => void }> = [];

    if (container) {
      container.addEventListener('scroll', checkScroll, { passive: true });
      listeners.push({ element: container, handler: checkScroll });
    }

    if (parentContainer) {
      parentContainer.addEventListener('scroll', checkScroll, {
        passive: true,
      });
      listeners.push({ element: parentContainer, handler: checkScroll });
    }

    if (mobileStyle) {
      window.addEventListener('scroll', checkScroll, { passive: true });
      listeners.push({ element: window, handler: checkScroll });
    }

    const resizeObserver = new ResizeObserver(() => {
      checkScroll();
    });

    if (container) {
      resizeObserver.observe(container);

      if (container.firstElementChild) {
        resizeObserver.observe(container.firstElementChild);
      }
    }

    checkScroll();

    return () => {
      listeners.forEach(({ element, handler }) => {
        element.removeEventListener('scroll', handler);
      });
      resizeObserver.disconnect();
    };
  }, [checkScroll, items, mobileStyle]); // Added items as dependency to re-bind if structure changes significantly

  useEffect(() => {
    if (mobileStyle) {
      setPortalTarget(document.getElementById('chat-scroll-target'));
    } else {
      setPortalTarget(null);
    }
  }, [mobileStyle]);

  const containerClassName = cn(
    styles.chatComponents,
    className,
    mobileStyle ? styles.mobile : '',
  );

  const scrollButton = (
    <button
      className={cn(
        styles.scrollToBottom,
        showScrollDown ? styles.visible : '',
        mobileStyle ? styles.mobileScrollBtn : '',
      )}
      onClick={scrollToBottom}
    >
      <ChevronsDown size={20} />
    </button>
  );

  return (
    <div
      className={containerClassName}
      style={{ position: 'relative', overflow: 'hidden', padding: 0 }}
    >
      {isListenMode ? (
        <ListenModeRenderer
          items={items}
          mobileStyle={mobileStyle}
          chatRef={chatRef as React.RefObject<HTMLDivElement>}
          containerClassName={containerClassName}
          isLoading={isLoading}
          sectionTitle={lessonTitle}
          previewMode={previewMode}
          onRequestAudioForBlock={requestAudioForBlock}
          onSend={memoizedOnSend}
        />
      ) : (
        <div
          className={containerClassName}
          ref={chatRef}
          style={{ width: '100%', height: '100%', overflowY: 'auto' }}
        >
          <div>
            {isLoading ? (
              <></>
            ) : (
              items.map((item, idx) => {
                const isLongPressed =
                  longPressedBlockBid === item.generated_block_bid;
                const baseKey =
                  item.generated_block_bid || `${item.type}-${idx}`;
                const parentKey = item.parent_block_bid || baseKey;
                if (item.type === ChatContentItemType.ASK) {
                  return (
                    <div
                      key={`ask-${parentKey}`}
                      style={{
                        position: 'relative',
                        margin: '0 auto',
                        maxWidth: mobileStyle ? '100%' : '1000px',
                        padding: '0 20px',
                      }}
                    >
                      <AskBlock
                        isExpanded={item.isAskExpanded}
                        shifu_bid={shifuBid}
                        outline_bid={lessonId}
                        preview_mode={previewMode}
                        generated_block_bid={item.parent_block_bid || ''}
                        onToggleAskExpanded={toggleAskExpanded}
                        askList={(item.ask_list || []) as any[]}
                      />
                    </div>
                  );
                }

                if (item.type === ChatContentItemType.LIKE_STATUS) {
                  const parentBlockBid = item.parent_block_bid || '';
                  const parentContentItem = parentBlockBid
                    ? itemByGeneratedBid.get(parentBlockBid)
                    : undefined;
                  const canRequestAudio =
                    !previewMode && Boolean(parentBlockBid);
                  const hasAudioForBlock = Boolean(
                    parentContentItem?.audioUrl ||
                    parentContentItem?.isAudioStreaming ||
                    (parentContentItem?.audioSegments &&
                      parentContentItem.audioSegments.length > 0),
                  );
                  const shouldAutoPlay =
                    autoPlayTargetBlockBid === parentBlockBid;
                  return mobileStyle ? null : (
                    <div
                      key={`like-${parentKey}`}
                      style={{
                        margin: '0 auto',
                        maxWidth: '1000px',
                        padding: '0px 20px',
                      }}
                    >
                      <InteractionBlock
                        shifu_bid={shifuBid}
                        generated_block_bid={parentBlockBid}
                        like_status={item.like_status}
                        readonly={item.readonly}
                        onRefresh={onRefresh}
                        onToggleAskExpanded={toggleAskExpanded}
                        extraActions={
                          canRequestAudio || hasAudioForBlock ? (
                            <AudioPlayer
                              audioUrl={parentContentItem?.audioUrl}
                              streamingSegments={
                                parentContentItem?.audioSegments
                              }
                              isStreaming={Boolean(
                                parentContentItem?.isAudioStreaming,
                              )}
                              alwaysVisible={canRequestAudio}
                              onRequestAudio={
                                canRequestAudio
                                  ? () => requestAudioForBlock(parentBlockBid)
                                  : undefined
                              }
                              autoPlay={shouldAutoPlay}
                              onPlayStateChange={isPlaying =>
                                handleAudioPlayStateChange(
                                  parentBlockBid,
                                  isPlaying,
                                )
                              }
                              onEnded={() => handleAudioEnded(parentBlockBid)}
                              className='interaction-icon-btn'
                              size={16}
                            />
                          ) : null
                        }
                      />
                    </div>
                  );
                }

                return (
                  <div
                    key={`content-${baseKey}`}
                    style={{
                      position: 'relative',
                      margin:
                        !idx || item.type === ChatContentItemType.INTERACTION
                          ? '0 auto'
                          : '40px auto 0 auto',
                      maxWidth: mobileStyle ? '100%' : '1000px',
                      padding: '0 20px',
                    }}
                  >
                    {isLongPressed && mobileStyle && (
                      <div className='long-press-overlay' />
                    )}
                    <ContentBlock
                      item={item}
                      mobileStyle={mobileStyle}
                      blockBid={item.generated_block_bid}
                      confirmButtonText={confirmButtonText}
                      copyButtonText={copyButtonText}
                      copiedButtonText={copiedButtonText}
                      onClickCustomButtonAfterContent={handleClickAskButton}
                      onSend={memoizedOnSend}
                      onLongPress={handleLongPress}
                      autoPlayAudio={
                        autoPlayTargetBlockBid === item.generated_block_bid
                      }
                      onAudioPlayStateChange={handleAudioPlayStateChange}
                      onAudioEnded={handleAudioEnded}
                    />
                  </div>
                );
              })
            )}
            <div
              ref={chatBoxBottomRef}
              id='chat-box-bottom'
            ></div>
          </div>
        </div>
      )}
      {!isListenMode &&
        (mobileStyle && portalTarget
          ? createPortal(scrollButton, portalTarget)
          : scrollButton)}
      {mobileStyle && mobileInteraction?.generatedBlockBid && (
        <InteractionBlockM
          open={mobileInteraction.open}
          onOpenChange={open => {
            setMobileInteraction(prev => ({ ...prev, open }));
            if (!open) {
              setLongPressedBlockBid('');
            }
          }}
          position={mobileInteraction.position}
          shifu_bid={shifuBid}
          generated_block_bid={mobileInteraction.generatedBlockBid}
          like_status={mobileInteraction.likeStatus}
          onRefresh={onRefresh}
          audioUrl={
            itemByGeneratedBid.get(mobileInteraction.generatedBlockBid)
              ?.audioUrl
          }
          streamingSegments={
            itemByGeneratedBid.get(mobileInteraction.generatedBlockBid)
              ?.audioSegments
          }
          isStreaming={Boolean(
            itemByGeneratedBid.get(mobileInteraction.generatedBlockBid)
              ?.isAudioStreaming,
          )}
          onRequestAudio={
            !previewMode && mobileInteraction.generatedBlockBid
              ? () => requestAudioForBlock(mobileInteraction.generatedBlockBid)
              : undefined
          }
        />
      )}
      <Dialog
        open={reGenerateConfirm.open}
        onOpenChange={open => {
          if (!open) {
            reGenerateConfirm.onCancel();
          }
        }}
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
              onClick={reGenerateConfirm.onCancel}
              className='px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50'
            >
              {t('common.core.cancel')}
            </button>
            <button
              type='button'
              onClick={reGenerateConfirm.onConfirm}
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

NewChatComponents.displayName = 'NewChatComponents';

export default memo(NewChatComponents);
