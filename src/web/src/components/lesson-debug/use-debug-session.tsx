'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import type { SSE } from 'sse.js';
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { createInteractionParser, normalizeVariableName } from 'remark-flow';
import {
  ELEMENT_TYPE,
  LIKE_STATUS,
  type AudioCompleteData,
  type ElementType,
  type StudyRecordItem,
} from '@/api/learning';
import { getStringEnv } from '@/lib/env-utils';
import { resolveInteractionSubmission } from '@/lib/interaction-user-input';
import {
  requiresInteractionRewind,
  updateInteractionItems,
} from '@/lib/chat-interaction-rewind';
import { maskIncompleteMermaidBlock } from '@/lib/markdown-utils';
import { debugError, debugWarn } from '@/lib/debug-console';
import {
  getAudioTrackByPosition,
  normalizeAudioCompletePayload,
  normalizeAudioSegmentPayload,
  toAudioSegmentData,
  upsertAudioComplete,
  upsertAudioSegment,
} from '@/lib/audio-utils';
import LoadingBar from '@/components/chat/LoadingBar';
import {
  applyElementToList,
  isLoadingItem,
  LOADING_ITEM_BID,
  matchesElementBid,
  withoutLoadingItem,
} from '@/lib/lesson-stream/content-list';
import {
  readDoneIsTerminal,
  readRunEventError,
} from '@/lib/lesson-stream/run-events';
import { ChatContentItem, ChatContentItemType } from '@/types/chat-ui';
import { normalizeLegacyBlockCompatList } from '@/lib/chat-ui-compat';
import { getDynamicApiBaseUrl } from '@/config/environment';
import { useShifu } from '@/store';
import { toast } from '@/hooks/use-toast';
import {
  resolveLearnerErrorMessage,
  resolveLearnerErrorToast,
} from '@/lib/learner-error';
import { showAiServiceErrorToast } from '@/lib/ai-service-toast';
import {
  type CreditInsufficientAudience,
  getCreditInsufficientMessage,
  isCreditInsufficientBusinessCode,
  showCreditInsufficientToast,
} from '@/lib/credit-insufficient-toast';
import type { ErrorWithCode } from '@/lib/request';
import { onSseData, openSseStream } from '@/lib/sse-client';
import { useTranslation } from 'react-i18next';
import { useTracking } from '@/hooks/use-tracking';
import type {
  DebugRunParams,
  DebugVariableValues,
} from '@/types/debug-session';
import { mergeStoredDebugVariableValues } from './debug-variable-storage';
import {
  buildDebugContinuationParams,
  buildDebugInteractionInput,
  resolveDebugGeneratedBlockBid,
} from './debug-request-params';
import { startDebugAnswerEditTracking } from './debug-answer-edit-tracking';

interface InteractionParseResult {
  variableName?: string;
  buttonTexts?: string[];
  buttonValues?: string[];
  placeholder?: string;
  isMultiSelect?: boolean;
}

type DebugStreamSource = InstanceType<typeof SSE>;
type DebugAnswerEditResult = Parameters<
  NonNullable<ReturnType<typeof startDebugAnswerEditTracking>>
>[0];

// The editor Debug API requires a session ID, so every browser context gets one.
// The server keys a debug session by author, course, lesson and this ID, so the
// fallback only has to differ between this author's Debug runs; it is not a secret.
let fallbackDebugSessionCount = 0;
const createFallbackDebugSessionId = () => {
  fallbackDebugSessionCount += 1;
  return `${Date.now().toString(36)}-${fallbackDebugSessionCount.toString(36)}`;
};

const createDebugSessionId = () => {
  const webCrypto: Partial<Crypto> | undefined = globalThis.crypto;
  if (typeof webCrypto?.randomUUID === 'function') {
    return webCrypto.randomUUID();
  }
  if (typeof webCrypto?.getRandomValues === 'function') {
    const bytes = webCrypto.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join(
      '',
    );
  }
  return createFallbackDebugSessionId();
};

enum DebugStreamEventType {
  DEBUG_VARIABLES = 'debug_variables',
  DEBUG_VARIABLES_COMMITTED = 'debug_variables_committed',
  DEBUG_ENGINE = 'preview_engine',
  ELEMENT = 'element',
  DONE = 'done',
  ERROR = 'error',
  AUDIO_SEGMENT = 'audio_segment',
  AUDIO_COMPLETE = 'audio_complete',
}

type DebugStreamVariableState = {
  awaitingLegacyRewindSeed: boolean;
};

type DebugStreamEvent = {
  type?: string;
  event_type?: string;
  code?: number;
  content?: unknown;
  data?: unknown;
  generated_block_bid?: unknown;
  is_terminal?: unknown;
};

const DEBUG_BUSINESS_ERROR_ITEM_BID = 'preview-business-error';

const parseObjectPayload = <T extends Record<string, unknown>>(
  input: unknown,
): T | null => {
  if (input && typeof input === 'object') {
    return input as T;
  }
  if (typeof input !== 'string') {
    return null;
  }
  const normalized = input.trim();
  if (!normalized) {
    return null;
  }
  const startsAsJsonObject =
    normalized.startsWith('{') || normalized.startsWith('[');
  if (!startsAsJsonObject) {
    return null;
  }
  try {
    const parsed = JSON.parse(normalized);
    if (parsed && typeof parsed === 'object') {
      return parsed as T;
    }
  } catch (error) {
    debugWarn('[lesson-debug] failed to parse Debug stream event', error);
  }
  return null;
};

const resolveResponsePayload = (
  response: DebugStreamEvent,
): Record<string, unknown> | null => {
  return (
    parseObjectPayload<Record<string, unknown>>(response.content) ||
    parseObjectPayload<Record<string, unknown>>(response.data)
  );
};

const resolveElementPayload = (
  response: DebugStreamEvent,
): Partial<StudyRecordItem> | null => {
  return resolveResponsePayload(response) as Partial<StudyRecordItem> | null;
};

const resolveElementBid = (
  elementRecord: Partial<StudyRecordItem> | null,
  response: DebugStreamEvent,
): string => {
  if (!elementRecord) {
    return '';
  }
  if (typeof elementRecord.target_element_bid === 'string') {
    return elementRecord.target_element_bid;
  }
  if (typeof elementRecord.element_bid === 'string') {
    return elementRecord.element_bid;
  }
  if (typeof elementRecord.generated_block_bid === 'string') {
    return elementRecord.generated_block_bid;
  }
  if (typeof response.generated_block_bid === 'string') {
    return response.generated_block_bid;
  }
  return '';
};

const resolveElementType = (
  elementRecord: Partial<StudyRecordItem> | null,
): ElementType | null => {
  if (!elementRecord) {
    return null;
  }
  const rawElementType = elementRecord.element_type;
  if (typeof rawElementType !== 'string') {
    return null;
  }
  return rawElementType.toLowerCase() as ElementType;
};

