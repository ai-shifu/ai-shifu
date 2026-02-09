import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
  useContext,
  useMemo,
} from 'react';
import React from 'react';
import { useLatest, useMountedState } from 'react-use';
import {
  fixMarkdownStream,
  maskIncompleteMermaidBlock,
} from '@/c-utils/markdownUtils';
import { useCourseStore } from '@/c-store/useCourseStore';
import { useUserStore } from '@/store';
import { useShallow } from 'zustand/react/shallow';
import {
  StudyRecordItem,
  LikeStatus,
  AudioCompleteData,
  type AudioSegmentData,
  getRunMessage,
  SSE_INPUT_TYPE,
  getLessonStudyRecord,
  SSE_OUTPUT_TYPE,
  SYS_INTERACTION_TYPE,
  LIKE_STATUS,
  BLOCK_TYPE,
  BlockType,
  checkIsRunning,
  streamGeneratedBlockAudio,
} from '@/c-api/studyV2';
import {
  upsertAudioComplete,
  upsertAudioCompleteByPosition,
  upsertAudioSegment,
  upsertAudioSegmentByPosition,
  type AudioSegment,
} from '@/c-utils/audio-utils';
import { LESSON_STATUS_VALUE } from '@/c-constants/courseConstants';
import {
  events,
  EVENT_NAMES as BZ_EVENT_NAMES,
} from '@/app/c/[[...id]]/events';
import { EVENT_NAMES } from '@/c-common/hooks/useTracking';
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { createInteractionParser } from 'remark-flow';
import LoadingBar from './LoadingBar';
import type { PreviewVariablesMap } from '@/components/lesson-preview/variableStorage';
import { useTranslation } from 'react-i18next';
import { show as showToast } from '@/hooks/useToast';
import AskIcon from '@/c-assets/newchat/light/icon_ask.svg';
import { AppContext } from '../AppContext';
import { appendCustomButtonAfterContent } from './chatUiUtils';

interface InteractionParseResult {
  variableName?: string;
  buttonTexts?: string[];
  buttonValues?: string[];
  placeholder?: string;
  isMultiSelect?: boolean;
}

interface InteractionDefaultValues {
  buttonText?: string;
  inputText?: string;
  selectedValues?: string[];
}

export enum ChatContentItemType {
  CONTENT = 'content',
  INTERACTION = 'interaction',
  ASK = 'ask',
  LIKE_STATUS = 'likeStatus',
}

export interface ChatContentItem {
  content?: string;
  customRenderBar?: (() => React.ReactNode | null) | ComponentType<any>;
  defaultButtonText?: string;
  defaultInputText?: string;
  defaultSelectedValues?: string[]; // for multi-select interactions
  readonly?: boolean;
  isHistory?: boolean;
  generated_block_bid: string;
  ask_generated_block_bid?: string; // use for ask block, because an interaction block gid isn't ask gid
  parent_block_bid?: string; // when like_status is not none, the parent_block_bid is the generated_block_bid of the interaction block
  like_status?: LikeStatus;
  type: ChatContentItemType | BlockType;
  ask_list?: ChatContentItem[]; // list of ask records for this content block
  isAskExpanded?: boolean; // whether the ask panel is expanded
  generateTime?: number;
  variables?: PreviewVariablesMap;
  // Audio properties for TTS
  audioUrl?: string;
  audioSegments?: AudioSegment[];
  isAudioStreaming?: boolean;
  audioDurationMs?: number;
  // Segmented AV TTS (multiple audios per generated block)
  audios?: AudioCompleteData[];
  audioTracksByPosition?: Record<
    number,
    {
      audioUrl?: string;
      audioSegments?: AudioSegment[];
      isAudioStreaming?: boolean;
      audioDurationMs?: number;
      audioBid?: string;
    }
  >;
}

interface SSEParams {
  input: string | Record<string, any>;
  input_type: SSE_INPUT_TYPE;
  reload_generated_block_bid?: string;
}

export interface UseChatSessionParams {
  shifuBid: string;
  outlineBid: string;
  lessonId: string;
  chapterId?: string;
  previewMode?: boolean;
  isListenMode?: boolean;
  trackEvent: (name: string, payload?: Record<string, any>) => void;
  trackTrailProgress: (courseId: string, generatedBlockBid: string) => void;
  lessonUpdate?: (params: Record<string, any>) => void;
  chapterUpdate?: (params: Record<string, any>) => void;
  updateSelectedLesson: (lessonId: string, forceExpand?: boolean) => void;
  getNextLessonId: (lessonId?: string | null) => string | null;
  scrollToLesson: (lessonId: string) => void;
  // scrollToBottom: (behavior?: ScrollBehavior) => void;
  showOutputInProgressToast: () => void;
  onPayModalOpen: () => void;
  chatBoxBottomRef: React.RefObject<HTMLDivElement | null>;
  onGoChapter: (lessonId: string) => void;
}

export interface UseChatSessionResult {
  items: ChatContentItem[];
  isLoading: boolean;
  onSend: (content: OnSendContentParams, blockBid: string) => void;
  onRefresh: (generatedBlockBid: string) => void;
  toggleAskExpanded: (parentBlockBid: string) => void;
  requestAudioForBlock: (
    generatedBlockBid: string,
  ) => Promise<AudioCompleteData | null>;
  reGenerateConfirm: {
    open: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  };
}

/**
 * useChatLogicHook orchestrates the streaming chat lifecycle for lesson content.
 */
