'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { SSE } from 'sse.js';
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { createInteractionParser, normalizeVariableName } from 'remark-flow';
import {
  ELEMENT_TYPE,
  LIKE_STATUS,
  type AudioCompleteData,
  type ElementType,
  type StudyRecordItem,
} from '@/api/studyV2';
import { getStringEnv } from '@/lib/envUtils';
import { resolveInteractionSubmission } from '@/lib/interaction-user-input';
import {
  mergeStreamingMarkdownText,
  maskIncompleteMermaidBlock,
} from '@/lib/markdownUtils';
import { debugError, debugWarn } from '@/lib/debugConsole';
import {
  getAudioTrackByPosition,
  normalizeAudioCompletePayload,
  normalizeAudioSegmentPayload,
  toAudioSegmentData,
  upsertAudioComplete,
  upsertAudioSegment,
} from '@/lib/audio-utils';
import LoadingBar from '@/components/ChatUi/LoadingBar';
import { ChatContentItem, ChatContentItemType } from '@/types/chatUi';
import { normalizeLegacyBlockCompatList } from '@/lib/chatUiCompat';
import { getDynamicApiBaseUrl } from '@/config/environment';
import { useShifu, useUserStore } from '@/store';
import { toast } from '@/hooks/useToast';
import {
  resolveLearnerErrorMessage,
  resolveLearnerErrorToast,
} from '@/lib/learnerError';
import { showAiServiceErrorToast } from '@/lib/aiServiceToast';
import {
  type CreditInsufficientAudience,
  getCreditInsufficientMessage,
  isCreditInsufficientBusinessCode,
  showCreditInsufficientToast,
} from '@/lib/creditInsufficientToast';
import {
  attachSseBusinessResponseFallback,
  getCurrentLanguageHeaders,
} from '@/lib/request';
import type { ErrorWithCode } from '@/lib/request';
import { buildTraceHeaders } from '@/lib/request-trace';
import { useTranslation } from 'react-i18next';
import { useTracking } from '@/hooks/useTracking';
import { DebugVariablesMap, saveDebugVariables } from './variableStorage';
import {
  buildDebugInteractionUserInput,
  resolveDebugGeneratedBlockBid,
} from './debug-submission';

interface InteractionParseResult {
  variableName?: string;
  buttonTexts?: string[];
  buttonValues?: string[];
  placeholder?: string;
  isMultiSelect?: boolean;
}

interface StartDebugParams {
  shifuBid?: string;
  outlineBid?: string;
  mdflow?: string;
  user_input?: Record<string, unknown>;
  variables?: Record<string, unknown>;
  block_index?: number;
  max_block_count?: number;
  systemVariableKeys?: string[];
}

type DebugSseSource = InstanceType<typeof SSE>;

// The editor Debug API requires a session ID, so every browser context gets one.
// The server keys a debug session by author, course, lesson and this ID, so the
// fallback only has to differ between this author's Debug runs; it is not a secret.
let fallbackDebugSessionCount = 0;
const fallbackDebugSessionId = () => {
  fallbackDebugSessionCount += 1;
  return `${Date.now().toString(36)}-${fallbackDebugSessionCount.toString(36)}`;
};

const newDebugSessionId = () => {
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
  return fallbackDebugSessionId();
};

export const buildInteractionContinuationDebugParams = ({
  currentParams,
  latestMdflow,
  blockIndex,
  variables,
  userInput,
}: {
  currentParams: StartDebugParams;
  latestMdflow: string;
  blockIndex: number;
  variables: DebugVariablesMap;
  userInput?: Record<string, string[]>;
}): StartDebugParams => {
  const nextParams: StartDebugParams = {
    ...currentParams,
    mdflow: latestMdflow,
    block_index: blockIndex,
    variables,
  };

  if (userInput) {
    nextParams.user_input = userInput;
  } else if ('user_input' in nextParams) {
    delete nextParams.user_input;
  }

  return nextParams;
};

enum DEBUG_SSE_OUTPUT_TYPE {
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

type DebugSseResponseData = {
  type?: string;
  event_type?: string;
  code?: number;
  content?: unknown;
  data?: unknown;
  generated_block_bid?: unknown;
  is_terminal?: unknown;
};

const resolveDebugBusinessCode = (
  response: DebugSseResponseData,
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
    debugWarn('[preview-chat] failed to parse preview payload object', error);
  }
  return null;
};

const resolveResponsePayload = (
  response: DebugSseResponseData,
): Record<string, unknown> | null => {
  return (
    parseObjectPayload<Record<string, unknown>>(response.content) ||
    parseObjectPayload<Record<string, unknown>>(response.data)
  );
};