const resolveElementIndex = (
  elementRecord: Partial<StudyRecordItem> | null,
): number | undefined => {
  if (!elementRecord) {
    return undefined;
  }
  return typeof elementRecord.element_index === 'number'
    ? elementRecord.element_index
    : undefined;
};

const normalizeDebugVariableValues = (
  variableValues?: Record<string, unknown>,
): DebugVariableValues => {
  if (!variableValues) {
    return {};
  }
  return Object.entries(variableValues).reduce<DebugVariableValues>(
    (acc, entry) => {
      const [key, value] = entry;
      if (value === undefined || value === null) {
        acc[key] = '';
      } else if (Array.isArray(value)) {
        acc[key] = value
          .map(item => (item === undefined || item === null ? '' : `${item}`))
          .filter(Boolean)
          .join(', ');
      } else {
        acc[key] = `${value}`;
      }
      return acc;
    },
    {},
  );
};

const resolveDebugElementBid = (
  item?: Pick<ChatContentItem, 'generated_block_bid' | 'element_bid'> | null,
): string => {
  if (!item) {
    return '';
  }
  return item.element_bid || item.generated_block_bid || '';
};

const isDebugActionableItem = (
  item?: Pick<
    ChatContentItem,
    'type' | 'generated_block_bid' | 'element_bid'
  > | null,
): boolean => {
  const resolvedBid = resolveDebugElementBid(item);
  if (!resolvedBid || resolvedBid === LOADING_ITEM_BID) {
    return false;
  }
  return (
    item?.type === ChatContentItemType.CONTENT ||
    item?.type === ChatContentItemType.INTERACTION
  );
};

const resolveLatestDebugActionableItem = (
  items: ChatContentItem[],
): ChatContentItem | undefined => {
  return [...items].reverse().find(item => isDebugActionableItem(item));
};

const syncDebugActionableFinalState = (items: ChatContentItem[]) => {
  let lastActionableIndex = -1;

  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (isDebugActionableItem(items[index])) {
      lastActionableIndex = index;
      break;
    }
  }

  if (lastActionableIndex <= 0) {
    return items;
  }

  let hasChanges = false;
  const nextItems = items.map((item, index) => {
    if (!isDebugActionableItem(item) || index >= lastActionableIndex) {
      return item;
    }

    const shouldUseTypewriter =
      item.type === ChatContentItemType.CONTENT &&
      item.element_type === ELEMENT_TYPE.TEXT
        ? (item.shouldUseTypewriter ?? true)
        : false;

    if (
      item.is_final === true &&
      item.shouldUseTypewriter === shouldUseTypewriter
    ) {
      return item;
    }

    hasChanges = true;
    return {
      ...item,
      is_final: true,
      shouldUseTypewriter,
    };
  });

  return hasChanges ? nextItems : items;
};

export const buildDebugBusinessErrorItem = (
  message: string,
  businessCode?: number,
): ChatContentItem => ({
  element_bid: DEBUG_BUSINESS_ERROR_ITEM_BID,
  generated_block_bid: DEBUG_BUSINESS_ERROR_ITEM_BID,
  content: message,
  readonly: true,
  type: ChatContentItemType.ERROR,
  business_code: businessCode,
});

export const replaceDebugLoadingWithBusinessError = (
  items: ChatContentItem[],
  message: string,
  businessCode?: number,
): ChatContentItem[] => {
  const normalizedMessage = message.trim();
  if (!normalizedMessage) {
    return withoutLoadingItem(items);
  }

  const nextList = items.filter(
    item =>
      !isLoadingItem(item) &&
      item.generated_block_bid !== DEBUG_BUSINESS_ERROR_ITEM_BID,
  );

  return [
    ...nextList,
    buildDebugBusinessErrorItem(normalizedMessage, businessCode),
  ];
};

