import React, {
  useState,
  useRef,
  useCallback,
  useContext,
  useEffect,
} from 'react';
import { cn } from '@/lib/utils';
import { lessonFeedbackInteractionDefaultValueOptions } from '@/c-utils/lesson-feedback-interaction-defaults';
import { useTranslation } from 'react-i18next';
import { Maximize2, Minimize2, X } from 'lucide-react';
import { ContentRender, MarkdownFlowInput } from 'markdown-flow-ui/renderer';
import {
  checkIsRunning,
  getRunMessage,
  SSE_INPUT_TYPE,
  SSE_OUTPUT_TYPE,
} from '@/c-api/studyV2';
import { fixMarkdownStream } from '@/c-utils/markdownUtils';
import LoadingBar from './LoadingBar';
import styles from './AskBlock.module.scss';
import { toast } from '@/hooks/useToast';
import { AppContext } from '../AppContext';
import Image from 'next/image';
import ShifuIcon from '@/c-assets/newchat/light/icon_shifu.svg';
import { BLOCK_TYPE } from '@/c-api/studyV2';
import { Avatar, AvatarImage } from '@/components/ui/Avatar';
import { useCourseStore } from '@/c-store/useCourseStore';
export interface AskMessage {
  type: typeof BLOCK_TYPE.ASK | typeof BLOCK_TYPE.ANSWER;
  content: string;
  isStreaming?: boolean;
  element_bid?: string;
}

export interface AskBlockProps {
  askList?: AskMessage[];
  className?: string;
  isExpanded?: boolean;
  shifu_bid: string;
  outline_bid: string;
  preview_mode?: boolean;
  element_bid: string;
  onAskListChange?: (askList: AskMessage[], element_bid: string) => void;
  onToggleAskExpanded?: (element_bid: string) => void;
}

/**
 * AskBlock
 * Follow-up area component that contains the Q&A list and custom input box with streaming support
 */
