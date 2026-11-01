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
  mergeStreamingMarkdownText,
  maskIncompleteMermaidBlock,
} from '@/lib/markdown-utils';
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
  resolveDebugRegenerationStartIndex,
} from './debug-request-params';
import { startDebugRegenerateTracking } from './debug-regenerate-tracking';

interface InteractionParseResult {
  variableName?: string;
  buttonTexts?: string[];
  buttonValues?: string[];
  placeholder?: string;
  isMultiSelect?: boolean;
}

type DebugStreamSource = InstanceType<typeof SSE>;
type DebugRegenerateResult = Parameters<
  NonNullable<ReturnType<typeof startDebugRegenerateTracking>>
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
  DEBUG_ENGINE = 'preview_engine',
  ELEMENT = 'element',
  INTERACTION = 'interaction',
  CONTENT = 'content',
  DONE = 'done',
  TEXT_END = 'text_end',
  ERROR = 'error',
  AUDIO_SEGMENT = 'audio_segment',
  AUDIO_COMPLETE = 'audio_complete',
}

type DebugStreamEvent = {
  type?: string;
  event_type?: string;
  code?: number;
  content?: unknown;
  data?: unknown;
  generated_block_bid?: unknown;
  is_terminal?: unknown;
};

const resolveDebugBusinessCode = (
  response: DebugStreamEvent,
): number | undefined => {
  if (typeof response.code === 'number') {
    return response.code;
  }
  for (const candidate of [response.content, response.data]) {
    const payload = parseObjectPayload<{ code?: unknown }>(candidate);
    if (typeof payload?.code === 'number') {
      return payload.code;
    }
  }
  return undefined;
};

const DEBUG_LOADING_ITEM_BID = 'loading';
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

const resolveResponseStringPayload = (response: DebugStreamEvent): string => {
  const contentPayload =
    typeof response.content === 'string' ? response.content : '';
  if (contentPayload) {
    return contentPayload;
  }
  const dataPayload =
    typeof response.data === 'string' ? response.data : undefined;
  if (dataPayload) {
    return dataPayload;
  }
  const objectPayload = resolveResponsePayload(response);
  const mdflow =
    objectPayload && typeof objectPayload.mdflow === 'string'
      ? objectPayload.mdflow
      : '';
  return mdflow || '';
};

const resolveDoneIsTerminal = (response: DebugStreamEvent): boolean | null => {
  const topLevelFlag = readBooleanField(response as Record<string, unknown>, [
    'is_terminal',
  ]);
  if (topLevelFlag !== null) {
    return topLevelFlag;
  }
  const payloadObject = resolveResponsePayload(response);
  if (!payloadObject) {
    return null;
  }
  return readBooleanField(payloadObject, ['is_terminal']);
};

const readPayloadField = (
  payload: Record<string, unknown>,
  keys: string[],
): unknown => {
  for (const key of keys) {
    if (key in payload) {
      return payload[key];
    }
  }
  return undefined;
};