export function useDebugSession({
  creditInsufficientAudience,
  onCourseVariablesCommitted,
}: {
  creditInsufficientAudience: CreditInsufficientAudience | null;
  onCourseVariablesCommitted?: (updates: DebugVariableValues) => void;
}) {
  const { t } = useTranslation();
  const { trackEvent } = useTracking();
  const { actions } = useShifu();
  const getCurrentMdflow = actions?.getCurrentMdflow;
  const resolveBaseUrl = useCallback(async () => {
    const dynamicBase = await getDynamicApiBaseUrl();
    const candidate = dynamicBase || getStringEnv('baseURL') || '';
    const normalized = candidate.replace(/\/$/, '');
    if (normalized && normalized !== '') {
      return normalized;
    }
    if (typeof window !== 'undefined' && window.location?.origin) {
      return window.location.origin;
    }
    return '';
  }, []);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const sessionItemsRef = useRef<ChatContentItem[]>([]);
  const [sessionItems, setSessionItems] = useState<ChatContentItem[]>([]);
  const currentContentRef = useRef<string>('');
  const currentContentElementBidRef = useRef<string | null>(null);
  const currentStreamingElementBidRef = useRef<string | null>(null);
  const runParamsRef = useRef<DebugRunParams>({});
  const initialVariableValuesRef = useRef<Record<string, unknown> | null>(null);
  const runStreamRef = useRef<DebugStreamSource | null>(null);
  const audioStreamsByElementRef = useRef<Record<string, DebugStreamSource>>(
    {},
  );
  const cancelAudioRequestsByElementRef = useRef<Record<string, () => void>>(
    {},
  );
  const streamGenerationRef = useRef(0);
  const debugSessionIdRef = useRef(createDebugSessionId());
  // Whether a run of the current debug session has started streaming. Editing
  // the script only restarts the debug session once a run has started.
  const hasSessionStartedRef = useRef(false);
  const trackedEngineSessionIdRef = useRef<string | null>(null);
  const isStreamingRef = useRef(false);
  const debugFailedRef = useRef(false);
  const doneTerminalStateRef = useRef<boolean | null>(null);
  const debugAnswerEditResultRef = useRef<
    ((result: DebugAnswerEditResult) => void) | undefined
  >(undefined);
  const answerEditRetryTargetRef = useRef<{
    generatedBlockBid: string;
    elementBid: string;
    userInput: Record<string, unknown>;
    prefixItems: ChatContentItem[];
    debugSessionId: string;
    params: Pick<DebugRunParams, 'shifuBid' | 'outlineBid' | 'mdflow'>;
  } | null>(null);
  const [hasAnswerEditRetryTarget, setHasAnswerEditRetryTarget] =
    useState(false);
  const clearAnswerEditRetryTarget = useCallback(() => {
    answerEditRetryTargetRef.current = null;
    setHasAnswerEditRetryTarget(false);
  }, []);
  const finishDebugAnswerEdit = useCallback(
    (result: DebugAnswerEditResult) => {
      const finish = debugAnswerEditResultRef.current;
      debugAnswerEditResultRef.current = undefined;
      if (finish && result === 'success') {
        clearAnswerEditRetryTarget();
      }
      finish?.(result);
    },
    [clearAnswerEditRetryTarget],
  );
  const [variableValuesSnapshot, setVariableValuesSnapshot] =
    useState<DebugVariableValues>({});
  const interactionParserRef = useRef(createInteractionParser());
  const freshAgentInteractionBidsRef = useRef<Set<string>>(new Set());
  const freshQuestionVariableNamesRef = useRef(new Set<string>());
  const resolveLatestMdflow = useCallback(() => {
    const latest = getCurrentMdflow?.();
    if (typeof latest === 'string') {
      return latest;
    }
    return (runParamsRef.current?.mdflow as string) || '';
  }, [getCurrentMdflow]);
  const [pendingInteractionResubmission, setPendingInteractionResubmission] =
    useState<{
      content: OnSendContentParams;
      elementBid: string;
    } | null>(null);
  const [isRegenerationConfirmationOpen, setIsRegenerationConfirmationOpen] =
    useState(false);
  const showOutputInProgressToast = useCallback(() => {
    toast({
      title: t('module.chat.outputInProgress'),
    });
  }, [t]);

  const showDebugErrorToast = useCallback(
    (message: string, fallbackMessage: string) => {
      return showAiServiceErrorToast({
        message,
        fallbackMessage,
        includeUnknown: true,
        unavailableMessage: t('module.preview.aiDebugUnavailable'),
      }).message;
    },
    [t],
  );

  const updateSessionItems = useCallback(
    (
      updater:
        | ChatContentItem[]
        | ((prev: ChatContentItem[]) => ChatContentItem[]),
    ) => {
      setSessionItems(prev => {
        const next =
          typeof updater === 'function'
            ? (updater as (prev: ChatContentItem[]) => ChatContentItem[])(prev)
            : updater;
        const normalizedNext = normalizeLegacyBlockCompatList(
          syncDebugActionableFinalState(next),
        );
        sessionItemsRef.current = normalizedNext;
        return normalizedNext;
      });
    },
    [],
  );

  const setVariableValue = useCallback((name: string, value: string) => {
    if (!name) {
      return;
    }
    const update = { [name]: value };
    if (initialVariableValuesRef.current && name === 'sys_user_language') {
      // Language is a Debug setting, not an answer to discard on restart.
      initialVariableValuesRef.current = {
        ...initialVariableValuesRef.current,
        ...update,
      };
    }
    const mergedVariableValues = {
      ...(runParamsRef.current.variableValues || {}),
      ...update,
    };
    runParamsRef.current.variableValues = mergedVariableValues;
    setVariableValuesSnapshot(previous => ({ ...previous, ...update }));
  }, []);

  const persistVariableValues = useCallback(
    ({
      shifuBid,
      systemVariableKeys,
      variableValues,
    }: {
      shifuBid?: string;
      systemVariableKeys?: string[];
      variableValues?: DebugVariableValues;
    }) => {
      const resolvedVariableValues =
        variableValues ||
        (runParamsRef.current.variableValues as DebugVariableValues) ||
        variableValuesSnapshot;
      const resolvedShifuBid = shifuBid || runParamsRef.current.shifuBid;
      const resolvedSystemKeys =
        systemVariableKeys || runParamsRef.current.systemVariableKeys || [];
      if (!resolvedShifuBid) {
        return;
      }
      mergeStoredDebugVariableValues(
        resolvedShifuBid,
        resolvedVariableValues,
        resolvedSystemKeys,
      );
    },
    [variableValuesSnapshot],
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
        debugWarn('[lesson-debug] failed to parse interaction block', error);
        return null;
      }
    },
    [],
  );

  const closeTtsStream = useCallback((elementBid: string) => {
    const source = audioStreamsByElementRef.current[elementBid];
    if (!source) {
      return;
    }
    delete audioStreamsByElementRef.current[elementBid];
    delete cancelAudioRequestsByElementRef.current[elementBid];
    source.close();
  }, []);

  const closeAllTtsStreams = useCallback(() => {
    // Cancellation settles callers even after stopRun invalidates the stream.
    Object.values(cancelAudioRequestsByElementRef.current).forEach(cancel =>
      cancel(),
    );
    cancelAudioRequestsByElementRef.current = {};
    Object.values(audioStreamsByElementRef.current).forEach(source => {
      source?.close?.();
    });
    audioStreamsByElementRef.current = {};
  }, []);

  const invalidateStreamGeneration = useCallback(() => {
    streamGenerationRef.current += 1;
    return streamGenerationRef.current;
  }, []);

  const isCurrentStreamGeneration = useCallback(
    (runId: number) => streamGenerationRef.current === runId,
    [],
  );

  const stopRun = useCallback(() => {
    const wasEditingAnswer = Boolean(debugAnswerEditResultRef.current);
    finishDebugAnswerEdit('cancelled');
    invalidateStreamGeneration();
    if (runStreamRef.current) {
      runStreamRef.current.close();
      runStreamRef.current = null;
    }
    closeAllTtsStreams();
    isStreamingRef.current = false;
    setIsStreaming(false);
    currentStreamingElementBidRef.current = null;
    setIsLoading(false);
    if (wasEditingAnswer) {
      updateSessionItems(prev => withoutLoadingItem(prev));
    }
  }, [
    closeAllTtsStreams,
    finishDebugAnswerEdit,
    invalidateStreamGeneration,
    updateSessionItems,
  ]);

  const handleDebugBusinessError = useCallback(
    (errorOrMessage?: string | ErrorWithCode | null, fallbackCode?: number) => {
      finishDebugAnswerEdit('failed');
      debugFailedRef.current = true;
      const resolvedToast = resolveLearnerErrorToast({
        error: typeof errorOrMessage === 'string' ? undefined : errorOrMessage,
        message:
          typeof errorOrMessage === 'string' ? errorOrMessage : undefined,
        fallbackMessage: t('module.preview.llmError'),
      });
      const resolvedCode =
        typeof errorOrMessage === 'string'
          ? fallbackCode
          : (errorOrMessage?.code ?? fallbackCode);
      const isCreditError = isCreditInsufficientBusinessCode(resolvedCode);
      let displayMessage: string;
      if (isCreditError) {
        if (creditInsufficientAudience === null) {
          stopRun();
          return;
        }
        displayMessage = getCreditInsufficientMessage(
          creditInsufficientAudience,
          resolvedCode,
        );
        showCreditInsufficientToast({
          audience: creditInsufficientAudience,
          code: resolvedCode,
        });
      } else {
        displayMessage = showDebugErrorToast(
          resolvedToast.message,
          t('module.preview.llmError'),
        );
      }
      updateSessionItems(prev =>
        replaceDebugLoadingWithBusinessError(
          prev,
          displayMessage,
          resolvedCode,
        ),
      );
      setErrorMessage(displayMessage);
      stopRun();
    },
    [
      creditInsufficientAudience,
      finishDebugAnswerEdit,
      updateSessionItems,
      showDebugErrorToast,
      stopRun,
      t,
    ],
  );

  const resetSession = useCallback(() => {
    debugFailedRef.current = false;
    stopRun();
    clearAnswerEditRetryTarget();
    updateSessionItems([]);
    setErrorMessage(null);
    currentContentRef.current = '';
    currentContentElementBidRef.current = null;
    currentStreamingElementBidRef.current = null;
    freshAgentInteractionBidsRef.current.clear();
    setVariableValuesSnapshot({});
    initialVariableValuesRef.current = null;
    debugSessionIdRef.current = createDebugSessionId();
    hasSessionStartedRef.current = false;
    trackedEngineSessionIdRef.current = null;
  }, [clearAnswerEditRetryTarget, stopRun, updateSessionItems]);

  const clearFreshAgentInteractionAnswer = useCallback(
    (itemBid: string, variableName?: string) => {
      if (!variableName || freshAgentInteractionBidsRef.current.has(itemBid)) {
        return;
      }
      freshAgentInteractionBidsRef.current.add(itemBid);
      freshQuestionVariableNamesRef.current.add(variableName);
      const currentVariableValues = (runParamsRef.current.variableValues ||
        {}) as DebugVariableValues;
      if (!(variableName in currentVariableValues)) {
        return;
      }
      const nextVariableValues = { ...currentVariableValues };
      delete nextVariableValues[variableName];
      runParamsRef.current.variableValues = nextVariableValues;
      setVariableValuesSnapshot(
        normalizeDebugVariableValues(nextVariableValues),
      );
    },
    [],
  );

  const ensureAudioItem = useCallback(
    (
      items: ChatContentItem[],
      elementBid: string,
      defaults: Partial<ChatContentItem> = {},
    ) => {
      const hasTarget = items.some(item => matchesElementBid(item, elementBid));
      if (hasTarget) {
        return items;
      }

      return [
        ...withoutLoadingItem(items),
        {
          element_bid: elementBid,
          generated_block_bid: elementBid,
          content: '',
          element_type: ELEMENT_TYPE.TEXT,
          is_final: false,
          readonly: false,
          shouldUseTypewriter: true,
          type: ChatContentItemType.CONTENT,
          ...defaults,
        } as ChatContentItem,
      ];
    },
    [],
  );

  const buildLikeStatusItem = useCallback(
    (parentElementBid: string): ChatContentItem => ({
      element_bid: `${parentElementBid}-feedback`,
      parent_element_bid: parentElementBid,
      parent_block_bid: parentElementBid,
      generated_block_bid: `${parentElementBid}-feedback`,
      like_status: LIKE_STATUS.NONE,
      type: ChatContentItemType.LIKE_STATUS,
    }),
    [],
  );

  const appendLikeStatusIfMissing = useCallback(
    (list: ChatContentItem[], parentElementBid: string): ChatContentItem[] => {
      if (!parentElementBid) {
        return list;
      }
      const hasLikeStatus = list.some(
        item =>
          item.type === ChatContentItemType.LIKE_STATUS &&
          (item.parent_block_bid === parentElementBid ||
            item.parent_element_bid === parentElementBid),
      );
      if (hasLikeStatus) {
        return list;
      }
      return [...list, buildLikeStatusItem(parentElementBid)];
    },
    [buildLikeStatusItem],
  );

  const finalizeDebugElementOutputInList = useCallback(
    (items: ChatContentItem[], completedElementBid: string) => {
      if (!completedElementBid) {
        return items;
      }

      const targetIndex = items.findIndex(
        item => item.element_bid === completedElementBid,
      );
      if (targetIndex < 0) {
        return items;
      }

      const nextItems = [...items];
      const targetItem = nextItems[targetIndex];
      nextItems[targetIndex] = {
        ...targetItem,
        is_final: true,
        shouldUseTypewriter:
          targetItem.type === ChatContentItemType.CONTENT &&
          targetItem.element_type === ELEMENT_TYPE.TEXT
            ? (targetItem.shouldUseTypewriter ?? true)
            : false,
      };

      return appendLikeStatusIfMissing(nextItems, completedElementBid);
    },
    [appendLikeStatusIfMissing],
  );

  const finalizeDebugItems = useCallback(() => {
    flushSync(() => {
      updateSessionItems((prev: ChatContentItem[]) => {
        const updatedList = [...prev].filter(item => !isLoadingItem(item));
        const latestActionableBid = resolveDebugElementBid(
          resolveLatestDebugActionableItem(updatedList),
        );
        if (!latestActionableBid) {
          return updatedList;
        }
        return finalizeDebugElementOutputInList(
          updatedList,
          latestActionableBid,
        );
      });
    });
  }, [finalizeDebugElementOutputInList, updateSessionItems]);

  const upsertElementDebugItem = useCallback(
    (response: DebugStreamEvent) => {
      const elementRecord = resolveElementPayload(response);
      const itemBid = resolveElementBid(elementRecord, response);
      if (!itemBid) {
        return;
      }

      const elementType = resolveElementType(elementRecord);
      const generatedBlockBid = resolveDebugGeneratedBlockBid({
        elementGeneratedBlockBid: elementRecord?.generated_block_bid,
        responseGeneratedBlockBid: response.generated_block_bid,
        fallbackBid: itemBid,
      });
      const elementIndex = resolveElementIndex(elementRecord);
      const elementContent =
        typeof elementRecord?.content === 'string' ? elementRecord.content : '';
      const isInteractionElement = elementType === ELEMENT_TYPE.INTERACTION;
      const interactionInfo = isInteractionElement
        ? parseInteractionBlock(elementContent)
        : null;
      const variableName = interactionInfo?.variableName;
      if (isInteractionElement) {
        clearFreshAgentInteractionAnswer(itemBid, variableName);
      }
      const nextItemType = isInteractionElement
        ? ChatContentItemType.INTERACTION
        : ChatContentItemType.CONTENT;
      const previousStreamingElementBid = currentStreamingElementBidRef.current;

      updateSessionItems(prev => {
        const contentToRender =
          elementType === ELEMENT_TYPE.HTML
            ? elementContent
            : maskIncompleteMermaidBlock(elementContent);

        const nextItem: ChatContentItem = {
          element_bid: itemBid,
          generated_block_bid: generatedBlockBid,
          content: contentToRender,
          readonly: false,
          type: nextItemType,
          element_type: elementType || undefined,
          element_index: elementIndex,
          is_final: Boolean(elementRecord?.is_final),
          sequence_number:
            typeof elementRecord?.sequence_number === 'number'
              ? elementRecord.sequence_number
              : undefined,
          is_marker:
            typeof elementRecord?.is_marker === 'boolean'
              ? elementRecord.is_marker
              : undefined,
          is_new:
            typeof elementRecord?.is_new === 'boolean'
              ? elementRecord.is_new
              : undefined,
          is_renderable:
            typeof elementRecord?.is_renderable === 'boolean'
              ? elementRecord.is_renderable
              : undefined,
          is_speakable:
            typeof elementRecord?.is_speakable === 'boolean'
              ? elementRecord.is_speakable
              : undefined,
          user_input: '',
          shouldUseTypewriter:
            nextItemType === ChatContentItemType.CONTENT &&
            elementType === ELEMENT_TYPE.TEXT,
        };

        return applyElementToList(withoutLoadingItem(prev), nextItem, {
          completedElementBid: list => {
            if (
              previousStreamingElementBid &&
              previousStreamingElementBid !== itemBid
            ) {
              const previousItem = list.find(
                item => item.element_bid === previousStreamingElementBid,
              );
              const previousItemBid = resolveDebugElementBid(previousItem);
              if (isDebugActionableItem(previousItem) && previousItemBid) {
                return previousItemBid;
              }
            }
            if (list.some(item => item.element_bid === itemBid)) {
              return '';
            }
            const latestActionableBid = resolveDebugElementBid(
              resolveLatestDebugActionableItem(list),
            );
            return latestActionableBid && latestActionableBid !== itemBid
              ? latestActionableBid
              : '';
          },
          finalize: finalizeDebugElementOutputInList,
          matches: item => item.element_bid === itemBid,
          merge: (previous, next) => ({
            ...previous,
            ...next,
            user_input: previous.user_input || '',
          }),
        });
      });
      currentContentElementBidRef.current = itemBid;
      currentStreamingElementBidRef.current = itemBid;
    },
    [
      clearFreshAgentInteractionAnswer,
      finalizeDebugElementOutputInList,
      parseInteractionBlock,
      updateSessionItems,
    ],
  );

  const handlePayload = useCallback(
    (payload: string, streamVariables: DebugStreamVariableState) => {
      try {
        const normalizedPayload = payload.replace(/^data:\s*/, '').trim();
        if (!normalizedPayload) {
          return;
        }
        const response = JSON.parse(normalizedPayload) as DebugStreamEvent;
        const responseType =
          typeof response.type === 'string'
            ? response.type
            : typeof response.event_type === 'string'
              ? response.event_type
              : '';
        const payloadObject = resolveResponsePayload(response);
        if (responseType === DebugStreamEventType.ELEMENT) {
          updateSessionItems(prev => withoutLoadingItem(prev));
        }

        if (
          responseType === DebugStreamEventType.DEBUG_VARIABLES ||
          responseType === DebugStreamEventType.DEBUG_VARIABLES_COMMITTED
        ) {
          const committed =
            responseType === DebugStreamEventType.DEBUG_VARIABLES_COMMITTED;
          const variables = committed
            ? parseObjectPayload<Record<string, unknown>>(
                payloadObject?.variables,
              )
            : payloadObject;
          if (variables) {
            const snapshot = { ...variables };
            for (const name of freshQuestionVariableNamesRef.current) {
              delete snapshot[name];
            }
            if (committed) {
              const courseUpdates = parseObjectPayload<DebugVariableValues>(
                payloadObject?.course_updates,
              );
              const rewindSeed = parseObjectPayload<Record<string, unknown>>(
                payloadObject?.user_variables,
              );
              // Rebase on scoped memory after rewind. A full panel snapshot can
              // contain lesson-only values that must not become request inputs.
              const requestVariables = {
                ...(rewindSeed ?? runParamsRef.current.variableValues),
                ...courseUpdates,
              };
              for (const name of freshQuestionVariableNamesRef.current) {
                delete requestVariables[name];
              }
              if (rewindSeed) streamVariables.awaitingLegacyRewindSeed = false;
              runParamsRef.current.variableValues = requestVariables;
              if (courseUpdates && Object.keys(courseUpdates).length) {
                mergeStoredDebugVariableValues(
                  runParamsRef.current.shifuBid,
                  courseUpdates,
                  runParamsRef.current.systemVariableKeys || [],
                );
                onCourseVariablesCommitted?.(courseUpdates);
              }
            } else if (streamVariables.awaitingLegacyRewindSeed) {
              // Older servers retain the checkpoint's user memory themselves.
              // Keep only the language, which the next preview request sets.
              const language = variables.sys_user_language;
              runParamsRef.current.variableValues =
                typeof language === 'string'
                  ? { sys_user_language: language }
                  : {};
              streamVariables.awaitingLegacyRewindSeed = false;
            }
            setVariableValuesSnapshot(normalizeDebugVariableValues(snapshot));
          }
        } else if (responseType === DebugStreamEventType.ELEMENT) {
          upsertElementDebugItem(response);
        } else if (responseType === DebugStreamEventType.DEBUG_ENGINE) {
          hasSessionStartedRef.current = true;
          if (
            response.content === '2.0' &&
            trackedEngineSessionIdRef.current !== debugSessionIdRef.current
          ) {
            trackedEngineSessionIdRef.current = debugSessionIdRef.current;
            void trackEvent('creator_lesson_preview_engine_started', {
              engine: 'v2',
              shifu_bid: runParamsRef.current.shifuBid,
              outline_bid: runParamsRef.current.outlineBid,
            });
          }
        } else if (responseType === DebugStreamEventType.DONE) {
          const doneIsTerminal = readDoneIsTerminal(response);
          finalizeDebugItems();
          doneTerminalStateRef.current = doneIsTerminal;
          currentContentElementBidRef.current = null;
          currentContentRef.current = '';
          currentStreamingElementBidRef.current = null;
          if (doneIsTerminal === true) {
            finishDebugAnswerEdit('success');
            stopRun();
          }
        } else if (responseType === DebugStreamEventType.ERROR) {
          const { message, code } = readRunEventError(response);
          handleDebugBusinessError(
            message || t('module.preview.llmError'),
            code,
          );
        }
      } catch (err) {
        debugWarn('[lesson-debug] SSE handling error', err);
      }
    },
    [
      finalizeDebugItems,
      finishDebugAnswerEdit,
      handleDebugBusinessError,
      onCourseVariablesCommitted,
      stopRun,
      trackEvent,
      updateSessionItems,
      t,
      upsertElementDebugItem,
    ],
  );

  useEffect(() => {
    return () => {
      stopRun();
    };
  }, [stopRun]);

  const startRun = useCallback(
    async ({
      shifuBid,
      outlineBid,
      mdflow,
      blockIndex,
      userInput,
      variableValues,
      maxBlockCount,
      systemVariableKeys,
      reloadGeneratedBlockBid,
      reloadElementBid,
    }: DebugRunParams) => {
      if (creditInsufficientAudience === null) {
        return;
      }
      let normalizedUserInput =
        userInput &&
        Object.values(userInput).some(value =>
          Array.isArray(value)
            ? value.length > 0
            : value !== undefined && value !== null && `${value}`.trim() !== '',
        )
          ? userInput
          : undefined;
      if (
        hasSessionStartedRef.current &&
        mdflow !== runParamsRef.current.mdflow &&
        !normalizedUserInput
      ) {
        // Without an answer there is nothing to continue: start the edited draft
        // from its beginning with a new debug session. An answer keeps the
        // session, and the server continues it under the edited draft.
        variableValues = { ...(initialVariableValuesRef.current || {}) };
        resetSession();
        normalizedUserInput = undefined;
        blockIndex = 0;
        reloadGeneratedBlockBid = undefined;
        reloadElementBid = undefined;
      }
      if (initialVariableValuesRef.current === null) {
        initialVariableValuesRef.current = { ...(variableValues || {}) };
      }
      if (!debugSessionIdRef.current) {
        debugSessionIdRef.current = createDebugSessionId();
      }
      const retryTarget = answerEditRetryTargetRef.current;
      if (
        !reloadGeneratedBlockBid ||
        retryTarget?.generatedBlockBid !== reloadGeneratedBlockBid ||
        retryTarget?.elementBid !== reloadElementBid ||
        retryTarget.debugSessionId !== debugSessionIdRef.current ||
        retryTarget.params.shifuBid !== shifuBid ||
        retryTarget.params.outlineBid !== outlineBid ||
        retryTarget.params.mdflow !== mdflow
      ) {
        clearAnswerEditRetryTarget();
      }
      const mergedParams: DebugRunParams = {
        ...runParamsRef.current,
        shifuBid,
        outlineBid,
        mdflow,
        blockIndex,
        variableValues,
        maxBlockCount,
        systemVariableKeys,
      };
      const {
        shifuBid: finalShifuBid,
        outlineBid: finalOutlineBid,
        mdflow: finalMdflow,
        blockIndex: finalBlockIndex = 0,
        variableValues: finalVariableValues = {},
        maxBlockCount: finalMaxBlockCount,
      } = mergedParams;
      debugFailedRef.current = false;
      runParamsRef.current = mergedParams;
      setVariableValuesSnapshot(
        normalizeDebugVariableValues(finalVariableValues),
      );

      if (!finalShifuBid || !finalOutlineBid) {
        setErrorMessage(t('module.preview.invalidParams'));
        return;
      }

      if (
        typeof finalMaxBlockCount === 'number' &&
        finalMaxBlockCount >= 0 &&
        finalBlockIndex >= finalMaxBlockCount
      ) {
        stopRun();
        return;
      }

      stopRun();
      const streamGeneration = invalidateStreamGeneration();
      freshQuestionVariableNamesRef.current.clear();
      isStreamingRef.current = true;
      setIsStreaming(true);
      debugAnswerEditResultRef.current = startDebugAnswerEditTracking({
        anchor: reloadElementBid,
        shifuBid: finalShifuBid,
        outlineBid: finalOutlineBid,
        trackEvent,
      });
      doneTerminalStateRef.current = null;
      let resolvedBaseUrl: string;
      try {
        resolvedBaseUrl = await resolveBaseUrl();
      } catch (error) {
        if (isCurrentStreamGeneration(streamGeneration)) {
          handleDebugBusinessError(error as ErrorWithCode);
        }
        return;
      }
      if (!isCurrentStreamGeneration(streamGeneration)) {
        return;
      }
      if (!resolvedBaseUrl) {
        finishDebugAnswerEdit('failed');
        stopRun();
        setErrorMessage(t('module.preview.missingApiBaseUrl'));
        return;
      }
      setErrorMessage(null);
      updateSessionItems(prev => [
        ...withoutLoadingItem(prev),
        {
          element_bid: LOADING_ITEM_BID,
          generated_block_bid: LOADING_ITEM_BID,
          content: '',
          customRenderBar: () => <LoadingBar />,
          type: ChatContentItemType.CONTENT,
        },
      ]);
      setIsLoading(true);
      isStreamingRef.current = true;
      currentContentRef.current = '';
      currentContentElementBidRef.current = null;
      currentStreamingElementBidRef.current = null;

      try {
        const payload: Record<string, unknown> = {
          request_generation: streamGeneration,
          block_index: finalBlockIndex,
          content: finalMdflow,
          variables: finalVariableValues,
          ...(reloadGeneratedBlockBid
            ? { reload_generated_block_bid: reloadGeneratedBlockBid }
            : {}),
          ...(reloadElementBid ? { reload_element_bid: reloadElementBid } : {}),
          ...(debugSessionIdRef.current
            ? { debug_session_id: debugSessionIdRef.current }
            : {}),
        };
        if (normalizedUserInput) {
          payload.user_input = normalizedUserInput;
        }
        const url = `${resolvedBaseUrl}/api/learn/shifu/${finalShifuBid}/preview/${finalOutlineBid}`;
        const source = openSseStream({
          url,
          method: 'POST',
          payload,
          meta: { skipErrorToast: true, creditInsufficientAudience },
          onBusinessError: (error, erroredSource) => {
            if (runStreamRef.current !== erroredSource) {
              return;
            }
            handleDebugBusinessError(error);
          },
        });
        runStreamRef.current = source;
        const streamVariables: DebugStreamVariableState = {
          awaitingLegacyRewindSeed: Boolean(reloadGeneratedBlockBid),
        };
        onSseData(source, data => {
          if (
            !isCurrentStreamGeneration(streamGeneration) ||
            debugFailedRef.current ||
            runStreamRef.current !== source
          ) {
            return;
          }
          handlePayload(data, streamVariables);
          setIsLoading(false);
        });
        source.addEventListener('error', err => {
          if (
            !isCurrentStreamGeneration(streamGeneration) ||
            runStreamRef.current !== source
          ) {
            return;
          }
          debugError('[lesson-debug] Debug stream error', err);
          finalizeDebugItems();
          const hasReceivedNonTerminalDone =
            doneTerminalStateRef.current === false;
          if (hasReceivedNonTerminalDone) {
            finishDebugAnswerEdit('success');
            stopRun();
            return;
          }
          handleDebugBusinessError(t('module.preview.streamError'));
        });
        source.addEventListener('readystatechange', event => {
          const readyState = (event as Event & { readyState?: number })
            .readyState;
          if (
            (readyState ?? source.readyState) !== 2 ||
            !isCurrentStreamGeneration(streamGeneration) ||
            runStreamRef.current !== source
          ) {
            return;
          }
          finalizeDebugItems();
          if (doneTerminalStateRef.current === false) {
            finishDebugAnswerEdit('success');
            stopRun();
          } else {
            handleDebugBusinessError(t('module.preview.streamError'));
          }
        });
        source.stream();
      } catch (err) {
        debugFailedRef.current = true;
        debugError('[lesson-debug] Debug request error', err);
        handleDebugBusinessError(
          resolveLearnerErrorMessage({
            error: err as ErrorWithCode,
            fallbackMessage: t('module.preview.requestFailed'),
          }),
        );
        stopRun();
        setIsLoading(false);
      }
    },
    [
      clearAnswerEditRetryTarget,
      finalizeDebugItems,
      finishDebugAnswerEdit,
      creditInsufficientAudience,
      handleDebugBusinessError,
      handlePayload,
      invalidateStreamGeneration,
      isCurrentStreamGeneration,
      resolveBaseUrl,
      resetSession,
      updateSessionItems,
      stopRun,
      t,
      trackEvent,
    ],
  );

  const restartSession = useCallback(() => {
    const currentParams = { ...runParamsRef.current };
    const initialVariableValues = {
      ...(initialVariableValuesRef.current || {}),
    };
    resetSession();
    void startRun({
      ...currentParams,
      mdflow: resolveLatestMdflow(),
      variableValues: initialVariableValues,
      blockIndex: 0,
      userInput: undefined,
    });
  }, [resetSession, resolveLatestMdflow, startRun]);

  const applyInteractionAnswer = useCallback(
    (
      params: OnSendContentParams,
      elementBid: string,
    ): { nextItems: ChatContentItem[]; interactionIndex: number } => {
      const { items: nextItems, index: interactionIndex } =
        updateInteractionItems(sessionItemsRef.current, params, elementBid, {
          truncateFollowingItems: true,
          preserveHelpers: true,
        });
      if (interactionIndex !== -1) updateSessionItems(nextItems);
      return { nextItems, interactionIndex };
    },
    [updateSessionItems],
  );

  const startAnswerEdit = useCallback(
    (
      generatedBlockBid: string,
      prefixItems: ChatContentItem[],
      answer: {
        elementBid: string;
        userInput: Record<string, unknown>;
      },
    ) => {
      const retainedElementBids = new Set(
        prefixItems.map(item => item.element_bid),
      );
      freshAgentInteractionBidsRef.current = new Set(
        [...freshAgentInteractionBidsRef.current].filter(bid =>
          retainedElementBids.has(bid),
        ),
      );
      updateSessionItems(prefixItems);
      void startRun({
        ...runParamsRef.current,
        // The server rewinds to the answered question and continues under the
        // draft as it is now, so an edit does not force a restart.
        mdflow: resolveLatestMdflow(),
        blockIndex: 0,
        userInput: answer.userInput,
        reloadElementBid: answer.elementBid,
        reloadGeneratedBlockBid: generatedBlockBid,
      });
    },
    [resolveLatestMdflow, startRun, updateSessionItems],
  );

  const submitInteractionAnswer = useCallback(
    (
      content: OnSendContentParams,
      elementBid: string,
      options?: { skipConfirm?: boolean },
    ) => {
      if (creditInsufficientAudience === null) {
        return false;
      }
      const draftEdited = resolveLatestMdflow() !== runParamsRef.current.mdflow;

      const { variableName } = content;
      const normalizedVariableName =
        normalizeVariableName(variableName ?? '') || '';
      const hasVariableName = Boolean(normalizedVariableName);
      const listUpdateContent =
        variableName === normalizedVariableName
          ? content
          : { ...content, variableName: normalizedVariableName };

      const requiresRegeneration = requiresInteractionRewind(
        sessionItemsRef.current,
        elementBid,
        { isStreaming: isStreamingRef.current, content: listUpdateContent },
      );
      const { values } = resolveInteractionSubmission(content);
      if (draftEdited && !values.length) {
        // Without an answer there is nothing to continue under the edited draft:
        // start it from its beginning. An answer, to the current question or an
        // earlier one, continues the conversation under the edited draft.
        restartSession();
        return true;
      }
      if (requiresRegeneration) {
        if (!options?.skipConfirm) {
          setPendingInteractionResubmission({
            content: listUpdateContent,
            elementBid,
          });
          setIsRegenerationConfirmationOpen(true);
          return false;
        }
        const target = sessionItemsRef.current.find(
          item => item.element_bid === elementBid,
        );
        const userInput = buildDebugInteractionInput(
          normalizedVariableName,
          resolveInteractionSubmission(content).values,
        );
        if (!target?.generated_block_bid || !userInput) return false;
        stopRun();
        const { items: prefix, index } = updateInteractionItems(
          sessionItemsRef.current,
          listUpdateContent,
          elementBid,
          { truncateFollowingItems: true },
        );
        if (index < 0) return false;
        answerEditRetryTargetRef.current = {
          generatedBlockBid: target.generated_block_bid,
          elementBid,
          userInput,
          prefixItems: prefix,
          debugSessionId: debugSessionIdRef.current,
          params: {
            shifuBid: runParamsRef.current.shifuBid,
            outlineBid: runParamsRef.current.outlineBid,
            mdflow: resolveLatestMdflow(),
          },
        };
        setHasAnswerEditRetryTarget(true);
        startAnswerEdit(target.generated_block_bid, prefix, {
          elementBid,
          userInput,
        });
        return true;
      }
      if (isStreamingRef.current) {
        showOutputInProgressToast();
        return false;
      }

      const { nextItems, interactionIndex } = applyInteractionAnswer(
        listUpdateContent,
        elementBid,
      );
      if (interactionIndex === -1) {
        updateSessionItems(nextItems);
      }

      if (!values.length) {
        return false;
      }

      const nextValue = values.join(',');

      if (hasVariableName) {
        const nextVariableValues: DebugVariableValues = {
          ...(runParamsRef.current.variableValues as DebugVariableValues),
          [normalizedVariableName]: nextValue,
        };
        runParamsRef.current.variableValues = nextVariableValues;
        setVariableValuesSnapshot(
          normalizeDebugVariableValues(nextVariableValues),
        );
        mergeStoredDebugVariableValues(
          runParamsRef.current.shifuBid,
          { [normalizedVariableName]: nextValue },
          runParamsRef.current.systemVariableKeys || [],
        );
      }

      const requestVariableValues: DebugVariableValues =
        (runParamsRef.current.variableValues as DebugVariableValues) || {};
      const userInputPayload = buildDebugInteractionInput(
        normalizedVariableName,
        values,
      );

      const nextParams = buildDebugContinuationParams({
        currentParams: runParamsRef.current,
        latestMdflow: resolveLatestMdflow(),
        blockIndex: runParamsRef.current.blockIndex ?? 0,
        variableValues: requestVariableValues,
        userInput: userInputPayload,
      });
      startRun(nextParams);
      return true;
    },
    [
      creditInsufficientAudience,
      updateSessionItems,
      showOutputInProgressToast,
      startRun,
      applyInteractionAnswer,
      stopRun,
      startAnswerEdit,
      resolveLatestMdflow,
      restartSession,
    ],
  );

  const retryAnswerEdit = useCallback(() => {
    if (creditInsufficientAudience === null) {
      return;
    }
    if (isStreamingRef.current) {
      showOutputInProgressToast();
      return;
    }
    const target = answerEditRetryTargetRef.current;
    if (!target) {
      return;
    }
    if (
      target.debugSessionId !== debugSessionIdRef.current ||
      target.params.shifuBid !== runParamsRef.current.shifuBid ||
      target.params.outlineBid !== runParamsRef.current.outlineBid
    ) {
      clearAnswerEditRetryTarget();
      return;
    }
    // The retry sends the draft as it is now; record that draft on the target so
    // the retried request still owns it and a second failure can retry again.
    target.params = { ...target.params, mdflow: resolveLatestMdflow() };
    // A failed connection may already have replaced the server checkpoint.
    // Retry the logical target without restoring its discarded rows or answers.
    startAnswerEdit(target.generatedBlockBid, target.prefixItems, {
      elementBid: target.elementBid,
      userInput: target.userInput,
    });
  }, [
    clearAnswerEditRetryTarget,
    creditInsufficientAudience,
    resolveLatestMdflow,
    showOutputInProgressToast,
    startAnswerEdit,
  ]);

  const submitInteraction = useCallback(
    (content: OnSendContentParams, elementBid: string) => {
      submitInteractionAnswer(content, elementBid);
    },
    [submitInteractionAnswer],
  );

  const confirmRegeneration = useCallback(() => {
    if (!pendingInteractionResubmission) {
      setIsRegenerationConfirmationOpen(false);
      return;
    }
    submitInteractionAnswer(
      pendingInteractionResubmission.content,
      pendingInteractionResubmission.elementBid,
      {
        skipConfirm: true,
      },
    );
    setPendingInteractionResubmission(null);
    setIsRegenerationConfirmationOpen(false);
  }, [pendingInteractionResubmission, submitInteractionAnswer]);

  const cancelRegeneration = useCallback(() => {
    setPendingInteractionResubmission(null);
    setIsRegenerationConfirmationOpen(false);
  }, []);

  const nullRenderBar = useCallback(() => null, []);

  const items = useMemo(
    () =>
      sessionItems.map(item => ({
        ...item,
        customRenderBar: item.customRenderBar || nullRenderBar,
      })),
    [sessionItems, nullRenderBar],
  );

  const requestElementAudio = useCallback(
    async ({
      shifuBid,
      elementBid,
      text,
    }: {
      shifuBid: string;
      elementBid: string;
      text: string;
    }): Promise<AudioCompleteData | null> => {
      if (creditInsufficientAudience === null || !shifuBid || !elementBid) {
        return null;
      }
      const streamGeneration = streamGenerationRef.current;

      const existingItem = sessionItemsRef.current.find(item =>
        matchesElementBid(item, elementBid),
      );
      const cachedTrack = getAudioTrackByPosition(
        existingItem?.audioTracks ?? [],
      );
      if (cachedTrack?.audioUrl && !cachedTrack.isAudioStreaming) {
        return {
          audio_url: cachedTrack.audioUrl,
          audio_bid: '',
          duration_ms: cachedTrack.durationMs ?? 0,
        };
      }

      if (audioStreamsByElementRef.current[elementBid]) {
        return null;
      }

      const resolvedBaseUrl = await resolveBaseUrl();
      if (!isCurrentStreamGeneration(streamGeneration)) {
        throw new DOMException('Preview audio request cancelled', 'AbortError');
      }

      updateSessionItems(prevState =>
        ensureAudioItem(
          prevState.map(item => {
            if (!matchesElementBid(item, elementBid)) {
              return item;
            }
            return {
              ...item,
              audioTracks: [],
              audioUrl: undefined,
              audioDurationMs: undefined,
              isAudioStreaming: true,
            };
          }),
          elementBid,
          {
            audioTracks: [],
            audioUrl: undefined,
            audioDurationMs: undefined,
            isAudioStreaming: true,
          },
        ),
      );

      return new Promise((resolve, reject) => {
        const url = `${resolvedBaseUrl}/api/learn/shifu/${shifuBid}/tts/preview?preview_mode=true`;
        const source = openSseStream({
          url,
          method: 'POST',
          payload: { text: text || '' },
          meta: { creditInsufficientAudience },
          onBusinessError: error => fail(error),
        });
        audioStreamsByElementRef.current[elementBid] = source;
        let settled = false;
        const settleFailure = (error: Error) => {
          if (
            settled ||
            audioStreamsByElementRef.current[elementBid] !== source
          ) {
            return;
          }
          settled = true;
          updateSessionItems(prevState =>
            ensureAudioItem(
              prevState.map(item =>
                matchesElementBid(item, elementBid)
                  ? {
                      ...item,
                      isAudioStreaming: false,
                      audioTracks: [],
                      audioSegments: [],
                      audioUrl: undefined,
                      audioDurationMs: undefined,
                    }
                  : item,
              ),
              elementBid,
            ),
          );
          closeTtsStream(elementBid);
          reject(error);
        };
        const fail = (error: Error) => {
          if (isCurrentStreamGeneration(streamGeneration)) settleFailure(error);
        };
        cancelAudioRequestsByElementRef.current[elementBid] = () =>
          settleFailure(
            new DOMException('Preview audio request cancelled', 'AbortError'),
          );
        onSseData(source, payload => {
          if (
            !isCurrentStreamGeneration(streamGeneration) ||
            debugFailedRef.current ||
            audioStreamsByElementRef.current[elementBid] !== source
          ) {
            return;
          }

          try {
            const response = JSON.parse(payload);
            if (response?.type === 'error' || response?.type === 'done') {
              fail(
                new Error(
                  typeof response.content === 'string' &&
                    response.content.trim()
                    ? response.content
                    : 'Preview audio stream ended without audio',
                ),
              );
              return;
            }
            if (response?.type === DebugStreamEventType.AUDIO_SEGMENT) {
              const audioPayload = response.content ?? response.data;
              const audioSegment = normalizeAudioSegmentPayload(audioPayload);
              if (!audioSegment) {
                return;
              }
              updateSessionItems(prevState =>
                upsertAudioSegment(
                  prevState,
                  elementBid,
                  toAudioSegmentData(audioSegment),
                  ensureAudioItem,
                ),
              );
              return;
            }

            if (response?.type === DebugStreamEventType.AUDIO_COMPLETE) {
              const audioPayload = response.content ?? response.data;
              const audioComplete = normalizeAudioCompletePayload(audioPayload);
              if (!audioComplete) {
                return;
              }
              updateSessionItems(prevState =>
                upsertAudioComplete(
                  prevState,
                  elementBid,
                  audioComplete,
                  ensureAudioItem,
                ),
              );
              settled = true;
              closeTtsStream(elementBid);
              resolve(audioComplete ?? null);
            }
          } catch (err) {
            debugWarn('[lesson-debug] Debug audio stream parse error', err);
          }
        });

        source.addEventListener('error', () => {
          fail(new Error('Preview audio stream failed'));
        });
        source.addEventListener('readystatechange', event => {
          const readyState = (event as Event & { readyState?: number })
            .readyState;
          if ((readyState ?? source.readyState) === 2) {
            fail(new Error('Preview audio stream ended without audio'));
          }
        });

        source.stream();
      });
    },
    [
      closeTtsStream,
      creditInsufficientAudience,
      ensureAudioItem,
      isCurrentStreamGeneration,
      resolveBaseUrl,
      updateSessionItems,
    ],
  );

  return {
    items,
    isLoading,
    isStreaming,
    errorMessage,
    startRun,
    stopRun,
    resetSession,
    submitInteraction,
    retryAnswerEdit,
    canRetryAnswerEdit:
      hasAnswerEditRetryTarget &&
      !isStreaming &&
      creditInsufficientAudience !== null,
    persistVariableValues,
    setVariableValue,
    variableValues: variableValuesSnapshot,
    requestElementAudio,
    regenerationConfirmation: {
      open: isRegenerationConfirmationOpen,
      onConfirm: confirmRegeneration,
      onCancel: cancelRegeneration,
    },
  };
}