function useChatLogicHook({
  shifuBid,
  onGoChapter,
  outlineBid,
  lessonId,
  chapterId,
  previewMode,
  isListenMode = false,
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
}: UseChatSessionParams): UseChatSessionResult {
  const { t, i18n, ready } = useTranslation();
  const { mobileStyle } = useContext(AppContext);

  const { updateUserInfo } = useUserStore(
    useShallow(state => ({
      updateUserInfo: state.updateUserInfo,
    })),
  );
  const isStreamingRef = useRef(false);
  const { updateResetedChapterId, updateResetedLessonId, resetedLessonId } =
    useCourseStore(
      useShallow(state => ({
        resetedLessonId: state.resetedLessonId,
        updateResetedChapterId: state.updateResetedChapterId,
        updateResetedLessonId: state.updateResetedLessonId,
      })),
    );

  const [contentList, setContentList] = useState<ChatContentItem[]>([]);
  // const [isTypeFinished, setIsTypeFinished] = useState(false);
  const isTypeFinishedRef = useRef(false);
  const [isLoading, setIsLoading] = useState(true);
  const isInitHistoryRef = useRef(true);
  // const [lastInteractionBlock, setLastInteractionBlock] =
  //   useState<ChatContentItem | null>(null);
  const [loadedChapterId, setLoadedChapterId] = useState('');

  const contentListRef = useRef<ChatContentItem[]>([]);
  const currentContentRef = useRef<string>('');
  const currentBlockIdRef = useRef<string | null>(null);
  const runRef = useRef<((params: SSEParams) => void) | null>(null);
  const interactionParserRef = useRef(createInteractionParser());
  const sseRef = useRef<any>(null);
  const ttsSseRef = useRef<Record<string, any>>({});
  const lastInteractionBlockRef = useRef<ChatContentItem | null>(null);
  const hasScrolledToBottomRef = useRef<boolean>(false);
  const [pendingRegenerate, setPendingRegenerate] = useState<{
    content: OnSendContentParams;
    blockBid: string;
  } | null>(null);
  const [showRegenerateConfirm, setShowRegenerateConfirm] = useState(false);

  const effectivePreviewMode = previewMode ?? false;
  const allowTtsStreaming = !effectivePreviewMode;
  const getAskButtonMarkup = useCallback(
    () =>
      `<custom-button-after-content><img src="${AskIcon.src}" alt="ask" width="14" height="14" /><span>${t('module.chat.ask')}</span></custom-button-after-content>`,
    [t],
  );

  const parseInteractionBlock = useCallback(
    (content?: string | null): InteractionParseResult | null => {
      if (!content) {
        return null;
      }
      try {
        return interactionParserRef.current.parseToRemarkFormat(
          content,
        ) as InteractionParseResult;
      } catch (error) {
        console.warn('Failed to parse interaction block', error);
        return null;
      }
    },
    [],
  );

  const normalizeButtonValue = useCallback(
    (
      token: string,
      info: InteractionParseResult,
    ): { value: string; display?: string } | null => {
      if (!token) {
        return null;
      }
      const cleaned = token.trim();
      const buttonValues = info.buttonValues || [];
      const buttonTexts = info.buttonTexts || [];
      const valueIndex = buttonValues.indexOf(cleaned);
      if (valueIndex > -1) {
        return {
          value: buttonValues[valueIndex],
          display: buttonTexts[valueIndex],
        };
      }
      const textIndex = buttonTexts.indexOf(cleaned);
      if (textIndex > -1) {
        return {
          value: buttonValues[textIndex] || buttonTexts[textIndex],
          display: buttonTexts[textIndex],
        };
      }
      return null;
    },
    [],
  );

  const splitPresetValues = useCallback((raw: string) => {
    return raw
      .split(/[,，\n]/)
      .map(item => item.trim())
      .filter(Boolean);
  }, []);

  const getInteractionDefaultValues = useCallback(
    (
      content?: string | null,
      rawValue?: string | null,
    ): InteractionDefaultValues => {
      const normalized = rawValue?.toString().trim();
      if (!normalized) {
        return {};
      }

      const interactionInfo = parseInteractionBlock(content);
      if (!interactionInfo) {
        return {
          buttonText: normalized,
          inputText: normalized,
        };
      }

      if (interactionInfo.isMultiSelect) {
        const tokens = splitPresetValues(normalized);
        if (!tokens.length) {
          return {};
        }
        const selectedValues: string[] = [];
        const customInputs: string[] = [];
        tokens.forEach(token => {
          const mapped = normalizeButtonValue(token, interactionInfo);
          if (mapped) {
            selectedValues.push(mapped.value);
          } else if (interactionInfo.placeholder) {
            customInputs.push(token);
          } else {
            selectedValues.push(token);
          }
        });
        return {
          selectedValues: selectedValues.length ? selectedValues : undefined,
          inputText: customInputs.length ? customInputs.join(', ') : undefined,
        };
      }

      const mapped = normalizeButtonValue(normalized, interactionInfo);
      if (mapped) {
        return {
          buttonText: mapped.value || mapped.display || normalized,
        };
      }

      if (interactionInfo.placeholder) {
        return {
          inputText: normalized,
        };
      }

      return {
        buttonText: normalized,
        inputText: normalized,
      };
    },
    [normalizeButtonValue, parseInteractionBlock, splitPresetValues],
  );

  // Use react-use hooks for safer state management
  const isMounted = useMountedState();
  const chatBoxBottomRefLatest = useLatest(chatBoxBottomRef);

  /**
   * Auto scroll to bottom when history records are loaded and rendered
   * Only scroll once, don't interfere with user scrolling
   */
  // useEffect(() => {
  //   // Only scroll once after initial load
  //   if (hasScrolledToBottomRef.current) {
  //     return;
  //   }

  //   // Wait for: 1) loading complete, 2) has content, 3) chapter loaded
  //   if (!isLoading && contentList.length > 0 && loadedChapterId) {
  //     // Simple one-time scroll after a reasonable delay
  //     const timer = setTimeout(() => {
  //       if (!isMounted()) return;

  //       const bottomEl = chatBoxBottomRefLatest.current?.current;
  //       if (bottomEl) {
  //         // Use instant scroll to avoid blocking user interaction
  //         bottomEl.scrollIntoView({
  //           behavior: 'auto',
  //           block: 'end',
  //         });
  //         hasScrolledToBottomRef.current = true;
  //       }
  //     }, 300);

  //     return () => clearTimeout(timer);
  //   }
  // }, [
  //   isLoading,
  //   contentList.length,
  //   loadedChapterId,
  //   isMounted,
  //   chatBoxBottomRefLatest,
  // ]);

  /**
   * Keeps the React state and mutable ref of the content list in sync.
   */
  const setTrackedContentList = useCallback(
    (
      updater:
        | ChatContentItem[]
        | ((prev: ChatContentItem[]) => ChatContentItem[]),
    ) => {
      setContentList(prev => {
        const next =
          typeof updater === 'function'
            ? (updater as (prev: ChatContentItem[]) => ChatContentItem[])(prev)
            : updater;
        contentListRef.current = next;
        return next;
      });
    },
    [],
  );

  /**
   * Applies stream-driven lesson status updates and triggers follow-up actions.
   */
  const lessonUpdateResp = useCallback(
    (response, isEnd: boolean) => {
      const {
        outline_bid: currentOutlineBid,
        status,
        title,
      } = response.content;
      lessonUpdate?.({
        id: currentOutlineBid,
        name: title,
        status,
        status_value: status,
      });
      if (status === LESSON_STATUS_VALUE.PREPARE_LEARNING && !isEnd) {
        runRef.current?.({
          input: '',
          input_type: SSE_INPUT_TYPE.NORMAL,
        });
      }

      if (status === LESSON_STATUS_VALUE.LEARNING && !isEnd) {
        updateSelectedLesson(currentOutlineBid);
      }
    },
    [lessonUpdate, updateSelectedLesson],
  );

  /**
   * Starts the SSE request and streams content into the chat list.
   */
  const run = useCallback(
    (sseParams: SSEParams) => {
      // setIsTypeFinished(false);
      isTypeFinishedRef.current = false;
      isInitHistoryRef.current = false;
      // currentBlockIdRef.current = 'loading';
      currentContentRef.current = '';
      // setLastInteractionBlock(null);
      lastInteractionBlockRef.current = null;
      if (!isListenMode) {
        setTrackedContentList(prev => {
          const hasLoading = prev.some(
            item => item.generated_block_bid === 'loading',
          );
          if (hasLoading) {
            return prev;
          }
          const placeholderItem: ChatContentItem = {
            generated_block_bid: 'loading',
            content: '',
            customRenderBar: () => <LoadingBar />,
            type: ChatContentItemType.CONTENT,
          };
          return [...prev, placeholderItem];
        });
      }

      let isEnd = false;

      const source = getRunMessage(
        shifuBid,
        outlineBid,
        effectivePreviewMode,
        // Listen Mode now relies on on-demand segmented TTS (`listen=true`) for AV sync.
        // Keep run SSE free of TTS to avoid generating a single merged track.
        { ...sseParams, listen: false },
        async response => {
          // if (response.type === SSE_OUTPUT_TYPE.HEARTBEAT) {
          //   if (!isEnd) {
          //     currentBlockIdRef.current = 'loading';
          //     setTrackedContentList(prev => {
          //       const hasLoading = prev.some(
          //         item => item.generated_block_bid === 'loading',
          //       );
          //       if (hasLoading) {
          //         return prev;
          //       }
          //       const placeholderItem: ChatContentItem = {
          //         generated_block_bid: 'loading',
          //         content: '',
          //         customRenderBar: () => <LoadingBar />,
          //         type: ChatContentItemType.CONTENT,
          //       };
          //       return [...prev, placeholderItem];
          //     });
          //   }
          //   return;
          // }
          try {
            const nid = response.generated_block_bid;
            if (
              // currentBlockIdRef.current === 'loading' &&
              response.type === SSE_OUTPUT_TYPE.INTERACTION ||
              response.type === SSE_OUTPUT_TYPE.CONTENT
            ) {
              if (
                contentListRef.current?.some(
                  item => item.generated_block_bid === 'loading',
                )
              ) {
                // currentBlockIdRef.current = nid;
                // close loading
                setTrackedContentList(pre => {
                  const newList = pre.filter(
                    item => item.generated_block_bid !== 'loading',
                  );
                  return newList;
                });
              }
            }
            const blockId = nid;
            // const blockId = currentBlockIdRef.current;

            if (blockId && [SSE_OUTPUT_TYPE.BREAK].includes(response.type)) {
              trackTrailProgress(shifuBid, blockId);
            }

            if (response.type === SSE_OUTPUT_TYPE.INTERACTION) {
              setTrackedContentList((prev: ChatContentItem[]) => {
                // Use markdown-flow-ui default rendering for all interactions
                const interactionBlock: ChatContentItem = {
                  generated_block_bid: nid,
                  content: response.content,
                  customRenderBar: () => null,
                  defaultButtonText: '',
                  defaultInputText: '',
                  readonly: false,
                  type: ChatContentItemType.INTERACTION,
                };
                const lastContent = prev[prev.length - 1];
                if (
                  lastContent &&
                  lastContent.type === ChatContentItemType.CONTENT
                ) {
                  const likeStatusItem: ChatContentItem = {
                    parent_block_bid: lastContent.generated_block_bid || '',
                    generated_block_bid: '',
                    content: '',
                    like_status: LIKE_STATUS.NONE,
                    type: ChatContentItemType.LIKE_STATUS,
                  };
                  return [...prev, likeStatusItem, interactionBlock];
                } else {
                  return [...prev, interactionBlock];
                }
              });
            } else if (response.type === SSE_OUTPUT_TYPE.CONTENT) {
              if (isEnd) {
                return;
              }

              const prevText = currentContentRef.current || '';
              const delta = fixMarkdownStream(prevText, response.content || '');
              const nextText = prevText + delta;
              currentContentRef.current = nextText;
              const displayText = maskIncompleteMermaidBlock(nextText);
              if (blockId) {
                setTrackedContentList(prevState => {
                  let hasItem = false;
                  const updatedList = prevState.map(item => {
                    if (item.generated_block_bid === blockId) {
                      hasItem = true;
                      return {
                        ...item,
                        content: displayText,
                        customRenderBar: () => null,
                      };
                    }
                    return item;
                  });
                  if (!hasItem) {
                    updatedList.push({
                      generated_block_bid: blockId,
                      content: displayText,
                      defaultButtonText: '',
                      defaultInputText: '',
                      readonly: false,
                      customRenderBar: () => null,
                      type: ChatContentItemType.CONTENT,
                    });
                  }
                  return updatedList;
                });
              }
            } else if (response.type === SSE_OUTPUT_TYPE.OUTLINE_ITEM_UPDATE) {
              const { status, outline_bid } = response.content;
              if (response.content.has_children) {
                // only update current chapter
                if (outline_bid && outline_bid === chapterId) {
                  chapterUpdate?.({
                    id: outline_bid,
                    status,
                    status_value: status,
                  });
                  if (status === LESSON_STATUS_VALUE.COMPLETED) {
                    isEnd = true;
                  }
                }
              } else {
                // only update current lesson
                if (outline_bid && outline_bid === lessonId) {
                  lessonUpdateResp(response, isEnd);
                }
              }
            } else if (
              // response.type === SSE_OUTPUT_TYPE.BREAK ||
              response.type === SSE_OUTPUT_TYPE.TEXT_END
            ) {
              setTrackedContentList((prev: ChatContentItem[]) => {
                const updatedList = [...prev].filter(
                  item => item.generated_block_bid !== 'loading',
                );
                // Find the last CONTENT type item and append AskButton to its content
                // Set isHistory=true to prevent triggering typewriter effect for AskButton
                if (mobileStyle && !isListenMode) {
                  for (let i = updatedList.length - 1; i >= 0; i--) {
                    if (
                      updatedList[i].type === ChatContentItemType.CONTENT &&
                      !updatedList[i].content?.includes(
                        `<custom-button-after-content>`,
                      )
                    ) {
                      updatedList[i] = {
                        ...updatedList[i],
                        content: appendCustomButtonAfterContent(
                          updatedList[i].content,
                          getAskButtonMarkup(),
                        ),
                        isHistory: true, // Prevent AskButton from triggering typewriter
                      };
                      break;
                    }
                  }
                }

                // Add interaction blocks - use captured value instead of ref
                const lastItem = updatedList[updatedList.length - 1];
                const gid = lastItem?.generated_block_bid || '';
                if (lastItem && lastItem.type === ChatContentItemType.CONTENT) {
                  updatedList.push({
                    parent_block_bid: gid,
                    generated_block_bid: '',
                    content: '',
                    like_status: LIKE_STATUS.NONE,
                    type: ChatContentItemType.LIKE_STATUS,
                  });
                  // sseRef.current?.close();
                  runRef.current?.({
                    input: '',
                    input_type: SSE_INPUT_TYPE.NORMAL,
                  });
                }
                return updatedList;
              });
            } else if (response.type === SSE_OUTPUT_TYPE.VARIABLE_UPDATE) {
              if (response.content.variable_name === 'sys_user_nickname') {
                updateUserInfo({
                  name: response.content.variable_value,
                });
              }
            } else if (response.type === SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
              if (!allowTtsStreaming) {
                return;
              }
              // Handle audio segment during TTS streaming
              const audioSegment = response.content as AudioSegmentData;
              if (blockId) {
                setTrackedContentList(prevState =>
                  upsertAudioSegment(prevState, blockId, audioSegment),
                );
              }
            } else if (response.type === SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
              if (!allowTtsStreaming) {
                return;
              }
              // Handle audio completion with OSS URL
              const audioComplete = response.content as AudioCompleteData;
              if (blockId) {
                setTrackedContentList(prevState =>
                  upsertAudioComplete(prevState, blockId, audioComplete),
                );
              }
            }
          } catch (error) {
            console.warn('SSE handling error:', error);
          }
        },
      );
      source.addEventListener('readystatechange', () => {
        // readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
        if (source.readyState === 1) {
          isStreamingRef.current = true;
        }
        if (source.readyState === 2) {
          isStreamingRef.current = false;
        }
      });
      source.addEventListener('error', () => {
        setTrackedContentList(prev => {
          return prev.filter(item => item.generated_block_bid !== 'loading');
        });
        isStreamingRef.current = false;
      });
      sseRef.current = source;
    },
    [
      chapterUpdate,
      effectivePreviewMode,
      isListenMode,
      lessonUpdateResp,
      outlineBid,
      isTypeFinishedRef,
      setTrackedContentList,
      shifuBid,
      lessonId,
      mobileStyle,
      trackTrailProgress,
      allowTtsStreaming,
      updateUserInfo,
    ],
  );

  useEffect(() => {
    return () => {
      sseRef.current?.close();
    };
  }, []);

  useEffect(() => {
    runRef.current = run;
  }, [run]);

  /**
   * Transforms persisted study records into chat-friendly content items.
   */
  const mapRecordsToContent = useCallback(
    (records: StudyRecordItem[]) => {
      const result: ChatContentItem[] = [];
      let buffer: StudyRecordItem[] = []; // cache consecutive ask entries
      let lastContentId: string | null = null;

      const flushBuffer = () => {
        if (buffer.length > 0) {
          const parentId = lastContentId || '';
          result.push({
            generated_block_bid: '',
            type: BLOCK_TYPE.ASK,
            isAskExpanded: !mobileStyle && buffer.length > 0,
            parent_block_bid: parentId,
            ask_list: buffer.map(item => ({
              ...item,
              type: item.block_type,
            })), // keep the original ask list
            readonly: false,
            isHistory: true,
            customRenderBar: () => null,
            defaultButtonText: '',
            defaultInputText: '',
          });
          buffer = [];
        }
      };

      records.forEach((item: StudyRecordItem) => {
        if (item.block_type === BLOCK_TYPE.CONTENT) {
          // flush the previously cached ask entries
          flushBuffer();
          const normalizedContent = item.content ?? '';
          const contentWithButton =
            mobileStyle && !isListenMode
              ? appendCustomButtonAfterContent(
                  normalizedContent,
                  getAskButtonMarkup(),
                )
              : normalizedContent;
          result.push({
            generated_block_bid: item.generated_block_bid,
            content: contentWithButton,
            customRenderBar: () => null,
            defaultButtonText: item.user_input || '',
            defaultInputText: item.user_input || '',
            readonly: false,
            isHistory: true,
            type: item.block_type,
            // Include audio URL from history
            audioUrl: item.audio_url,
            audios: item.audios,
            audioTracksByPosition: item.audios
              ? item.audios.reduce(
                  (acc, audio) => {
                    const position = Number(audio.position ?? 0);
                    if (Number.isNaN(position)) {
                      return acc;
                    }
                    acc[position] = {
                      audioUrl: audio.audio_url,
                      audioDurationMs: audio.duration_ms,
                      audioBid: audio.audio_bid,
                      isAudioStreaming: false,
                    };
                    return acc;
                  },
                  {} as NonNullable<ChatContentItem['audioTracksByPosition']>,
                )
              : undefined,
          });
          lastContentId = item.generated_block_bid;

          if (item.like_status) {
            result.push({
              generated_block_bid: '',
              parent_block_bid: item.generated_block_bid,
              like_status: item.like_status,
              type: ChatContentItemType.LIKE_STATUS,
            });
          }
        } else if (
          item.block_type === BLOCK_TYPE.ASK ||
          item.block_type === BLOCK_TYPE.ANSWER
        ) {
          // accumulate ask entries
          buffer.push(item);
        } else {
          // flush and handle other types (including INTERACTION)
          flushBuffer();

          const interactionDefaults =
            item.block_type === BLOCK_TYPE.INTERACTION
              ? getInteractionDefaultValues(item.content, item.user_input)
              : null;

          // Use markdown-flow-ui default rendering for all interactions
          result.push({
            generated_block_bid: item.generated_block_bid,
            content: item.content,
            customRenderBar: () => null,
            defaultButtonText: interactionDefaults
              ? (interactionDefaults.buttonText ?? '')
              : item.user_input || '',
            defaultInputText: interactionDefaults
              ? (interactionDefaults.inputText ?? '')
              : item.user_input || '',
            defaultSelectedValues: interactionDefaults
              ? interactionDefaults.selectedValues
              : item.user_input
                ? item.user_input
                    .split(',')
                    .map(v => v.trim())
                    .filter(v => v)
                : undefined,
            readonly: false,
            isHistory: true,
            type: item.block_type,
          });
        }
      });

      // final flush
      flushBuffer();
      return result;
    },
    [mobileStyle, t],
  );

  /**
   * Loads the persisted lesson records and primes the chat stream.
   */
  const refreshData = useCallback(async () => {
    setTrackedContentList(() => []);

    // setIsTypeFinished(true);
    isTypeFinishedRef.current = true;
    lastInteractionBlockRef.current = null;
    setIsLoading(true);
    hasScrolledToBottomRef.current = false;
    isInitHistoryRef.current = true;

    try {
      const recordResp = await getLessonStudyRecord({
        shifu_bid: shifuBid,
        outline_bid: outlineBid,
        preview_mode: effectivePreviewMode,
      });

      if (recordResp?.records?.length > 0) {
        const contentRecords = mapRecordsToContent(recordResp.records);
        setTrackedContentList(contentRecords);
        // setIsTypeFinished(true);
        isTypeFinishedRef.current = true;
        if (chapterId) {
          setLoadedChapterId(chapterId);
        }
        if (
          recordResp.records[recordResp.records.length - 1].block_type ===
            BLOCK_TYPE.CONTENT ||
          recordResp.records[recordResp.records.length - 1].block_type ===
            BLOCK_TYPE.ERROR
        ) {
          runRef.current?.({
            input: '',
            input_type: SSE_INPUT_TYPE.NORMAL,
          });
        }
      } else {
        runRef.current?.({
          input: '',
          input_type: SSE_INPUT_TYPE.NORMAL,
        });
        if (!effectivePreviewMode) {
          trackEvent('learner_lesson_start', {
            shifu_bid: shifuBid,
            outline_bid: outlineBid,
          });
        }
      }
    } catch (error) {
      console.warn('refreshData error:', error);
    } finally {
      setIsLoading(false);
    }
  }, [
    chapterId,
    mapRecordsToContent,
    outlineBid,
    // scrollToBottom,
    setTrackedContentList,
    shifuBid,
    // lessonId,
    effectivePreviewMode,
  ]);

  useEffect(() => {
    if (!chapterId) {
      return;
    }
    if (loadedChapterId === chapterId) {
      return;
    }
    setLoadedChapterId(chapterId);
  }, [chapterId, loadedChapterId]);

  useEffect(() => {
    const unsubscribe = useCourseStore.subscribe(
      state => state.resetedLessonId,
      async curr => {
        if (!curr) {
          return;
        }
        setIsLoading(true);
        if (curr === lessonId) {
          sseRef.current?.close();
          await refreshData();
          // updateResetedChapterId(null);
          // @ts-expect-error resetedLessonId can be null per store design
          updateResetedLessonId(null);
        }
        setIsLoading(false);
      },
    );

    return () => {
      unsubscribe();
    };
  }, [
    loadedChapterId,
    refreshData,
    updateResetedLessonId,
    resetedLessonId,
    lessonId,
  ]);

  useEffect(() => {
    const unsubscribe = useUserStore.subscribe(
      state => state.isLoggedIn,
      isLoggedIn => {
        if (!isLoggedIn || !chapterId) {
          return;
        }
        setLoadedChapterId(chapterId);
        refreshData();
      },
    );

    return () => {
      unsubscribe();
    };
  }, [chapterId, refreshData]);

  useEffect(() => {
    sseRef.current?.close();
    if (!lessonId || resetedLessonId === lessonId) {
      return;
    }
    refreshData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lessonId, resetedLessonId]);

  useEffect(() => {
    const onGoToNavigationNode = (
      event: CustomEvent<{ chapterId: string; lessonId: string }>,
    ) => {
      const { chapterId: targetChapterId, lessonId: targetLessonId } =
        event.detail;
      if (targetChapterId !== loadedChapterId) {
        return;
      }
      // setIsTypeFinished(true);
      isTypeFinishedRef.current = true;
      // setLastInteractionBlock(null);
      lastInteractionBlockRef.current = null;
      scrollToLesson(targetLessonId);
      updateSelectedLesson(targetLessonId);
    };

    events.addEventListener(
      BZ_EVENT_NAMES.GO_TO_NAVIGATION_NODE,
      onGoToNavigationNode as EventListener,
    );

    return () => {
      events.removeEventListener(
        BZ_EVENT_NAMES.GO_TO_NAVIGATION_NODE,
        onGoToNavigationNode as EventListener,
      );
    };
  }, [loadedChapterId, scrollToLesson, updateSelectedLesson]);

  /**
   * updateContentListWithUserOperate rewinds the list to the chosen interaction point.
   */
  const updateContentListWithUserOperate = useCallback(
    (
      params: OnSendContentParams,
      blockBid: string,
    ): { newList: ChatContentItem[]; needChangeItemIndex: number } => {
      const newList = [...contentListRef.current];
      // first find the item with the same variable value
      let needChangeItemIndex = newList.findIndex(item =>
        item.content?.includes(params.variableName || ''),
      );
      // if has multiple items with the same variable value, we need to find the item with the same blockBid
      const sameVariableValueItems =
        newList.filter(item =>
          item.content?.includes(params.variableName || ''),
        ) || [];
      if (sameVariableValueItems.length > 1) {
        needChangeItemIndex = newList.findIndex(
          item => item.generated_block_bid === blockBid,
        );
      }
      if (needChangeItemIndex !== -1) {
        newList[needChangeItemIndex] = {
          ...newList[needChangeItemIndex],
          readonly: false,
          defaultButtonText: params.buttonText || '',
          defaultInputText: params.inputText || '',
          defaultSelectedValues: params.selectedValues,
        };
        if (!isListenMode) {
          newList.length = needChangeItemIndex + 1;
        }
        setTrackedContentList(newList);
      }

      return { newList, needChangeItemIndex };
    },
    [isListenMode, setTrackedContentList],
  );

  /**
   * onRefresh replays a block from the server using the original inputs.
   */
  const onRefresh = useCallback(
    async (generatedBlockBid: string) => {
      if (isStreamingRef.current) {
        showOutputInProgressToast();
        return;
      }

      const runningRes = await checkIsRunning(shifuBid, outlineBid);
      if (runningRes.is_running) {
        showOutputInProgressToast();
        return;
      }

      const newList = [...contentListRef.current];
      const needChangeItemIndex = newList.findIndex(
        item => item.generated_block_bid === generatedBlockBid,
      );
      if (needChangeItemIndex === -1) {
        showOutputInProgressToast();
        return;
      }

      newList.length = needChangeItemIndex;
      setTrackedContentList(newList);

      // setIsTypeFinished(false);
      isTypeFinishedRef.current = false;
      runRef.current?.({
        input: '',
        input_type: SSE_INPUT_TYPE.NORMAL,
        reload_generated_block_bid: generatedBlockBid,
      });
    },
    [
      isTypeFinishedRef,
      outlineBid,
      shifuBid,
      isStreamingRef,
      setTrackedContentList,
      showOutputInProgressToast,
    ],
  );

  /**
   * onSend processes user interactions and continues streaming responses.
   */
  const processSend = useCallback(
    (
      content: OnSendContentParams,
      blockBid: string,
      options?: { skipConfirm?: boolean },
    ) => {
      if (isStreamingRef.current) {
        showOutputInProgressToast();
        return;
      }

      const { variableName, buttonText, inputText } = content;
      if (buttonText === SYS_INTERACTION_TYPE.PAY) {
        trackEvent(EVENT_NAMES.POP_PAY, { from: 'show-btn' });
        onPayModalOpen();
        return;
      }
      if (buttonText === SYS_INTERACTION_TYPE.LOGIN) {
        if (typeof window !== 'undefined') {
          const redirect = encodeURIComponent(
            window.location.pathname + window.location.search,
          );
          window.location.href = `/login?redirect=${redirect}`;
        }
        return;
      }
      if (buttonText === SYS_INTERACTION_TYPE.NEXT_CHAPTER) {
        const nextLessonId = getNextLessonId(lessonId);
        if (nextLessonId) {
          updateSelectedLesson(nextLessonId, true);
          onGoChapter(nextLessonId);
          scrollToLesson(nextLessonId);
        } else {
          showToast(t('module.chat.noMoreLessons'));
        }
        return;
      }

      let isReGenerate = false;
      const currentList = contentListRef.current;
      if (currentList.length > 0) {
        isReGenerate =
          blockBid !== currentList[currentList.length - 1].generated_block_bid;
      }

      if (isReGenerate && !options?.skipConfirm) {
        setPendingRegenerate({ content, blockBid });
        setShowRegenerateConfirm(true);
        return;
      }

      const { newList, needChangeItemIndex } = updateContentListWithUserOperate(
        content,
        blockBid,
      );

      if (needChangeItemIndex === -1) {
        setTrackedContentList(newList);
      }

      // setIsTypeFinished(false);
      isTypeFinishedRef.current = false;
      // scrollToBottom();

      // Build values array from user input (following playground pattern)
      let values: string[] = [];
      if (content.selectedValues && content.selectedValues.length > 0) {
        // Multi-select mode: combine selected values with optional input text
        values = [...content.selectedValues];
        if (inputText) {
          values.push(inputText);
        }
      } else if (inputText) {
        // Single-select mode: use input text
        values = [inputText];
      } else if (buttonText) {
        // Single-select mode: use button text
        values = [buttonText];
      }

      runRef.current?.({
        input: {
          [variableName as string]: values,
        },
        input_type: SSE_INPUT_TYPE.NORMAL,
        reload_generated_block_bid:
          isReGenerate && needChangeItemIndex !== -1
            ? newList[needChangeItemIndex].generated_block_bid
            : undefined,
      });
    },
    [
      getNextLessonId,
      isTypeFinishedRef,
      lessonId,
      onGoChapter,
      onPayModalOpen,
      scrollToLesson,
      setTrackedContentList,
      showOutputInProgressToast,
      trackEvent,
      updateContentListWithUserOperate,
      updateSelectedLesson,
      t,
    ],
  );

  const onSend = useCallback(
    (content: OnSendContentParams, blockBid: string) => {
      processSend(content, blockBid);
    },
    [processSend],
  );

  const handleConfirmRegenerate = useCallback(() => {
    if (!pendingRegenerate) {
      setShowRegenerateConfirm(false);
      return;
    }
    processSend(pendingRegenerate.content, pendingRegenerate.blockBid, {
      skipConfirm: true,
    });
    setPendingRegenerate(null);
    setShowRegenerateConfirm(false);
  }, [pendingRegenerate, processSend]);

  const handleCancelRegenerate = useCallback(() => {
    setPendingRegenerate(null);
    setShowRegenerateConfirm(false);
  }, []);

  /**
   * toggleAskExpanded toggles the expanded state of the ask panel for a specific block
   */
  const toggleAskExpanded = useCallback(
    (parentBlockBid: string) => {
      setTrackedContentList(prev => {
        // Check if ASK block already exists
        const hasAskBlock = prev.some(
          item =>
            item.parent_block_bid === parentBlockBid &&
            item.type === ChatContentItemType.ASK,
        );

        if (hasAskBlock) {
          // Toggle existing ASK block's expanded state
          return prev.map(item =>
            item.parent_block_bid === parentBlockBid &&
            item.type === ChatContentItemType.ASK
              ? { ...item, isAskExpanded: !item.isAskExpanded }
              : item,
          );
        } else {
          // Create new ASK block after LIKE_STATUS block
          return prev.flatMap(item => {
            if (
              item.parent_block_bid === parentBlockBid &&
              item.type === ChatContentItemType.LIKE_STATUS
            ) {
              return [
                item,
                {
                  generated_block_bid: '',
                  parent_block_bid: parentBlockBid,
                  type: BLOCK_TYPE.ASK,
                  content: '',
                  isAskExpanded: true,
                  ask_list: [],
                  readonly: false,
                  customRenderBar: () => null,
                  defaultButtonText: '',
                  defaultInputText: '',
                },
              ];
            }
            return [item];
          });
        }
      });
    },
    [setTrackedContentList],
  );

  // Create a stable null render bar function
  const nullRenderBar = useCallback(() => null, []);

  const items = useMemo(
    () =>
      contentList.map(item => ({
        ...item,
        customRenderBar: item.customRenderBar || nullRenderBar,
      })),
    [contentList, nullRenderBar],
  );

  const closeTtsStream = useCallback((blockId: string) => {
    const source = ttsSseRef.current[blockId];
    if (!source) {
      return;
    }
    source.close();
    delete ttsSseRef.current[blockId];
  }, []);

  const requestAudioForBlock = useCallback(
    async (generatedBlockBid: string): Promise<AudioCompleteData | null> => {
      if (!generatedBlockBid) {
        return null;
      }

      if (!allowTtsStreaming) {
        return null;
      }

      const existingItem = contentListRef.current.find(
        item => item.generated_block_bid === generatedBlockBid,
      );
      if (
        !isListenMode &&
        existingItem?.audioUrl &&
        !existingItem.isAudioStreaming
      ) {
        return {
          audio_url: existingItem.audioUrl,
          audio_bid: '',
          duration_ms: existingItem.audioDurationMs ?? 0,
        };
      }

      if (ttsSseRef.current[generatedBlockBid]) {
        return null;
      }

      setTrackedContentList(prev =>
        prev.map(item => {
          if (item.generated_block_bid !== generatedBlockBid) {
            return item;
          }

          return {
            ...item,
            audioTracksByPosition: isListenMode
              ? {}
              : item.audioTracksByPosition,
            audioSegments: [],
            audioUrl: undefined,
            audioDurationMs: undefined,
            isAudioStreaming: true,
          };
        }),
      );

      return new Promise((resolve, reject) => {
        let resolved = false;
        let firstComplete: AudioCompleteData | null = null;

        const safeResolve = (value: AudioCompleteData | null) => {
          if (resolved) {
            return;
          }
          resolved = true;
          resolve(value);
        };

        const safeReject = (error: unknown) => {
          if (resolved) {
            return;
          }
          resolved = true;
          reject(
            error instanceof Error ? error : new Error('TTS stream failed'),
          );
        };

        const source = streamGeneratedBlockAudio({
          shifu_bid: shifuBid,
          generated_block_bid: generatedBlockBid,
          preview_mode: effectivePreviewMode,
          listen: isListenMode,
          onMessage: response => {
            if (response?.type === SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
              const audioPayload = response.content ?? response.data;
              const position = Number(audioPayload?.position ?? 0);
              setTrackedContentList(prevState =>
                isListenMode
                  ? upsertAudioSegmentByPosition(
                      prevState,
                      generatedBlockBid,
                      Number.isNaN(position) ? 0 : position,
                      audioPayload as AudioSegmentData,
                    )
                  : upsertAudioSegment(
                      prevState,
                      generatedBlockBid,
                      audioPayload as AudioSegmentData,
                    ),
              );
              return;
            }

            if (response?.type === SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
              const audioPayload = response.content ?? response.data;
              const audioComplete = audioPayload as AudioCompleteData;
              const position = Number(audioComplete?.position ?? 0);
              if (!firstComplete) {
                firstComplete = audioComplete;
              }
              setTrackedContentList(prevState =>
                isListenMode
                  ? upsertAudioCompleteByPosition(
                      prevState,
                      generatedBlockBid,
                      Number.isNaN(position) ? 0 : position,
                      audioComplete,
                    )
                  : upsertAudioComplete(
                      prevState,
                      generatedBlockBid,
                      audioComplete,
                    ),
              );
              if (!isListenMode) {
                closeTtsStream(generatedBlockBid);
                safeResolve(audioComplete ?? null);
              }
            }
          },
          onError: () => {
            setTrackedContentList(prev =>
              prev.map(item => {
                if (item.generated_block_bid !== generatedBlockBid) {
                  return item;
                }
                return {
                  ...item,
                  isAudioStreaming: false,
                };
              }),
            );
            closeTtsStream(generatedBlockBid);
            safeReject(new Error('TTS stream failed'));
          },
        });

        source.addEventListener('readystatechange', () => {
          if (!isListenMode) {
            return;
          }
          if (source.readyState !== 2) {
            return;
          }
          setTrackedContentList(prev =>
            prev.map(item => {
              if (item.generated_block_bid !== generatedBlockBid) {
                return item;
              }
              return {
                ...item,
                isAudioStreaming: false,
              };
            }),
          );
          closeTtsStream(generatedBlockBid);
          safeResolve(firstComplete);
        });

        ttsSseRef.current[generatedBlockBid] = source;
      });
    },
    [
      allowTtsStreaming,
      closeTtsStream,
      effectivePreviewMode,
      isListenMode,
      setTrackedContentList,
      shifuBid,
    ],
  );

  useEffect(() => {
    return () => {
      Object.values(ttsSseRef.current).forEach(source => {
        source?.close?.();
      });
      ttsSseRef.current = {};
    };
  }, []);

  return {
    items,
    isLoading,
    onSend,
    onRefresh,
    toggleAskExpanded,
    requestAudioForBlock,
    reGenerateConfirm: {
      open: showRegenerateConfirm,
      onConfirm: handleConfirmRegenerate,
      onCancel: handleCancelRegenerate,
    },
  };
}

export default useChatLogicHook;