const readBooleanField = (
  payload: Record<string, unknown>,
  keys: string[],
): boolean | null => {
  const value = readPayloadField(payload, keys);
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  if (typeof value === 'string') {
    const normalized = value.toLowerCase();
    if (normalized === 'true') {
      return true;
    }
    if (normalized === 'false') {
      return false;
    }
  }
  return null;
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
  if (!resolvedBid || resolvedBid === 'loading') {
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

const matchesDebugElementBid = (item: ChatContentItem, bid: string) => {
  if (!bid) {
    return false;
  }

  return item.element_bid === bid;
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
    return items.filter(
      item => item.generated_block_bid !== DEBUG_LOADING_ITEM_BID,
    );
  }

  const nextList = items.filter(
    item =>
      item.generated_block_bid !== DEBUG_LOADING_ITEM_BID &&
      item.generated_block_bid !== DEBUG_BUSINESS_ERROR_ITEM_BID,
  );

  return [
    ...nextList,
    buildDebugBusinessErrorItem(normalizedMessage, businessCode),
  ];
};

export function useDebugSession({
  creditInsufficientAudience,
}: {
  creditInsufficientAudience: CreditInsufficientAudience | null;
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
  const debugRegenerateResultRef = useRef<
    ((result: DebugRegenerateResult) => void) | undefined
  >(undefined);
  const regenerationRetryTargetRef = useRef<{
    generatedBlockBid: string;
    prefixItems: ChatContentItem[];
    debugSessionId: string;
    params: Pick<DebugRunParams, 'shifuBid' | 'outlineBid' | 'mdflow'>;
  } | null>(null);
  const [hasRegenerationRetryTarget, setHasRegenerationRetryTarget] =
    useState(false);
  const clearRegenerationRetryTarget = useCallback(() => {
    regenerationRetryTargetRef.current = null;
    setHasRegenerationRetryTarget(false);
  }, []);
  const finishDebugRegenerate = useCallback(
    (result: DebugRegenerateResult) => {
      const finish = debugRegenerateResultRef.current;
      debugRegenerateResultRef.current = undefined;
      if (finish && result === 'success') {
        clearRegenerationRetryTarget();
      }
      finish?.(result);
    },
    [clearRegenerationRetryTarget],
  );
  const [variableValuesSnapshot, setVariableValuesSnapshot] =
    useState<DebugVariableValues>({});
  const interactionParserRef = useRef(createInteractionParser());
  const freshAgentInteractionBidsRef = useRef<Set<string>>(new Set());
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
    setVariableValuesSnapshot(
      normalizeDebugVariableValues(mergedVariableValues),
    );
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
    const wasRegenerating = Boolean(debugRegenerateResultRef.current);
    finishDebugRegenerate('cancelled');
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
    if (wasRegenerating) {
      updateSessionItems(prev =>
        prev.filter(
          item => item.generated_block_bid !== DEBUG_LOADING_ITEM_BID,
        ),
      );
    }
  }, [
    closeAllTtsStreams,
    finishDebugRegenerate,
    invalidateStreamGeneration,
    updateSessionItems,
  ]);

  const handleDebugBusinessError = useCallback(
    (errorOrMessage?: string | ErrorWithCode | null, fallbackCode?: number) => {
      finishDebugRegenerate('failed');
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
      finishDebugRegenerate,
      updateSessionItems,
      showDebugErrorToast,
      stopRun,
      t,
    ],
  );

  const resetSession = useCallback(() => {
    debugFailedRef.current = false;
    stopRun();
    clearRegenerationRetryTarget();
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
  }, [clearRegenerationRetryTarget, stopRun, updateSessionItems]);

  const clearFreshAgentInteractionAnswer = useCallback(
    (itemBid: string, variableName?: string) => {
      if (!variableName || freshAgentInteractionBidsRef.current.has(itemBid)) {
        return;
      }
      freshAgentInteractionBidsRef.current.add(itemBid);
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

  const ensureContentItem = useCallback(
    (itemBid: string) => {
      if (currentContentElementBidRef.current === itemBid) {
        return itemBid;
      }
      currentContentElementBidRef.current = itemBid;
      updateSessionItems(prev => [
        ...prev.filter(item => item.generated_block_bid !== 'loading'),
        {
          element_bid: itemBid,
          generated_block_bid: itemBid,
          content: '',
          readonly: false,
          type: ChatContentItemType.CONTENT,
        },
      ]);
      return itemBid;
    },
    [updateSessionItems],
  );

  const ensureAudioItem = useCallback(
    (
      items: ChatContentItem[],
      elementBid: string,
      defaults: Partial<ChatContentItem> = {},
    ) => {
      const hasTarget = items.some(item =>
        matchesDebugElementBid(item, elementBid),
      );
      if (hasTarget) {
        return items;
      }

      return [
        ...items.filter(item => item.generated_block_bid !== 'loading'),
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
        const updatedList = [...prev].filter(
          item => item.generated_block_bid !== 'loading',
        );
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
        let nextList = prev.filter(
          item => item.generated_block_bid !== 'loading',
        );
        let completedElementBid = '';
        const hasIncomingItem = nextList.some(
          item => item.element_bid === itemBid,
        );

        if (
          previousStreamingElementBid &&
          previousStreamingElementBid !== itemBid
        ) {
          const previousItem = nextList.find(
            item => item.element_bid === previousStreamingElementBid,
          );
          const previousItemBid = resolveDebugElementBid(previousItem);
          if (isDebugActionableItem(previousItem) && previousItemBid) {
            completedElementBid = previousItemBid;
          }
        }

        if (!completedElementBid && !hasIncomingItem) {
          const latestActionableItem =
            resolveLatestDebugActionableItem(nextList);
          const latestActionableBid =
            resolveDebugElementBid(latestActionableItem);
          if (latestActionableBid && latestActionableBid !== itemBid) {
            completedElementBid = latestActionableBid;
          }
        }

        if (completedElementBid) {
          nextList = finalizeDebugElementOutputInList(
            nextList,
            completedElementBid,
          );
        }

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

        const hitIndex = nextList.findIndex(
          item => item.element_bid === itemBid,
        );
        if (hitIndex > -1) {
          const updatedList = [...nextList];
          const previousItem = updatedList[hitIndex];
          updatedList[hitIndex] = {
            ...previousItem,
            ...nextItem,
            user_input: previousItem.user_input || '',
          };
          return updatedList;
        }

        return [...nextList, nextItem];
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
    (payload: string) => {
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
        const generatedBlockBid =
          (typeof response.generated_block_bid === 'string'
            ? response.generated_block_bid
            : '') ||
          (payloadObject &&
          typeof payloadObject.generated_block_bid === 'string'
            ? payloadObject.generated_block_bid
            : '');
        if (
          responseType === DebugStreamEventType.ELEMENT ||
          responseType === DebugStreamEventType.INTERACTION ||
          responseType === DebugStreamEventType.CONTENT
        ) {
          updateSessionItems(prev =>
            prev.filter(item => item.generated_block_bid !== 'loading'),
          );
        }

        if (responseType === DebugStreamEventType.DEBUG_VARIABLES) {
          if (payloadObject) {
            runParamsRef.current.variableValues = { ...payloadObject };
            setVariableValuesSnapshot(
              normalizeDebugVariableValues(payloadObject),
            );
          }
        } else if (responseType === DebugStreamEventType.ELEMENT) {
          upsertElementDebugItem(response);
        } else if (responseType === DebugStreamEventType.INTERACTION) {
          const interactionContent = resolveResponseStringPayload(response);
          const interactionInfo = parseInteractionBlock(interactionContent);
          const variableName = interactionInfo?.variableName;
          const interactionElementBid =
            currentStreamingElementBidRef.current ||
            currentContentElementBidRef.current ||
            generatedBlockBid ||
            '';
          if (interactionElementBid) {
            clearFreshAgentInteractionAnswer(
              interactionElementBid,
              variableName,
            );
          }

          updateSessionItems((prev: ChatContentItem[]) => {
            const currentElementBid =
              currentStreamingElementBidRef.current ||
              currentContentElementBidRef.current ||
              generatedBlockBid ||
              '';
            if (!currentElementBid) {
              return prev;
            }
            const interactionBlock: ChatContentItem = {
              element_bid: currentElementBid,
              generated_block_bid: currentElementBid,
              content: interactionContent,
              readonly: false,
              user_input: '',
              type: ChatContentItemType.INTERACTION,
            };
            const nextListWithoutLoading = prev.filter(
              item => item.generated_block_bid !== 'loading',
            );
            const lastContent =
              nextListWithoutLoading[nextListWithoutLoading.length - 1];
            let nextList = nextListWithoutLoading;

            if (
              lastContent &&
              lastContent.type === ChatContentItemType.CONTENT
            ) {
              const lastContentBid =
                lastContent.generated_block_bid || lastContent.element_bid;
              if (lastContentBid) {
                nextList = finalizeDebugElementOutputInList(
                  nextList,
                  lastContentBid,
                );
              }
            }

            const hitIndex = nextList.findIndex(item =>
              matchesDebugElementBid(item, currentElementBid),
            );
            if (hitIndex > -1) {
              const updatedList = [...nextList];
              updatedList[hitIndex] = {
                ...updatedList[hitIndex],
                ...interactionBlock,
                user_input: updatedList[hitIndex].user_input,
              };
              return appendLikeStatusIfMissing(updatedList, currentElementBid);
            }

            nextList = [...nextList, interactionBlock];
            return appendLikeStatusIfMissing(nextList, currentElementBid);
          });
        } else if (responseType === DebugStreamEventType.CONTENT) {
          const markdownPayload = resolveResponseStringPayload(response);
          const contentElementBid = ensureContentItem(
            currentStreamingElementBidRef.current ||
              currentContentElementBidRef.current ||
              generatedBlockBid ||
              'preview-content',
          );
          const existingItem = sessionItemsRef.current.find(item =>
            matchesDebugElementBid(item, contentElementBid),
          );
          const prevText =
            currentContentRef.current ||
            (typeof existingItem?.content === 'string'
              ? existingItem.content
              : '');
          const nextText = mergeStreamingMarkdownText(
            prevText,
            markdownPayload || '',
          );
          currentContentRef.current = nextText;
          const displayText = maskIncompleteMermaidBlock(nextText);
          updateSessionItems(prev =>
            prev.map(item =>
              matchesDebugElementBid(item, contentElementBid)
                ? {
                    ...item,
                    content: displayText,
                    element_type: item.element_type || ELEMENT_TYPE.TEXT,
                    is_final: false,
                    shouldUseTypewriter: true,
                  }
                : item,
            ),
          );
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
          const doneIsTerminal = resolveDoneIsTerminal(response);
          finalizeDebugItems();
          doneTerminalStateRef.current = doneIsTerminal;
          currentContentElementBidRef.current = null;
          currentContentRef.current = '';
          currentStreamingElementBidRef.current = null;
          if (doneIsTerminal === true) {
            finishDebugRegenerate('success');
            stopRun();
          }
        } else if (responseType === DebugStreamEventType.TEXT_END) {
          finishDebugRegenerate('success');
          finalizeDebugItems();
          currentContentElementBidRef.current = null;
          currentContentRef.current = '';
          currentStreamingElementBidRef.current = null;
          stopRun();
        } else if (responseType === DebugStreamEventType.ERROR) {
          const errorMessage =
            resolveResponseStringPayload(response) ||
            t('module.preview.llmError');
          handleDebugBusinessError(
            errorMessage,
            resolveDebugBusinessCode(response),
          );
        } else if (responseType === DebugStreamEventType.AUDIO_SEGMENT) {
          const audioSegment = normalizeAudioSegmentPayload(
            resolveResponsePayload(response),
          );
          if (generatedBlockBid && audioSegment) {
            updateSessionItems(prevState =>
              upsertAudioSegment(
                prevState,
                generatedBlockBid,
                toAudioSegmentData(audioSegment),
                ensureAudioItem,
              ),
            );
          }
        } else if (responseType === DebugStreamEventType.AUDIO_COMPLETE) {
          const audioComplete = normalizeAudioCompletePayload(
            resolveResponsePayload(response),
          );
          if (!audioComplete) {
            return;
          }
          if (generatedBlockBid) {
            updateSessionItems(prevState =>
              upsertAudioComplete(
                prevState,
                generatedBlockBid,
                audioComplete,
                ensureAudioItem,
              ),
            );
          }
        }
      } catch (err) {
        debugWarn('[lesson-debug] SSE handling error', err);
      }
    },
    [
      appendLikeStatusIfMissing,
      clearFreshAgentInteractionAnswer,
      ensureAudioItem,
      ensureContentItem,
      finalizeDebugElementOutputInList,
      finalizeDebugItems,
      finishDebugRegenerate,
      handleDebugBusinessError,
      parseInteractionBlock,
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
      }
      if (initialVariableValuesRef.current === null) {
        initialVariableValuesRef.current = { ...(variableValues || {}) };
      }
      if (!debugSessionIdRef.current) {
        debugSessionIdRef.current = createDebugSessionId();
      }
      const retryTarget = regenerationRetryTargetRef.current;
      if (
        !reloadGeneratedBlockBid ||
        retryTarget?.generatedBlockBid !== reloadGeneratedBlockBid ||
        retryTarget.debugSessionId !== debugSessionIdRef.current ||
        retryTarget.params.shifuBid !== shifuBid ||
        retryTarget.params.outlineBid !== outlineBid ||
        retryTarget.params.mdflow !== mdflow
      ) {
        clearRegenerationRetryTarget();
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
      isStreamingRef.current = true;
      setIsStreaming(true);
      debugRegenerateResultRef.current = startDebugRegenerateTracking({
        anchor: reloadGeneratedBlockBid,
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
        finishDebugRegenerate('failed');
        stopRun();
        setErrorMessage(t('module.preview.missingApiBaseUrl'));
        return;
      }
      setErrorMessage(null);
      updateSessionItems(prev => [
        ...prev.filter(item => item.generated_block_bid !== 'loading'),
        {
          element_bid: DEBUG_LOADING_ITEM_BID,
          generated_block_bid: DEBUG_LOADING_ITEM_BID,
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
          block_index: finalBlockIndex,
          content: finalMdflow,
          variables: finalVariableValues,
          ...(reloadGeneratedBlockBid
            ? { reload_generated_block_bid: reloadGeneratedBlockBid }
            : {}),
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
        onSseData(source, data => {
          if (
            !isCurrentStreamGeneration(streamGeneration) ||
            debugFailedRef.current ||
            runStreamRef.current !== source
          ) {
            return;
          }
          handlePayload(data);
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
            finishDebugRegenerate('success');
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
            finishDebugRegenerate('success');
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
      clearRegenerationRetryTarget,
      finalizeDebugItems,
      finishDebugRegenerate,
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
      const nextItems = [...sessionItemsRef.current];
      let interactionIndex = nextItems.findIndex(item =>
        item.content?.includes(params.variableName || ''),
      );
      const matchingVariableItems =
        nextItems.filter(item =>
          item.content?.includes(params.variableName || ''),
        ) || [];
      if (matchingVariableItems.length > 1) {
        interactionIndex = nextItems.findIndex(item =>
          matchesDebugElementBid(item, elementBid),
        );
      }
      if (interactionIndex !== -1) {
        nextItems[interactionIndex] = {
          ...nextItems[interactionIndex],
          readonly: false,
          user_input: resolveInteractionSubmission(params).userInput,
        };
        const trailingRows = nextItems.slice(interactionIndex + 1);
        const preservedHelperRows = trailingRows.filter(
          item =>
            (item.parent_block_bid === elementBid ||
              item.parent_element_bid === elementBid) &&
            (item.type === ChatContentItemType.LIKE_STATUS ||
              item.type === ChatContentItemType.ASK),
        );
        nextItems.length = interactionIndex + 1;
        if (preservedHelperRows.length > 0) {
          nextItems.push(...preservedHelperRows);
        }
        updateSessionItems(nextItems);
      }

      return { nextItems, interactionIndex };
    },
    [updateSessionItems],
  );

  // Resolve the last actionable element ID and skip helper rows.
  const resolveLastActionableElementBid = useCallback(
    (items: ChatContentItem[]) => {
      const lastActionableItem = [...items].reverse().find(item => {
        const elementBid = resolveDebugElementBid(item);
        if (!elementBid || elementBid === 'loading') {
          return false;
        }

        return (
          item.type !== ChatContentItemType.LIKE_STATUS &&
          item.type !== ChatContentItemType.ASK
        );
      });

      return resolveDebugElementBid(lastActionableItem) || '';
    },
    [],
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
      if (isStreamingRef.current) {
        showOutputInProgressToast();
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

      let requiresRegeneration = false;
      const currentList = sessionItemsRef.current.slice();
      if (currentList.length > 0) {
        const lastActionableElementBid =
          resolveLastActionableElementBid(currentList);
        requiresRegeneration =
          Boolean(lastActionableElementBid) &&
          elementBid !== lastActionableElementBid;
      }
      const { values } = resolveInteractionSubmission(content);
      if (draftEdited && (requiresRegeneration || !values.length)) {
        // Only an answer to the current question can continue under an edited
        // draft; anything else starts the edited draft from its beginning.
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
        // Resubmitting an earlier answer still restarts the Debug session.
        // Content regeneration uses the separate anchored rewind path.
        restartSession();
        return true;
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
      resolveLastActionableElementBid,
      resolveLatestMdflow,
      restartSession,
    ],
  );

  const startRegeneration = useCallback(
    (generatedBlockBid: string, prefixItems: ChatContentItem[]) => {
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
        blockIndex: 0,
        userInput: undefined,
        reloadGeneratedBlockBid: generatedBlockBid,
      });
    },
    [startRun, updateSessionItems],
  );

  const regenerateContent = useCallback(
    (elementBid?: string) => {
      if (creditInsufficientAudience === null) {
        return;
      }
      if (isStreamingRef.current) {
        showOutputInProgressToast();
        return;
      }
      if (
        !elementBid ||
        resolveLatestMdflow() !== runParamsRef.current.mdflow
      ) {
        restartSession();
        return;
      }
      const currentList = sessionItemsRef.current;
      const targetIndex = currentList.findIndex(
        item =>
          item.element_bid === elementBid &&
          item.type === ChatContentItemType.CONTENT &&
          item.element_type === ELEMENT_TYPE.TEXT &&
          Boolean(item.generated_block_bid),
      );
      if (targetIndex < 0) {
        return;
      }
      const target = currentList[targetIndex];
      const generatedBlockBid = target.generated_block_bid;
      if (!generatedBlockBid) {
        return;
      }
      const blockStartIndex = resolveDebugRegenerationStartIndex(
        currentList,
        targetIndex,
      );
      const prefix = currentList.slice(0, blockStartIndex);
      regenerationRetryTargetRef.current = {
        generatedBlockBid,
        prefixItems: prefix,
        debugSessionId: debugSessionIdRef.current,
        params: {
          shifuBid: runParamsRef.current.shifuBid,
          outlineBid: runParamsRef.current.outlineBid,
          mdflow: runParamsRef.current.mdflow,
        },
      };
      setHasRegenerationRetryTarget(true);
      startRegeneration(generatedBlockBid, prefix);
    },
    [
      creditInsufficientAudience,
      resolveLatestMdflow,
      restartSession,
      showOutputInProgressToast,
      startRegeneration,
    ],
  );

  const retryRegeneration = useCallback(() => {
    if (creditInsufficientAudience === null) {
      return;
    }
    if (isStreamingRef.current) {
      showOutputInProgressToast();
      return;
    }
    const target = regenerationRetryTargetRef.current;
    if (!target) {
      return;
    }
    if (
      target.debugSessionId !== debugSessionIdRef.current ||
      target.params.shifuBid !== runParamsRef.current.shifuBid ||
      target.params.outlineBid !== runParamsRef.current.outlineBid
    ) {
      clearRegenerationRetryTarget();
      return;
    }
    if (resolveLatestMdflow() !== target.params.mdflow) {
      restartSession();
      return;
    }
    // A failed connection may already have replaced the server checkpoint.
    // Retry the logical target without restoring its discarded rows or answers.
    startRegeneration(target.generatedBlockBid, target.prefixItems);
  }, [
    clearRegenerationRetryTarget,
    creditInsufficientAudience,
    resolveLatestMdflow,
    restartSession,
    showOutputInProgressToast,
    startRegeneration,
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
        matchesDebugElementBid(item, elementBid),
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
            if (!matchesDebugElementBid(item, elementBid)) {
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
                matchesDebugElementBid(item, elementBid)
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
    regenerateContent,
    retryRegeneration,
    canRetryRegeneration:
      hasRegenerationRetryTarget &&
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
