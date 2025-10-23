import React, {
  useState,
  useRef,
  useCallback,
  useContext,
  useEffect,
} from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import { Send, Maximize2, Minimize2, X } from 'lucide-react';
import { ContentRender } from 'markdown-flow-ui';
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
  generated_block_bid: string;
  onToggleAskExpanded?: (generated_block_bid: string) => void;
}

/**
 * AskBlock
 * Follow-up area component that contains the Q&A list and custom input box with streaming support
 */
export default function AskBlock({
  askList = [],
  className,
  isExpanded = false,
  shifu_bid,
  outline_bid,
  preview_mode = false,
  generated_block_bid,
  onToggleAskExpanded,
}: AskBlockProps) {
  const { t } = useTranslation();
  const { mobileStyle } = useContext(AppContext);

  const [displayList, setDisplayList] = useState<AskMessage[]>(() => {
    return askList.map(item => ({
      content: item.content || '',
      type: item.type,
    }));
  });

  const inputRef = useRef<HTMLInputElement>(null);
  const sseRef = useRef<any>(null);
  const currentContentRef = useRef<string>('');
  const isStreamingRef = useRef(false);
  const [isTypeFinished, setIsTypeFinished] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showMobileDialog, setShowMobileDialog] = useState(askList.length > 0);
  const mobileContentRef = useRef<HTMLDivElement | null>(null);
  const showOutputInProgressToast = useCallback(() => {
    toast({
      title: t('chat.outputInProgress'),
    });
  }, [t]);

  const handleSendCustomQuestion = useCallback(async () => {
    const question = inputRef.current?.value.trim() || '';
    if (isStreamingRef.current) {
      showOutputInProgressToast();
      return;
    }

    if (!isTypeFinished) {
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
    setIsTypeFinished(false);
    setShowMobileDialog(true);

    // Append the new question as a user message at the end
    setDisplayList(prev => [
      ...prev,
      {
        type: BLOCK_TYPE.ASK,
        content: question,
      },
    ]);

    // Clear the input box
    if (inputRef.current) {
      inputRef.current.value = '';
    }

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
        reload_generated_block_bid: generated_block_bid,
      },
      async response => {
        try {
          console.log('SSE response:', response);
          if (response.type === SSE_OUTPUT_TYPE.HEARTBEAT) {
            return;
          }
          setIsTypeFinished(false);

          if (response.type === SSE_OUTPUT_TYPE.CONTENT) {
            // Streaming content
            const prevText = currentContentRef.current || '';
            const delta = fixMarkdownStream(prevText, response.content || '');
            const nextText = prevText + delta;
            currentContentRef.current = nextText;

            // Update the content of the last teacher message
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
          }
          // if (
          //   response.type === SSE_OUTPUT_TYPE.BREAK ||
          //   response.type === SSE_OUTPUT_TYPE.TEXT_END ||
          //   response.type === SSE_OUTPUT_TYPE.INTERACTION
          // )
          else {
            // Streaming finished
            console.log('SSE end, close sse:', response);
            isStreamingRef.current = false;
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
        } catch (error) {
          console.warn('SSE handling error:', error);
          isStreamingRef.current = false;
        }
      },
    );

    // Add error and close listeners to ensure the state resets
    source.addEventListener('error', () => {
      console.log('SSE error');
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
      console.log('SSE readystatechange:', source.readyState);
      // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
      if (source.readyState === 2) {
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
    generated_block_bid,
    isTypeFinished,
    showOutputInProgressToast,
  ]);

  // Decide which messages to display
  const messagesToShow = isExpanded ? displayList : displayList.slice(0, 1);
  // console.log('displayList:',isExpanded,messagesToShow);

  useEffect(() => {
    if (!isExpanded) {
      setIsFullscreen(false);
    }
  }, [isExpanded]);

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
    if (!mobileStyle || !isExpanded) {
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
  }, [mobileStyle, isExpanded]);

  useEffect(() => {
    if (!mobileStyle || !showMobileDialog || !isExpanded) {
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
  }, [mobileStyle, showMobileDialog, isExpanded, messagesToShow.length]);

  const handleClose = useCallback(() => {
    setIsFullscreen(false);
    // onClose?.();
    onToggleAskExpanded?.(generated_block_bid);
  }, [onToggleAskExpanded, generated_block_bid]);

  const handleToggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev);
  }, []);

  const handleClickTitle = useCallback(
    (index: number) => {
      if (index !== 0 || isExpanded || !mobileStyle) {
        return;
      }
      onToggleAskExpanded?.(generated_block_bid);
    },
    [onToggleAskExpanded, generated_block_bid, isExpanded, mobileStyle],
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
                marginBottom: isExpanded ? '12px' : '0',
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
                  isExpanded && styles.isExpanded,
                )}
              >
                {message.content}
              </div>
            ) : (
              <div className={cn(styles.assistantMessage)}>
                <ContentRender
                  content={message.content}
                  customRenderBar={
                    message.isStreaming && !message.content
                      ? () => <LoadingBar />
                      : () => null
                  }
                  onSend={() => {}}
                  defaultButtonText={''}
                  defaultInputText={''}
                  enableTypewriter={message.isStreaming === true}
                  typingSpeed={20}
                  readonly={true}
                  onTypeFinished={() => setIsTypeFinished(true)}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const renderInput = (extraClass?: string) => {
    if (!isExpanded) {
      return null;
    }

    return (
      <div className={cn(styles.userInput, extraClass)}>
        <input
          ref={inputRef}
          type='text'
          placeholder={t('chat.askContent')}
          className={cn('flex-1 outline-none border-none bg-transparent')}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              handleSendCustomQuestion();
            }
          }}
        />
        <button
          onClick={handleSendCustomQuestion}
          className={cn(
            'flex items-center justify-center',
            'cursor-pointer',
            isStreamingRef.current || !isTypeFinished ? styles.isSending : '',
          )}
        >
          <Send size={mobileStyle ? 18 : 12} />
        </button>
      </div>
    );
  };

  if (mobileStyle && showMobileDialog && messagesToShow.length > 0) {
    return (
      <div className={cn(styles.askBlock, className, styles.mobile)}>
        {!isExpanded && renderMessages()}
        {isExpanded && (
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
                  <Image
                    src={ShifuIcon.src}
                    alt='shifu icon'
                    width={20}
                    height={20}
                    className={styles.mobileIcon}
                  />
                  <span>{t('chat.ask')}</span>
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
        marginTop: isExpanded || messagesToShow.length > 0 ? '8px' : '0',
        padding: isExpanded || messagesToShow.length > 0 ? '16px' : '0',
      }}
    >
      {renderMessages()}
      {renderInput()}
    </div>
  );
}