export default function AskBlock({
  askList = [],
  className,
  isExpanded = undefined,
  shifu_bid,
  outline_bid,
  preview_mode = false,
  element_bid,
  onAskListChange,
  onToggleAskExpanded,
}: AskBlockProps) {
  const { t } = useTranslation();
  const copyButtonText = t('module.renderUi.core.copyCode');
  const copiedButtonText = t('module.renderUi.core.copied');
  const { mobileStyle } = useContext(AppContext);
  const courseAvatar = useCourseStore(state => state.courseAvatar);
  const [displayList, setDisplayList] = useState<AskMessage[]>(() => {
    return askList.map(item => ({
      ...item,
      content: item.content || '',
    }));
  });

  const [inputValue, setInputValue] = useState('');
  const sseRef = useRef<any>(null);
  const currentContentRef = useRef<string>('');
  const currentAnswerElementBidRef = useRef<string>('');
  const isStreamingRef = useRef(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showMobileDialog, setShowMobileDialog] = useState(askList.length > 0);
  const mobileContentRef = useRef<HTMLDivElement | null>(null);
  const inputWrapperRef = useRef<HTMLDivElement | null>(null);
  const isSlideAskBlock = className?.includes('listen-slide-ask-block');
  const expanded = isExpanded ?? (!mobileStyle && askList.length > 0);
  const shouldForceSlideMobileDialog =
    Boolean(isSlideAskBlock) && mobileStyle && expanded;
  const shouldShowMobileDialog =
    showMobileDialog || shouldForceSlideMobileDialog;
  const showOutputInProgressToast = useCallback(() => {
    toast({
      title: t('module.chat.outputInProgress'),
    });
  }, [t]);

  const finalizeStreamingMessage = useCallback(() => {
    isStreamingRef.current = false;
    setDisplayList(prev => {
      const newList = [...prev];
      const lastIndex = newList.length - 1;
      if (lastIndex >= 0 && newList[lastIndex].type === BLOCK_TYPE.ANSWER) {
        newList[lastIndex] = {
          ...newList[lastIndex],
          isStreaming: false,
        };
      }
      return newList;
    });
  }, []);

  const updateStreamingAnswerMessage = useCallback((incomingText: string) => {
    const prevText = currentContentRef.current || '';
    const delta = fixMarkdownStream(prevText, incomingText || '');
    const nextText = prevText + delta;
    currentContentRef.current = nextText;

    setDisplayList(prev => {
      const newList = [...prev];
      const lastIndex = newList.length - 1;
      if (lastIndex >= 0 && newList[lastIndex].type === BLOCK_TYPE.ANSWER) {
        newList[lastIndex] = {
          ...newList[lastIndex],
          content: nextText,
          isStreaming: true,
        };
      }
      return newList;
    });
  }, []);

  const replaceStreamingAnswerMessage = useCallback(
    (incomingText: string, answerElementBid = '') => {
      const nextText = incomingText || '';
      currentContentRef.current = nextText;
      if (answerElementBid) {
        currentAnswerElementBidRef.current = answerElementBid;
      }

      setDisplayList(prev => {
        const newList = [...prev];
        const lastIndex = newList.length - 1;
        if (lastIndex >= 0 && newList[lastIndex].type === BLOCK_TYPE.ANSWER) {
          newList[lastIndex] = {
            ...newList[lastIndex],
            content: nextText,
            isStreaming: true,
            element_bid: answerElementBid || newList[lastIndex].element_bid,
          };
        }
        return newList;
      });
    },
    [],
  );

  const handleSendCustomQuestion = useCallback(async () => {
    const question = inputValue.trim();
    if (isStreamingRef.current) {
      showOutputInProgressToast();
      return;
    }

    if (!question) {
      return;
    }
    const runningRes = await checkIsRunning(shifu_bid, outline_bid);
    if (runningRes.is_running) {
      showOutputInProgressToast();
      return;
    }

    // Close any previous SSE connection
    sseRef.current?.close();
    setShowMobileDialog(true);

    // Append the new question as a user message at the end
    setDisplayList(prev => [
      ...prev,
      {
        type: BLOCK_TYPE.ASK,
        content: question,
      },
    ]);

    setInputValue('');

    // Add an empty teacher reply placeholder to receive streaming content
    setDisplayList(prev => [
      ...prev,
      {
        type: BLOCK_TYPE.ANSWER,
        content: '',
        isStreaming: true,
        element_bid: '',
      },
    ]);

    // Reset the streaming content buffer
    currentContentRef.current = '';
    currentAnswerElementBidRef.current = '';
    isStreamingRef.current = true;

    // Initiate the SSE request
    const source = getRunMessage(
      shifu_bid,
      outline_bid,
      preview_mode,
      {
        input: question,
        input_type: SSE_INPUT_TYPE.ASK,
        reload_generated_block_bid: element_bid,
        reload_element_bid: element_bid,
        listen: false,
      },
      async response => {
        try {
          if (response.type === SSE_OUTPUT_TYPE.HEARTBEAT) {
            return;
          }

          if (response.type === SSE_OUTPUT_TYPE.ERROR) {
            finalizeStreamingMessage();
            sseRef.current?.close();
            return;
          }

          if (response.type === SSE_OUTPUT_TYPE.CONTENT) {
            updateStreamingAnswerMessage(response.content || '');
            return;
          }

          if (response.type === SSE_OUTPUT_TYPE.ELEMENT) {
            const elementRecord =
              response.content && typeof response.content === 'object'
                ? response.content
                : null;
            const elementType =
              typeof elementRecord?.element_type === 'string'
                ? elementRecord.element_type
                : '';

            if (elementType === BLOCK_TYPE.ANSWER) {
              const answerElementBid =
                typeof elementRecord?.target_element_bid === 'string' &&
                elementRecord.target_element_bid
                  ? elementRecord.target_element_bid
                  : typeof elementRecord?.element_bid === 'string'
                    ? elementRecord.element_bid
                    : '';
              const answerText =
                typeof elementRecord?.content === 'string'
                  ? elementRecord.content
                  : '';

              replaceStreamingAnswerMessage(answerText, answerElementBid);
              return;
            }
          }

          if (
            response.type === SSE_OUTPUT_TYPE.BREAK ||
            response.type === SSE_OUTPUT_TYPE.TEXT_END
          ) {
            finalizeStreamingMessage();
            sseRef.current?.close();
            return;
          }
        } catch {
          finalizeStreamingMessage();
        }
      },
    );

    // Add error and close listeners to ensure the state resets
    source.addEventListener('error', () => {
      finalizeStreamingMessage();
    });

    source.addEventListener('readystatechange', () => {
      // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
      if (source.readyState === 1) {
        isStreamingRef.current = true;
      } else if (source.readyState === 2) {
        finalizeStreamingMessage();
      }
    });

    sseRef.current = source;
  }, [
    shifu_bid,
    outline_bid,
    preview_mode,
    element_bid,
    inputValue,
    showOutputInProgressToast,
    finalizeStreamingMessage,
    replaceStreamingAnswerMessage,
    updateStreamingAnswerMessage,
  ]);
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInputValue(e.target.value);
    },
    [],
  );

  // Decide which messages to display
  const messagesToShow = expanded ? displayList : displayList.slice(0, 1);
  const hasAskAnswerMessages = messagesToShow.length > 0;

  useEffect(() => {
    onAskListChange?.(displayList, element_bid);
  }, [displayList, element_bid, onAskListChange]);

  useEffect(() => {
    if (!expanded) {
      setIsFullscreen(false);
    }
  }, [expanded]);

  useEffect(() => {
    return () => {
      sseRef.current?.close();
    };
  }, []);

  useEffect(() => {
    if (askList.length > 0) {
      setShowMobileDialog(true);
    }
  }, [askList.length]);

  useEffect(() => {
    if (!mobileStyle || !expanded) {
      return;
    }

    if (typeof document === 'undefined') {
      return;
    }

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, [mobileStyle, expanded]);

  useEffect(() => {
    if (!mobileStyle || !shouldShowMobileDialog || !expanded) {
      return;
    }

    const container = mobileContentRef.current;
    if (!container) {
      return;
    }

    const rafId = requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });

    return () => {
      cancelAnimationFrame(rafId);
    };
  }, [mobileStyle, shouldShowMobileDialog, expanded, messagesToShow.length]);

  const handleClose = useCallback(() => {
    setIsFullscreen(false);
    // onClose?.();
    onToggleAskExpanded?.(element_bid);
  }, [onToggleAskExpanded, element_bid]);

  const handleToggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev);
  }, []);

  const focusAskInput = useCallback(() => {
    // Auto focus the follow-up textarea so the cursor is ready after expanding
    // if (!inputWrapperRef.current) {
    //   return null;
    // }
    // const focusable = inputWrapperRef.current.querySelector<
    //   HTMLTextAreaElement | HTMLInputElement | HTMLElement
    // >('textarea, input, [contenteditable="true"]');
    // if (focusable && typeof focusable.focus === 'function') {
    //   return requestAnimationFrame(() => {
    //     focusable.focus({ preventScroll: true });
    //   });
    // }
    // return null;
  }, []);

  useEffect(() => {
    if (!expanded) {
      return;
    }
    const rafId = focusAskInput() ?? null;
    return () => {
      // Cancel RAF to avoid focusing after unmount or quick collapse
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [expanded, focusAskInput]);

  const handleClickTitle = useCallback(
    (index: number) => {
      if (index !== 0 || expanded || !mobileStyle) {
        return;
      }
      onToggleAskExpanded?.(element_bid);
    },
    [onToggleAskExpanded, element_bid, expanded, mobileStyle],
  );

  const renderMessages = ({
    extraClass,
  }: {
    extraClass?: string;
  } = {}) => {
    if (messagesToShow.length === 0) {
      return null;
    }

    return (
      <div
        className={cn(styles.messageList, extraClass)}
        style={
          !mobileStyle
            ? {
                marginBottom: expanded ? '12px' : '0',
              }
            : undefined
        }
      >
        {messagesToShow.map((message, index) => (
          <div
            key={index}
            className={cn(styles.messageWrapper)}
            onClick={() => handleClickTitle(index)}
            style={{
              justifyContent:
                message.type === BLOCK_TYPE.ASK ? 'flex-end' : 'flex-start',
            }}
          >
            {message.type === BLOCK_TYPE.ASK ? (
              <div
                className={cn(
                  styles.userMessage,
                  expanded && styles.isExpanded,
                )}
              >
                {message.content}
              </div>
            ) : (
              <div
                className={cn(styles.assistantMessage, styles.askIframeWrapper)}
              >
                <ContentRender
                  content={message.content}
                  customRenderBar={
                    message.isStreaming && !message.content
                      ? () => <LoadingBar />
                      : () => null
                  }
                  onSend={() => {}}
                  userInput={''}
                  interactionDefaultValueOptions={
                    lessonFeedbackInteractionDefaultValueOptions
                  }
                  enableTypewriter={false}
                  typingSpeed={20}
                  readonly={true}
                  copyButtonText={copyButtonText}
                  copiedButtonText={copiedButtonText}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderInput = (extraClass?: string) => {
    if (!expanded) {
      return null;
    }

    return (
      <div
        className={cn(extraClass)}
        ref={inputWrapperRef}
      >
        <MarkdownFlowInput
          placeholder={t('module.chat.askContent')}
          value={inputValue}
          onChange={handleInputChange}
          onSend={handleSendCustomQuestion}
          className={cn(
            styles.inputGroup,
            isStreamingRef.current ? styles.isSending : '',
          )}
        />
      </div>
    );
  };

  if (
    mobileStyle &&
    shouldShowMobileDialog &&
    (messagesToShow.length > 0 || shouldForceSlideMobileDialog)
  ) {
    return (
      <div className={cn(styles.askBlock, className, styles.mobile)}>
        {!expanded && renderMessages()}
        {expanded && (
          <>
            <div
              className={styles.mobileOverlay}
              onClick={handleClose}
            />
            <div
              className={cn(
                styles.mobilePanel,
                isFullscreen ? styles.mobilePanelFullscreen : '',
              )}
            >
              <div className={styles.mobileHeader}>
                <div className={styles.mobileTitle}>
                  {courseAvatar && (
                    <Avatar className='w-7 h-7 mr-2'>
                      <AvatarImage src={courseAvatar} />
                    </Avatar>
                  )}
                  <span>{t('module.chat.ask')}</span>
                </div>
                <div className={styles.mobileActions}>
                  <button
                    type='button'
                    className={styles.mobileActionButton}
                    onClick={handleToggleFullscreen}
                    aria-label={isFullscreen ? 'Collapse' : 'Expand'}
                  >
                    {isFullscreen ? (
                      <Minimize2 size={18} />
                    ) : (
                      <Maximize2 size={18} />
                    )}
                  </button>
                  <button
                    type='button'
                    className={styles.mobileActionButton}
                    onClick={handleClose}
                    aria-label='Close'
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>
              <div
                className={cn(
                  styles.mobileContent,
                  !hasAskAnswerMessages && styles.mobileContentHidden,
                )}
                ref={mobileContentRef}
              >
                {renderMessages({
                  extraClass: styles.mobileMessageList,
                })}
              </div>
              {renderInput(styles.mobileInput)}
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        styles.askBlock,
        className,
        mobileStyle ? styles.mobile : '',
      )}
      style={
        isSlideAskBlock
          ? undefined
          : {
              marginTop: expanded || messagesToShow.length > 0 ? '8px' : '0',
              padding: expanded || messagesToShow.length > 0 ? '16px' : '0',
            }
      }
    >
      {renderMessages()}
      {renderInput()}
    </div>
  );
}
