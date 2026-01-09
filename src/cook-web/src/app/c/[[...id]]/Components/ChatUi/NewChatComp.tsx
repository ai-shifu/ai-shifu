import styles from './ChatComponents.module.scss';
import { ChevronsDown } from 'lucide-react';
import {
  useContext,
  useRef,
  memo,
  useCallback,
  useState,
  useEffect,
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
import useChatLogicHook, {
  ChatContentItem,
  ChatContentItemType,
} from './useChatLogicHook';
import AskBlock from './AskBlock';
import InteractionBlockM from './InteractionBlockM';
import ContentBlock from './ContentBlock';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/Dialog';

export const NewChatComponents = ({
  className,
  lessonUpdate,
  onGoChapter,
  chapterId,
  lessonId,
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
  // const { scrollToBottom } = useAutoScroll(chatRef as any, {
  //   threshold: 120,
  // });

  const [showScrollDown, setShowScrollDown] = useState(false);

  const scrollToBottom = useCallback(() => {
    chatBoxBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const checkScroll = useCallback(() => {
    if (!chatRef.current) return;
    requestAnimationFrame(() => {
      if (!chatRef.current) return;
      const { scrollTop, scrollHeight, clientHeight } = chatRef.current;
      // If content is not scrollable or at the bottom, don't show the button
      const isBottom =
        scrollHeight <= clientHeight ||
        scrollHeight - scrollTop - clientHeight < 150;
      setShowScrollDown(!isBottom);
    });
  }, []);

  const { openPayModal, payModalResult } = useCourseStore(
    useShallow(state => ({
      openPayModal: state.openPayModal,
      payModalResult: state.payModalResult,
    })),
  );

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

  // Audio playback state management
  // Auto-play is enabled by default for TTS - starts when first audio arrives
  const [autoPlayAudio] = useState(true);
  // Track which block is currently playing audio (for sequential playback)
  // Use both state (for re-renders) and ref (for callbacks)
  const [currentPlayingBlockBid, setCurrentPlayingBlockBid] = useState<
    string | null
  >(null);
  const currentPlayingBlockBidRef = useRef<string | null>(null);
  // Queue of blocks waiting to play
  const audioQueueRef = useRef<string[]>([]);
  // Track blocks that have already completed playing (don't auto-play again)
  const playedBlocksRef = useRef<Set<string>>(new Set());

  // Keep ref in sync with state
  useEffect(() => {
    currentPlayingBlockBidRef.current = currentPlayingBlockBid;
  }, [currentPlayingBlockBid]);

  // Handle audio play state change - use ref to avoid stale closure
  const handleAudioPlayStateChange = useCallback(
    (blockBid: string, isPlaying: boolean) => {
      if (isPlaying) {
        currentPlayingBlockBidRef.current = blockBid;
        setCurrentPlayingBlockBid(blockBid);
      } else {
        // Check using ref for the most up-to-date value
        if (currentPlayingBlockBidRef.current === blockBid) {
          // Mark this block as played so it won't auto-play again
          playedBlocksRef.current.add(blockBid);

          // Current audio finished, play next in queue
          const nextBlockBid = audioQueueRef.current.shift();
          if (nextBlockBid) {
            currentPlayingBlockBidRef.current = nextBlockBid;
            setCurrentPlayingBlockBid(nextBlockBid);
          } else {
            currentPlayingBlockBidRef.current = null;
            setCurrentPlayingBlockBid(null);
          }
        }
      }
    },
    [],
  ); // No dependencies - uses refs

  // Check if a block should auto-play (first in queue or currently playing)
  const shouldAutoPlay = useCallback(
    (blockBid: string, hasAudio: boolean) => {
      const result = (() => {
        if (!autoPlayAudio || !hasAudio) return false;

        // If this block has already completed playing, don't auto-play again
        if (playedBlocksRef.current.has(blockBid)) {
          return false;
        }

        // If nothing is playing, this block can play
        if (!currentPlayingBlockBid) {
          return true;
        }

        // If this block is the current playing one
        if (currentPlayingBlockBid === blockBid) {
          return true;
        }

        // Otherwise, add to queue if not already there
        if (!audioQueueRef.current.includes(blockBid)) {
          audioQueueRef.current.push(blockBid);
        }
        return false;
      })();
      return result;
    },
    [autoPlayAudio, currentPlayingBlockBid],
  );

  // Reset audio state when lesson changes
  useEffect(() => {
    playedBlocksRef.current.clear();
    audioQueueRef.current = [];
    currentPlayingBlockBidRef.current = null;
    setCurrentPlayingBlockBid(null);
  }, [lessonId]);

  const {
    items,
    isLoading,
    onSend,
    onRefresh,
    toggleAskExpanded,
    reGenerateConfirm,
  } = useChatLogicHook({
    onGoChapter,
    shifuBid,
    outlineBid: lessonId,
    lessonId,
    chapterId,
    previewMode,
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
    if (container) {
      container.addEventListener('scroll', checkScroll);

      const resizeObserver = new ResizeObserver(() => {
        checkScroll();
      });

      // Observe the container itself
      resizeObserver.observe(container);

      // Observe the content inside (the first child div we added)
      if (container.firstElementChild) {
        resizeObserver.observe(container.firstElementChild);
      }

      checkScroll();

      return () => {
        container.removeEventListener('scroll', checkScroll);
        resizeObserver.disconnect();
      };
    }
  }, [checkScroll, items]); // Added items as dependency to re-bind if structure changes significantly

  // Memoize onSend to prevent new function references
  const memoizedOnSend = useCallback(onSend, [onSend]);

  return (
    <div
      className={cn(
        styles.chatComponents,
        className,
        mobileStyle ? styles.mobile : '',
      )}
      style={{ position: 'relative', overflow: 'hidden', padding: 0 }}
    >
      <div
        className={cn(
          styles.chatComponents,
          className,
          mobileStyle ? styles.mobile : '',
        )}
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
              const baseKey = item.generated_block_bid || `${item.type}-${idx}`;
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
                      generated_block_bid={item.parent_block_bid || ''}
                      like_status={item.like_status}
                      readonly={item.readonly}
                      onRefresh={onRefresh}
                      onToggleAskExpanded={toggleAskExpanded}
                    />
                  </div>
                );
              }

              // Calculate autoPlay once to ensure consistent value.
              // Do not auto-play historical audio on initial load.
              const hasAudioForAutoPlay =
                !item.isHistory &&
                Boolean(
                  item.audioUrl ||
                  item.audioSegments?.length ||
                  item.isAudioStreaming,
                );
              const blockAutoPlay = shouldAutoPlay(
                item.generated_block_bid,
                hasAudioForAutoPlay,
              );

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
                    autoPlayAudio={blockAutoPlay}
                    onAudioPlayStateChange={isPlaying =>
                      handleAudioPlayStateChange(
                        item.generated_block_bid,
                        isPlaying,
                      )
                    }
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
      <button
        className={cn(
          styles.scrollToBottom,
          showScrollDown ? styles.visible : '',
        )}
        onClick={scrollToBottom}
      >
        <ChevronsDown size={20} />
      </button>
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
