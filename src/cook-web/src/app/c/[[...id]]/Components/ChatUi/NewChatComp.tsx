import './ForkChatUI/styles/index.scss';
import 'markdown-flow-ui/dist/markdown-flow-ui.css';
import styles from './ChatComponents.module.scss';
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
import useAutoScroll from './useAutoScroll';
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
import { OnSendContentParams } from 'markdown-flow-ui';

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
  const { scrollToBottom } = useAutoScroll(chatRef as any, {
    threshold: 120,
  });

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

  const {
    items,
    isLoading,
    onSend,
    onRefresh,
    onTypeFinished,
    toggleAskExpanded,
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
    scrollToBottom,
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

  // Memoize onSend and onTypeFinished to prevent new function references
  const memoizedOnSend = useCallback(onSend, [onSend]);
  const memoizedOnTypeFinished = useCallback(onTypeFinished, [onTypeFinished]);

  return (
    <div
      className={cn(
        styles.chatComponents,
        className,
        mobileStyle ? styles.mobile : '',
      )}
      ref={chatRef}
    >
      {isLoading ? (
        <></>
      ) : (
        items.map((item, idx) => {
          const isLongPressed =
            longPressedBlockBid === item.generated_block_bid;

          if (item.type === ChatContentItemType.ASK) {
            return (
              <AskBlock
                isExpanded={item.isAskExpanded}
                shifu_bid={shifuBid}
                outline_bid={lessonId}
                preview_mode={previewMode}
                generated_block_bid={item.parent_block_bid || ''}
                onToggleAskExpanded={toggleAskExpanded}
                key={`${idx}-ask`}
                askList={(item.ask_list || []) as any[]}
              />
            );
          }

          if (item.type === ChatContentItemType.LIKE_STATUS) {
            return mobileStyle ? null : (
              <InteractionBlock
                key={`${idx}-interaction`}
                shifu_bid={shifuBid}
                generated_block_bid={item.parent_block_bid || ''}
                like_status={item.like_status}
                readonly={item.readonly}
                onRefresh={onRefresh}
                onToggleAskExpanded={toggleAskExpanded}
              />
            );
          }

          return (
            <div
              key={`${idx}-content`}
              style={{ position: 'relative' }}
            >
              {isLongPressed && mobileStyle && (
                <div className='long-press-overlay' />
              )}
              <ContentBlock
                item={item}
                mobileStyle={mobileStyle}
                blockBid={item.generated_block_bid}
                onClickCustomButtonAfterContent={handleClickAskButton}
                onSend={memoizedOnSend}
                onTypeFinished={memoizedOnTypeFinished}
                onLongPress={handleLongPress}
              />
            </div>
          );
        })
      )}
      <div
        ref={chatBoxBottomRef}
        id='chat-box-bottom'
      ></div>
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
    </div>
  );
};

NewChatComponents.displayName = 'NewChatComponents';

export default memo(NewChatComponents);