const resolveResponseStringPayload = (
  response: DebugSseResponseData,
): string => {
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

const resolveDoneIsTerminal = (
  response: DebugSseResponseData,
): boolean | null => {
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
  response: DebugSseResponseData,
): Partial<StudyRecordItem> | null => {
  return resolveResponsePayload(response) as Partial<StudyRecordItem> | null;
};

const resolveElementBid = (
  elementRecord: Partial<StudyRecordItem> | null,
  response: DebugSseResponseData,
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

const buildVariablesSnapshot = (
  variables?: Record<string, unknown>,
): DebugVariablesMap => {
  if (!variables) {
    return {};
  }
  return Object.entries(variables).reduce<DebugVariablesMap>((acc, entry) => {
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
  }, {});
};

const resolveDebugItemBid = (
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
  const resolvedBid = resolveDebugItemBid(item);
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

const matchDebugItemBid = (item: ChatContentItem, bid: string) => {
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

export function useDebugChat({
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
  const [error, setError] = useState<string | null>(null);
  const contentListRef = useRef<ChatContentItem[]>([]);
  const [contentList, setContentList] = useState<ChatContentItem[]>([]);
  const currentContentRef = useRef<string>('');
  const currentContentIdRef = useRef<string | null>(null);
  const currentStreamingElementBidRef = useRef<string | null>(null);
  const sseParams = useRef<StartDebugParams>({});
  const initialVariablesRef = useRef<Record<string, unknown> | null>(null);
  const sseRef = useRef<DebugSseSource | null>(null);
  const ttsSseRef = useRef<Record<string, DebugSseSource>>({});
  const ttsCancelRef = useRef<Record<string, () => void>>({});
  const debugRunIdRef = useRef(0);
  const debugSessionIdRef = useRef(newDebugSessionId());
  // Whether a run of the current debug session has started streaming. Editing
  // the script only restarts the debug session once a run has started.
  const debugRunStartedRef = useRef(false);
  const trackedEngineSessionIdRef = useRef<string | null>(null);
  const isStreamingRef = useRef(false);
  const debugFailedRef = useRef(false);
  const doneTerminalStateRef = useRef<boolean | null>(null);
  const [variablesSnapshot, setVariablesSnapshot] = useState<DebugVariablesMap>(
    {},
  );
  const interactionParserRef = useRef(createInteractionParser());
  const freshAgentInteractionBidsRef = useRef<Set<string>>(new Set());
  const resolveLatestMdflow = useCallback(() => {
    const latest = getCurrentMdflow?.();
    if (typeof latest === 'string') {
      return latest;
    }
    return (sseParams.current?.mdflow as string) || '';
  }, [getCurrentMdflow]);
  const [pendingRegenerate, setPendingRegenerate] = useState<{
    content: OnSendContentParams;
    blockBid: string;
  } | null>(null);
  const [showRegenerateConfirm, setShowRegenerateConfirm] = useState(false);
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
        const normalizedNext = normalizeLegacyBlockCompatList(
          syncDebugActionableFinalState(next),
        );
        contentListRef.current = normalizedNext;
        return normalizedNext;
      });
    },
    [],
  );

  const handleVariableChange = useCallback((name: string, value: string) => {
    if (!name) {
      return;
    }
    const update = { [name]: value };
    if (initialVariablesRef.current && name === 'sys_user_language') {
      // Language is a Debug setting, not an answer to discard on restart.
      initialVariablesRef.current = {
        ...initialVariablesRef.current,
        ...update,
      };
    }
    const mergedVariables = {
      ...(sseParams.current.variables || {}),
      ...update,
    };
    sseParams.current.variables = mergedVariables;
    setVariablesSnapshot(buildVariablesSnapshot(mergedVariables));
  }, []);

  const persistVariables = useCallback(
    ({
      shifuBid,
      systemVariableKeys,
      variables,
    }: {
      shifuBid?: string;
      systemVariableKeys?: string[];
      variables?: DebugVariablesMap;
    }) => {
      const resolvedVariables =
        variables ||
        (sseParams.current.variables as DebugVariablesMap) ||
        variablesSnapshot;
      const resolvedShifuBid = shifuBid || sseParams.current.shifuBid;
      const resolvedSystemKeys =
        systemVariableKeys || sseParams.current.systemVariableKeys || [];
      if (!resolvedShifuBid) {
        return;
      }
      saveDebugVariables(
        resolvedShifuBid,
        resolvedVariables,
        resolvedSystemKeys,
      );
    },
    [variablesSnapshot],
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
        debugWarn('[preview-chat] failed to parse interaction block', error);
        return null;
      }
    },
    [],
  );

  const closeTtsStream = useCallback((blockId: string) => {
    const source = ttsSseRef.current[blockId];
    if (!source) {
      return;
    }
    delete ttsSseRef.current[blockId];
    delete ttsCancelRef.current[blockId];
    source.close();
  }, []);

  const closeAllTtsStreams = useCallback(() => {
    // Cancellation settles callers even after stopDebug invalidates the run.
    Object.values(ttsCancelRef.current).forEach(cancel => cancel());
    ttsCancelRef.current = {};
    Object.values(ttsSseRef.current).forEach(source => {
      source?.close?.();
    });
    ttsSseRef.current = {};
  }, []);

  const invalidateDebugRun = useCallback(() => {
    debugRunIdRef.current += 1;
    return debugRunIdRef.current;
  }, []);

  const isCurrentDebugRun = useCallback(
    (runId: number) => debugRunIdRef.current === runId,
    [],
  );

  const stopDebug = useCallback(() => {
    invalidateDebugRun();
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }
    closeAllTtsStreams();
    isStreamingRef.current = false;
    currentStreamingElementBidRef.current = null;
    setIsLoading(false);
  }, [closeAllTtsStreams, invalidateDebugRun]);

  const handleDebugBusinessError = useCallback(
    (errorOrMessage?: string | ErrorWithCode | null, fallbackCode?: number) => {
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
          stopDebug();
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
      setTrackedContentList(prev =>
        replaceDebugLoadingWithBusinessError(
          prev,
          displayMessage,
          resolvedCode,
        ),
      );
      setError(displayMessage);
      stopDebug();
    },
    [
      creditInsufficientAudience,
      setTrackedContentList,
      showDebugErrorToast,
      stopDebug,
      t,
    ],
  );

  const resetDebug = useCallback(() => {
    debugFailedRef.current = false;
    stopDebug();
    setTrackedContentList([]);
    setError(null);
    currentContentRef.current = '';
    currentContentIdRef.current = null;
    currentStreamingElementBidRef.current = null;
    freshAgentInteractionBidsRef.current.clear();
    setVariablesSnapshot({});
    initialVariablesRef.current = null;
    debugSessionIdRef.current = newDebugSessionId();
    debugRunStartedRef.current = false;
    trackedEngineSessionIdRef.current = null;
  }, [stopDebug, setTrackedContentList]);

  const clearFreshAgentInteractionAnswer = useCallback(
    (itemBid: string, variableName?: string) => {
      if (!variableName || freshAgentInteractionBidsRef.current.has(itemBid)) {
        return;
      }
      freshAgentInteractionBidsRef.current.add(itemBid);
      const currentVariables = (sseParams.current.variables ||
        {}) as DebugVariablesMap;
      if (!(variableName in currentVariables)) {
        return;
      }
      const nextVariables = { ...currentVariables };
      delete nextVariables[variableName];
      sseParams.current.variables = nextVariables;
      setVariablesSnapshot(buildVariablesSnapshot(nextVariables));
    },
    [],
  );

  const ensureContentItem = useCallback(
    (itemBid: string) => {
      if (currentContentIdRef.current === itemBid) {
        return itemBid;
      }
      currentContentIdRef.current = itemBid;
      setTrackedContentList(prev => [
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
    [setTrackedContentList],
  );

  const ensureAudioItem = useCallback(
    (
      items: ChatContentItem[],
      blockId: string,
      defaults: Partial<ChatContentItem> = {},
    ) => {
      const hasTarget = items.some(item => matchDebugItemBid(item, blockId));
      if (hasTarget) {
        return items;
      }

      return [
        ...items.filter(item => item.generated_block_bid !== 'loading'),
        {
          element_bid: blockId,
          generated_block_bid: blockId,
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
    (parentBlockBid: string): ChatContentItem => ({
      element_bid: `${parentBlockBid}-feedback`,
      parent_element_bid: parentBlockBid,
      parent_block_bid: parentBlockBid,
      generated_block_bid: `${parentBlockBid}-feedback`,
      like_status: LIKE_STATUS.NONE,
      type: ChatContentItemType.LIKE_STATUS,
    }),
    [],
  );

  const appendLikeStatusIfMissing = useCallback(
    (list: ChatContentItem[], parentBlockBid: string): ChatContentItem[] => {
      if (!parentBlockBid) {
        return list;
      }
      const hasLikeStatus = list.some(
        item =>
          item.type === ChatContentItemType.LIKE_STATUS &&
          (item.parent_block_bid === parentBlockBid ||
            item.parent_element_bid === parentBlockBid),
      );
      if (hasLikeStatus) {
        return list;
      }
      return [...list, buildLikeStatusItem(parentBlockBid)];
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
      setTrackedContentList((prev: ChatContentItem[]) => {
        const updatedList = [...prev].filter(
          item => item.generated_block_bid !== 'loading',
        );
        const latestActionableBid = resolveDebugItemBid(
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
  }, [finalizeDebugElementOutputInList, setTrackedContentList]);

  const upsertElementDebugItem = useCallback(
    (response: DebugSseResponseData) => {
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

      setTrackedContentList(prev => {
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
          const previousItemBid = resolveDebugItemBid(previousItem);
          if (isDebugActionableItem(previousItem) && previousItemBid) {
            completedElementBid = previousItemBid;
          }
        }

        if (!completedElementBid && !hasIncomingItem) {
          const latestActionableItem =
            resolveLatestDebugActionableItem(nextList);
          const latestActionableBid = resolveDebugItemBid(latestActionableItem);
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
      currentContentIdRef.current = itemBid;
      currentStreamingElementBidRef.current = itemBid;
    },
    [
      clearFreshAgentInteractionAnswer,
      finalizeDebugElementOutputInList,
      parseInteractionBlock,
      setTrackedContentList,
    ],
  );

  const handlePayload = useCallback(
    (payload: string) => {
      try {
        const normalizedPayload = payload.replace(/^data:\s*/, '').trim();
        if (!normalizedPayload) {
          return;
        }
        const response = JSON.parse(normalizedPayload) as DebugSseResponseData;
        const responseType =
          typeof response.type === 'string'
            ? response.type
            : typeof response.event_type === 'string'
              ? response.event_type
              : '';
        const payloadObject = resolveResponsePayload(response);
        const blockId =
          (typeof response.generated_block_bid === 'string'
            ? response.generated_block_bid
            : '') ||
          (payloadObject &&
          typeof payloadObject.generated_block_bid === 'string'
            ? payloadObject.generated_block_bid
            : '');
        if (
          responseType === DEBUG_SSE_OUTPUT_TYPE.ELEMENT ||
          responseType === DEBUG_SSE_OUTPUT_TYPE.INTERACTION ||
          responseType === DEBUG_SSE_OUTPUT_TYPE.CONTENT
        ) {
          setTrackedContentList(prev =>
            prev.filter(item => item.generated_block_bid !== 'loading'),
          );
        }

        if (responseType === DEBUG_SSE_OUTPUT_TYPE.ELEMENT) {
          upsertElementDebugItem(response);
        } else if (responseType === DEBUG_SSE_OUTPUT_TYPE.INTERACTION) {
          const interactionContent = resolveResponseStringPayload(response);
          const interactionInfo = parseInteractionBlock(interactionContent);
          const variableName = interactionInfo?.variableName;
          const interactionBlockBid =
            currentStreamingElementBidRef.current ||
            currentContentIdRef.current ||
            blockId ||
            '';
          if (interactionBlockBid) {
            clearFreshAgentInteractionAnswer(interactionBlockBid, variableName);
          }

          setTrackedContentList((prev: ChatContentItem[]) => {
            const currentBlockBid =
              currentStreamingElementBidRef.current ||
              currentContentIdRef.current ||
              blockId ||
              '';
            if (!currentBlockBid) {
              return prev;
            }
            const interactionBlock: ChatContentItem = {
              element_bid: currentBlockBid,
              generated_block_bid: currentBlockBid,
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
              matchDebugItemBid(item, currentBlockBid),
            );
            if (hitIndex > -1) {
              const updatedList = [...nextList];
              updatedList[hitIndex] = {
                ...updatedList[hitIndex],
                ...interactionBlock,
                user_input: updatedList[hitIndex].user_input,
              };
              return appendLikeStatusIfMissing(updatedList, currentBlockBid);
            }

            nextList = [...nextList, interactionBlock];
            return appendLikeStatusIfMissing(nextList, currentBlockBid);
          });
        } else if (responseType === DEBUG_SSE_OUTPUT_TYPE.CONTENT) {
          const markdownPayload = resolveResponseStringPayload(response);
          const contentId = ensureContentItem(
            currentStreamingElementBidRef.current ||
              currentContentIdRef.current ||
              blockId ||
              'preview-content',
          );
          const existingItem = contentListRef.current.find(item =>
            matchDebugItemBid(item, contentId),
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
          setTrackedContentList(prev =>
            prev.map(item =>
              matchDebugItemBid(item, contentId)
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
        } else if (responseType === DEBUG_SSE_OUTPUT_TYPE.DEBUG_ENGINE) {
          debugRunStartedRef.current = true;
          if (
            response.content === '2.0' &&
            trackedEngineSessionIdRef.current !== debugSessionIdRef.current
          ) {
            trackedEngineSessionIdRef.current = debugSessionIdRef.current;
            void trackEvent('creator_lesson_preview_engine_started', {
              engine: 'v2',
              shifu_bid: sseParams.current.shifuBid,
              outline_bid: sseParams.current.outlineBid,
            });
          }
        } else if (responseType === DEBUG_SSE_OUTPUT_TYPE.DONE) {
          const doneIsTerminal = resolveDoneIsTerminal(response);
          finalizeDebugItems();
          doneTerminalStateRef.current = doneIsTerminal;
          currentContentIdRef.current = null;
          currentContentRef.current = '';
          currentStreamingElementBidRef.current = null;
          if (doneIsTerminal === true) {
            stopDebug();
          }
        } else if (responseType === DEBUG_SSE_OUTPUT_TYPE.TEXT_END) {
          finalizeDebugItems();
          currentContentIdRef.current = null;
          currentContentRef.current = '';
          currentStreamingElementBidRef.current = null;
          stopDebug();
        } else if (responseType === DEBUG_SSE_OUTPUT_TYPE.ERROR) {
          const errorMessage =
            resolveResponseStringPayload(response) ||
            t('module.preview.llmError');
          handleDebugBusinessError(
            errorMessage,
            resolveDebugBusinessCode(response),
          );
        } else if (responseType === DEBUG_SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
          const audioSegment = normalizeAudioSegmentPayload(
            resolveResponsePayload(response),
          );
          if (blockId && audioSegment) {
            setTrackedContentList(prevState =>
              upsertAudioSegment(
                prevState,
                blockId,
                toAudioSegmentData(audioSegment),
                ensureAudioItem,
              ),
            );
          }
        } else if (responseType === DEBUG_SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
          const audioComplete = normalizeAudioCompletePayload(
            resolveResponsePayload(response),
          );
          if (!audioComplete) {
            return;
          }
          if (blockId) {
            setTrackedContentList(prevState =>
              upsertAudioComplete(
                prevState,
                blockId,
                audioComplete,
                ensureAudioItem,
              ),
            );
          }
        }
      } catch (err) {
        debugWarn('[preview-chat] SSE handling error', err);
      }
    },
    [
      appendLikeStatusIfMissing,
      clearFreshAgentInteractionAnswer,
      ensureAudioItem,
      ensureContentItem,
      finalizeDebugElementOutputInList,
      finalizeDebugItems,
      handleDebugBusinessError,
      parseInteractionBlock,
      stopDebug,
      trackEvent,
      setTrackedContentList,
      t,
      upsertElementDebugItem,
    ],
  );

  useEffect(() => {
    return () => {
      stopDebug();
    };
  }, [stopDebug]);

  const startDebug = useCallback(
    async ({
      shifuBid,
      outlineBid,
      mdflow,
      block_index,
      user_input,
      variables,
      max_block_count,
      systemVariableKeys,
    }: StartDebugParams) => {
      if (creditInsufficientAudience === null) {
        return;
      }
      let normalizedUserInput =
        user_input &&
        Object.values(user_input).some(value =>
          Array.isArray(value)
            ? value.length > 0
            : value !== undefined && value !== null && `${value}`.trim() !== '',
        )
          ? user_input
          : undefined;
      if (debugRunStartedRef.current && mdflow !== sseParams.current.mdflow) {
        // An answer to an edited question belongs to the old script. Start the
        // new draft from its beginning with a new debug session instead.
        variables = { ...(initialVariablesRef.current || {}) };
        resetDebug();
        normalizedUserInput = undefined;
        block_index = 0;
      }
      if (initialVariablesRef.current === null) {
        initialVariablesRef.current = { ...(variables || {}) };
      }
      if (!debugSessionIdRef.current) {
        debugSessionIdRef.current = newDebugSessionId();
      }
      const mergedParams: StartDebugParams = {
        ...sseParams.current,
        shifuBid,
        outlineBid,
        mdflow,
        block_index,
        variables,
        max_block_count,
        systemVariableKeys,
      };
      const {
        shifuBid: finalShifuBid,
        outlineBid: finalOutlineBid,
        mdflow: finalMdflow,
        block_index: finalBlockIndex = 0,
        variables: finalVariables = {},
        max_block_count: finalMaxBlockCount,
      } = mergedParams;
      debugFailedRef.current = false;
      sseParams.current = mergedParams;
      setVariablesSnapshot(buildVariablesSnapshot(finalVariables));

      if (!finalShifuBid || !finalOutlineBid) {
        setError(t('module.preview.invalidParams'));
        return;
      }

      if (
        typeof finalMaxBlockCount === 'number' &&
        finalMaxBlockCount >= 0 &&
        finalBlockIndex >= finalMaxBlockCount
      ) {
        stopDebug();
        return;
      }

      stopDebug();
      const debugRunId = invalidateDebugRun();
      doneTerminalStateRef.current = null;
      const resolvedBaseUrl = await resolveBaseUrl();
      if (!resolvedBaseUrl) {
        setError(t('module.preview.missingApiBaseUrl'));
        return;
      }
      setTrackedContentList(prev => [
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
      currentContentIdRef.current = null;
      currentStreamingElementBidRef.current = null;

      try {
        const tokenValue = useUserStore.getState().getToken();
        const traceHeaders = buildTraceHeaders({
          'Content-Type': 'application/json',
          ...getCurrentLanguageHeaders(),
          ...(tokenValue
            ? {
                Authorization: `Bearer ${tokenValue}`,
                Token: tokenValue,
              }
            : {}),
        });
        const payload: Record<string, unknown> = {
          block_index: finalBlockIndex,
          content: finalMdflow,
          variables: finalVariables,
          ...(debugSessionIdRef.current
            ? { debug_session_id: debugSessionIdRef.current }
            : {}),
        };
        if (normalizedUserInput) {
          payload.user_input = normalizedUserInput;
        }
        const url = `${resolvedBaseUrl}/api/learn/shifu/${finalShifuBid}/preview/${finalOutlineBid}`;
        const source = new SSE(url, {
          headers: traceHeaders.headers,
          payload: JSON.stringify(payload),
          method: 'POST',
        });
        sseRef.current = source;
        attachSseBusinessResponseFallback(source, {
          requestToken: tokenValue || '',
          meta: {
            url,
            method: 'POST',
            requestToken: tokenValue || '',
            requestId: traceHeaders.requestId,
            harnessRunId: traceHeaders.harnessRunId,
            skipErrorToast: true,
            creditInsufficientAudience,
          },
          onHandled: error => {
            if (sseRef.current !== source) {
              return;
            }
            handleDebugBusinessError(error);
          },
        });
        source.addEventListener('message', event => {
          if (
            !isCurrentDebugRun(debugRunId) ||
            debugFailedRef.current ||
            sseRef.current !== source
          ) {
            return;
          }
          const raw = event?.data;
          if (!raw) return;
          const payload = String(raw).trim();
          if (payload) {
            handlePayload(payload);
            setIsLoading(false);
          }
        });
        source.addEventListener('error', err => {
          if (!isCurrentDebugRun(debugRunId) || sseRef.current !== source) {
            return;
          }
          debugError('[preview-chat] preview SSE error', err);
          finalizeDebugItems();
          const hasReceivedNonTerminalDone =
            doneTerminalStateRef.current === false;
          if (hasReceivedNonTerminalDone) {
            stopDebug();
            return;
          }
          handleDebugBusinessError(t('module.preview.streamError'));
        });
        source.stream();
      } catch (err) {
        debugFailedRef.current = true;
        debugError('[preview-chat] preview stream error', err);
        handleDebugBusinessError(
          resolveLearnerErrorMessage({
            error: err as ErrorWithCode,
            fallbackMessage: t('module.preview.requestFailed'),
          }),
        );
        stopDebug();
        setIsLoading(false);
      }
    },
    [
      finalizeDebugItems,
      creditInsufficientAudience,
      handleDebugBusinessError,
      handlePayload,
      invalidateDebugRun,
      isCurrentDebugRun,
      resolveBaseUrl,
      resetDebug,
      setTrackedContentList,
      stopDebug,
      t,
    ],
  );

  const restartAgentDebug = useCallback(() => {
    const currentParams = { ...sseParams.current };
    const initialVariables = { ...(initialVariablesRef.current || {}) };
    resetDebug();
    void startDebug({
      ...currentParams,
      mdflow: resolveLatestMdflow(),
      variables: initialVariables,
      block_index: 0,
      user_input: undefined,
    });
  }, [resetDebug, resolveLatestMdflow, startDebug]);

  const updateContentListWithUserOperate = useCallback(
    (
      params: OnSendContentParams,
      blockBid: string,
    ): { newList: ChatContentItem[]; needChangeItemIndex: number } => {
      const newList = [...contentListRef.current];
      let needChangeItemIndex = newList.findIndex(item =>
        item.content?.includes(params.variableName || ''),
      );
      const sameVariableValueItems =
        newList.filter(item =>
          item.content?.includes(params.variableName || ''),
        ) || [];
      if (sameVariableValueItems.length > 1) {
        needChangeItemIndex = newList.findIndex(item =>
          matchDebugItemBid(item, blockBid),
        );
      }
      if (needChangeItemIndex !== -1) {
        newList[needChangeItemIndex] = {
          ...newList[needChangeItemIndex],
          readonly: false,
          user_input: resolveInteractionSubmission(params).userInput,
        };
        const trailingRows = newList.slice(needChangeItemIndex + 1);
        const preservedHelperRows = trailingRows.filter(
          item =>
            (item.parent_block_bid === blockBid ||
              item.parent_element_bid === blockBid) &&
            (item.type === ChatContentItemType.LIKE_STATUS ||
              item.type === ChatContentItemType.ASK),
        );
        newList.length = needChangeItemIndex + 1;
        if (preservedHelperRows.length > 0) {
          newList.push(...preservedHelperRows);
        }
        setTrackedContentList(newList);
      }

      return { newList, needChangeItemIndex };
    },
    [setTrackedContentList],
  );

  // Resolve the last actionable block id and skip helper rows.
  const resolveLastActionableBlockBid = useCallback(
    (items: ChatContentItem[]) => {
      const lastActionableItem = [...items].reverse().find(item => {
        const elementBid = resolveDebugItemBid(item);
        if (!elementBid || elementBid === 'loading') {
          return false;
        }

        return (
          item.type !== ChatContentItemType.LIKE_STATUS &&
          item.type !== ChatContentItemType.ASK
        );
      });

      return resolveDebugItemBid(lastActionableItem) || '';
    },
    [],
  );

  const performSend = useCallback(
    (
      content: OnSendContentParams,
      blockBid: string,
      options?: { skipConfirm?: boolean },
    ) => {
      if (creditInsufficientAudience === null) {
        return false;
      }
      if (isStreamingRef.current) {
        showOutputInProgressToast();
        return false;
      }
      if (resolveLatestMdflow() !== sseParams.current.mdflow) {
        restartAgentDebug();
        return true;
      }

      const { variableName } = content;
      const normalizedVariableName =
        normalizeVariableName(variableName ?? '') || '';
      const hasVariableName = Boolean(normalizedVariableName);
      const listUpdateContent =
        variableName === normalizedVariableName
          ? content
          : { ...content, variableName: normalizedVariableName };

      let isReGenerate = false;
      const currentList = contentListRef.current.slice();
      if (currentList.length > 0) {
        const lastActionableBlockBid =
          resolveLastActionableBlockBid(currentList);
        isReGenerate =
          Boolean(lastActionableBlockBid) &&
          blockBid !== lastActionableBlockBid;
      }
      if (isReGenerate) {
        if (!options?.skipConfirm) {
          setPendingRegenerate({ content: listUpdateContent, blockBid });
          setShowRegenerateConfirm(true);
          return false;
        }
        // Editor debug has no persisted turn blocks to rewind. Start a new lesson
        // rather than send an old answer to the current debug session.
        restartAgentDebug();
        return true;
      }

      const { newList, needChangeItemIndex } = updateContentListWithUserOperate(
        listUpdateContent,
        blockBid,
      );
      if (needChangeItemIndex === -1) {
        setTrackedContentList(newList);
      }

      const { values } = resolveInteractionSubmission(content);

      if (!values.length) {
        return false;
      }

      const nextValue = values.join(',');

      if (hasVariableName) {
        const nextVariables: DebugVariablesMap = {
          ...(sseParams.current.variables as DebugVariablesMap),
          [normalizedVariableName]: nextValue,
        };
        sseParams.current.variables = nextVariables;
        setVariablesSnapshot(buildVariablesSnapshot(nextVariables));
        saveDebugVariables(
          sseParams.current.shifuBid,
          { [normalizedVariableName]: nextValue },
          sseParams.current.systemVariableKeys || [],
        );
      }

      const requestVariables: DebugVariablesMap =
        (sseParams.current.variables as DebugVariablesMap) || {};
      const userInputPayload = buildDebugInteractionUserInput(
        normalizedVariableName,
        values,
      );

      const nextParams = buildInteractionContinuationDebugParams({
        currentParams: sseParams.current,
        latestMdflow: resolveLatestMdflow(),
        blockIndex: sseParams.current.block_index ?? 0,
        variables: requestVariables,
        userInput: userInputPayload,
      });
      startDebug(nextParams);
      return true;
    },
    [
      creditInsufficientAudience,
      setTrackedContentList,
      showOutputInProgressToast,
      startDebug,
      updateContentListWithUserOperate,
      resolveLastActionableBlockBid,
      resolveLatestMdflow,
      restartAgentDebug,
    ],
  );

  // Editor debug cannot rewind a debug session, so regenerating any element
  // restarts the lesson.
  const onRefresh = useCallback(() => {
    if (creditInsufficientAudience === null) {
      return;
    }
    if (isStreamingRef.current) {
      showOutputInProgressToast();
      return;
    }
    restartAgentDebug();
  }, [
    creditInsufficientAudience,
    restartAgentDebug,
    showOutputInProgressToast,
  ]);

  const onSend = useCallback(
    (content: OnSendContentParams, blockBid: string) => {
      performSend(content, blockBid);
    },
    [performSend],
  );

  const handleConfirmRegenerate = useCallback(() => {
    if (!pendingRegenerate) {
      setShowRegenerateConfirm(false);
      return;
    }
    performSend(pendingRegenerate.content, pendingRegenerate.blockBid, {
      skipConfirm: true,
    });
    setPendingRegenerate(null);
    setShowRegenerateConfirm(false);
  }, [pendingRegenerate, performSend]);

  const handleCancelRegenerate = useCallback(() => {
    setPendingRegenerate(null);
    setShowRegenerateConfirm(false);
  }, []);

  const nullRenderBar = useCallback(() => null, []);

  const items = useMemo(
    () =>
      contentList.map(item => ({
        ...item,
        customRenderBar: item.customRenderBar || nullRenderBar,
      })),
    [contentList, nullRenderBar],
  );

  const requestAudioForBlock = useCallback(
    async ({
      shifuBid,
      blockId,
      text,
    }: {
      shifuBid: string;
      blockId: string;
      text: string;
    }): Promise<AudioCompleteData | null> => {
      if (creditInsufficientAudience === null || !shifuBid || !blockId) {
        return null;
      }
      const debugRunId = debugRunIdRef.current;

      const existingItem = contentListRef.current.find(item =>
        matchDebugItemBid(item, blockId),
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

      if (ttsSseRef.current[blockId]) {
        return null;
      }

      const resolvedBaseUrl = await resolveBaseUrl();
      if (!isCurrentDebugRun(debugRunId)) {
        throw new DOMException('Preview audio request cancelled', 'AbortError');
      }

      setTrackedContentList(prevState =>
        ensureAudioItem(
          prevState.map(item => {
            if (!matchDebugItemBid(item, blockId)) {
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
          blockId,
          {
            audioTracks: [],
            audioUrl: undefined,
            audioDurationMs: undefined,
            isAudioStreaming: true,
          },
        ),
      );

      const tokenValue = useUserStore.getState().getToken();
      const traceHeaders = buildTraceHeaders({
        'Content-Type': 'application/json',
        ...getCurrentLanguageHeaders(),
        ...(tokenValue
          ? {
              Authorization: `Bearer ${tokenValue}`,
              Token: tokenValue,
            }
          : {}),
      });

      return new Promise((resolve, reject) => {
        const url = `${resolvedBaseUrl}/api/learn/shifu/${shifuBid}/tts/preview?preview_mode=true`;
        const source = new SSE(url, {
          headers: traceHeaders.headers,
          payload: JSON.stringify({ text: text || '' }),
          method: 'POST',
        });
        ttsSseRef.current[blockId] = source;
        let settled = false;
        const settleFailure = (error: Error) => {
          if (settled || ttsSseRef.current[blockId] !== source) {
            return;
          }
          settled = true;
          setTrackedContentList(prevState =>
            ensureAudioItem(
              prevState.map(item =>
                matchDebugItemBid(item, blockId)
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
              blockId,
            ),
          );
          closeTtsStream(blockId);
          reject(error);
        };
        const fail = (error: Error) => {
          if (isCurrentDebugRun(debugRunId)) settleFailure(error);
        };
        ttsCancelRef.current[blockId] = () =>
          settleFailure(
            new DOMException('Preview audio request cancelled', 'AbortError'),
          );
        attachSseBusinessResponseFallback(source, {
          requestToken: tokenValue || '',
          meta: {
            url,
            method: 'POST',
            requestToken: tokenValue || '',
            requestId: traceHeaders.requestId,
            harnessRunId: traceHeaders.harnessRunId,
            creditInsufficientAudience,
          },
          onHandled: fail,
        });

        source.addEventListener('message', event => {
          if (
            !isCurrentDebugRun(debugRunId) ||
            debugFailedRef.current ||
            ttsSseRef.current[blockId] !== source
          ) {
            return;
          }
          const raw = event?.data;
          if (!raw) return;
          const payload = String(raw).trim();
          if (!payload) return;

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
            if (response?.type === DEBUG_SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
              const audioPayload = response.content ?? response.data;
              const audioSegment = normalizeAudioSegmentPayload(audioPayload);
              if (!audioSegment) {
                return;
              }
              setTrackedContentList(prevState =>
                upsertAudioSegment(
                  prevState,
                  blockId,
                  toAudioSegmentData(audioSegment),
                  ensureAudioItem,
                ),
              );
              return;
            }

            if (response?.type === DEBUG_SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
              const audioPayload = response.content ?? response.data;
              const audioComplete = normalizeAudioCompletePayload(audioPayload);
              if (!audioComplete) {
                return;
              }
              setTrackedContentList(prevState =>
                upsertAudioComplete(
                  prevState,
                  blockId,
                  audioComplete,
                  ensureAudioItem,
                ),
              );
              settled = true;
              closeTtsStream(blockId);
              resolve(audioComplete ?? null);
            }
          } catch (err) {
            debugWarn('[preview-chat] preview audio stream parse error', err);
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
      isCurrentDebugRun,
      resolveBaseUrl,
      setTrackedContentList,
    ],
  );

  return {
    items,
    isLoading,
    isStreaming: isStreamingRef.current,
    error,
    startDebug,
    stopDebug,
    resetDebug,
    onSend,
    onRefresh,
    persistVariables,
    onVariableChange: handleVariableChange,
    variables: variablesSnapshot,
    requestAudioForBlock,
    reGenerateConfirm: {
      open: showRegenerateConfirm,
      onConfirm: handleConfirmRegenerate,
      onCancel: handleCancelRegenerate,
    },
  };
}
