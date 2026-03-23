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
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import {
  normalizeAudioSegmentPayload,
  mergeAudioSegmentByUniqueKey,
  type AudioSegment,
} from '@/c-utils/audio-utils';
export interface AskMessage {
  type: typeof BLOCK_TYPE.ASK | typeof BLOCK_TYPE.ANSWER;
  content: string;
  isStreaming?: boolean;
}

export interface AskBlockProps {
  askList?: AskMessage[];
  className?: string;
  isExpanded?: boolean;
  shifu_bid: string;
  outline_bid: string;
  preview_mode?: boolean;
  element_bid: string;
  isListenMode?: boolean;
  onToggleAskExpanded?: (element_bid: string) => void;
}

const normalizeAskMessages = (askMessages: AskMessage[]): AskMessage[] =>
  askMessages.map(item => ({
    content: item.content || '',
    type: item.type,
    isStreaming: item.isStreaming,
  }));

const isSameAskMessages = (
  left: AskMessage[],
  right: AskMessage[],
): boolean => {
  if (left.length !== right.length) {
    return false;
  }

  return left.every((item, index) => {
    const nextItem = right[index];
    return (
      item.type === nextItem?.type &&
      item.content === nextItem?.content &&
      Boolean(item.isStreaming) === Boolean(nextItem?.isStreaming)
    );
  });
};

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
  isListenMode = false,
  onToggleAskExpanded,
}: AskBlockProps) {
  const { t } = useTranslation();
  const copyButtonText = t('module.renderUi.core.copyCode');
  const copiedButtonText = t('module.renderUi.core.copied');
  const { mobileStyle } = useContext(AppContext);
  const courseAvatar = useCourseStore(state => state.courseAvatar);
  const [askAudioSegments, setAskAudioSegments] = useState<AudioSegment[]>([]);
  const [askAudioUrl, setAskAudioUrl] = useState<string>('');
  const [isAskAudioStreaming, setIsAskAudioStreaming] = useState(false);
  const [displayList, setDisplayList] = useState<AskMessage[]>(() =>
    normalizeAskMessages(askList),
  );

  const [inputValue, setInputValue] = useState('');
  const sseRef = useRef<any>(null);
  const currentContentRef = useRef<string>('');
  const isStreamingRef = useRef(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showMobileDialog, setShowMobileDialog] = useState(askList.length > 0);
  const mobileContentRef = useRef<HTMLDivElement | null>(null);
  const inputWrapperRef = useRef<HTMLDivElement | null>(null);
  const expanded = isExpanded ?? (!mobileStyle && askList.length > 0);
  const showOutputInProgressToast = useCallback(() => {
    toast({
      title: t('module.chat.outputInProgress'),
    });
  }, [t]);

  const handleSendCustomQuestion = useCallback(async () => {
    const question = inputValue.trim();
    if (isStreamingRef.current) {
      showOutputInProgressToast();
      return;
    }

    if (!question) {
      return;
    }
    setAskAudioSegments([]);
    setAskAudioUrl('');
    setIsAskAudioStreaming(false);
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
      },
    ]);

    // Reset the streaming content buffer
    currentContentRef.current = '';
    isStreamingRef.current = true;

    // Initiate the SSE request
    const source = getRunMessage(
      shifu_bid,
      outline_bid,
      preview_mode,
      {
        input: question,
        input_type: SSE_INPUT_TYPE.ASK,
        reload_element_bid: element_bid,
        reload_generated_block_bid: element_bid,
        listen: isListenMode,
      },
      async response => {
        try {
          if (response.type === SSE_OUTPUT_TYPE.HEARTBEAT) {
            return;
          }
          if (response.type === SSE_OUTPUT_TYPE.CONTENT) {
            // Streaming content (non-listen mode)
            const prevText = currentContentRef.current || '';
            const delta = fixMarkdownStream(prevText, response.content || '');
            const nextText = prevText + delta;
            currentContentRef.current = nextText;

            setDisplayList(prev => {
              const newList = [...prev];
              const lastIndex = newList.length - 1;
              if (
                lastIndex >= 0 &&
                newList[lastIndex].type === BLOCK_TYPE.ANSWER
              ) {
                newList[lastIndex] = {
                  ...newList[lastIndex],
                  content: nextText,
                  isStreaming: true,
                };
              }
              return newList;
            });
          } else if (response.type === SSE_OUTPUT_TYPE.ELEMENT) {
            // Listen mode: text content + audio in element patches
            const elementContent = response.content;
            if (elementContent && typeof elementContent === 'object') {
              // Extract text content from element patch
              const textContent = elementContent.content;
              if (typeof textContent === 'string' && textContent) {
                currentContentRef.current = textContent;
                setDisplayList(prev => {
                  const newList = [...prev];
                  const lastIndex = newList.length - 1;
                  if (
                    lastIndex >= 0 &&
                    newList[lastIndex].type === BLOCK_TYPE.ANSWER
                  ) {
                    newList[lastIndex] = {
                      ...newList[lastIndex],
                      content: textContent,
                      isStreaming: true,
                    };
                  }
                  return newList;
                });
              }
              // Extract audio segments from element patch
              const segments = elementContent.audio_segments;
              if (Array.isArray(segments) && segments.length > 0) {
                setIsAskAudioStreaming(true);
                for (const seg of segments) {
                  const normalized = normalizeAudioSegmentPayload(seg);
                  if (normalized) {
                    setAskAudioSegments(prev =>
                      mergeAudioSegmentByUniqueKey(
                        element_bid,
                        prev,
                        normalized,
                      ),
                    );
                  }
                }
              }
              // Extract audio_url from element patch
              if (elementContent.audio_url) {
                setAskAudioUrl(elementContent.audio_url);
                setIsAskAudioStreaming(false);
              }
            }
          } else if (response.type === SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
            const payload = response.content ?? response.data;
            const segment = normalizeAudioSegmentPayload(payload);
            if (segment) {
              setIsAskAudioStreaming(true);
              setAskAudioSegments(prev =>
                mergeAudioSegmentByUniqueKey(element_bid, prev, segment),
              );
            }
          } else if (response.type === SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
            const payload = response.content ?? response.data;
            setAskAudioUrl(payload?.audio_url || '');
            setIsAskAudioStreaming(false);
          } else if (
            response.type === SSE_OUTPUT_TYPE.TEXT_END ||
            response.type === SSE_OUTPUT_TYPE.BREAK
          ) {
            // Streaming finished
            isStreamingRef.current = false;
            setIsAskAudioStreaming(false);
            setDisplayList(prev => {
              const newList = [...prev];
              const lastIndex = newList.length - 1;
              if (
                lastIndex >= 0 &&
                newList[lastIndex].type === BLOCK_TYPE.ANSWER
              ) {
                newList[lastIndex] = {
                  ...newList[lastIndex],
                  isStreaming: false,
                };
              }
              return newList;
            });
            sseRef.current?.close();
          }
        } catch {
          isStreamingRef.current = false;
        }
      },
    );

    // Add error and close listeners to ensure the state resets
    source.addEventListener('error', () => {
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
    });

    source.addEventListener('readystatechange', () => {
      // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
      if (source.readyState === 1) {
        isStreamingRef.current = true;
      } else if (source.readyState === 2) {
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
      }
    });

    sseRef.current = source;
  }, [
    shifu_bid,
    outline_bid,
    preview_mode,
    element_bid,
    inputValue,
    isListenMode,
    showOutputInProgressToast,
  ]);
  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInputValue(e.target.value);
    },
    [],
  );

  // Decide which messages to display
  const messagesToShow = expanded ? displayList : displayList.slice(0, 1);

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
    if (isStreamingRef.current) {
      return;
    }

    const nextDisplayList = normalizeAskMessages(askList);
    setDisplayList(prev =>
      isSameAskMessages(prev, nextDisplayList) ? prev : nextDisplayList,
    );
  }, [askList]);

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
    if (!mobileStyle || !showMobileDialog || !expanded) {
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
  }, [mobileStyle, showMobileDialog, expanded, messagesToShow.length]);

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
                {isListenMode &&
                  index === messagesToShow.length - 1 &&
                  (askAudioSegments.length > 0 || askAudioUrl) && (
                    <AudioPlayer
                      audioUrl={askAudioUrl}
                      streamingSegments={askAudioSegments}
                      isStreaming={isAskAudioStreaming}
                      autoPlay={true}
                      size={14}
                    />
                  )}
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

  if (mobileStyle && showMobileDialog && messagesToShow.length > 0) {
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
                className={styles.mobileContent}
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
      style={{
        marginTop: expanded || messagesToShow.length > 0 ? '8px' : '0',
        padding: expanded || messagesToShow.length > 0 ? '16px' : '0',
      }}
    >
      {renderMessages()}
      {renderInput()}
    </div>
  );
}
