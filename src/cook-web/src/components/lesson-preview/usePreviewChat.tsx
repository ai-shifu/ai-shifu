'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { SSE } from 'sse.js';
import { v4 as uuidv4 } from 'uuid';
import { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { createInteractionParser } from 'remark-flow';
import {
  ELEMENT_TYPE,
  LIKE_STATUS,
  type AudioCompleteData,
  type AudioSegmentData,
  type ElementType,
  type StudyRecordItem,
} from '@/c-api/studyV2';
import { getStringEnv } from '@/c-utils/envUtils';
import { resolveInteractionSubmission } from '@/c-utils/interaction-user-input';
import {
  fixMarkdownStream,
  maskIncompleteMermaidBlock,
} from '@/c-utils/markdownUtils';
import {
  getAudioTrackByPosition,
  upsertAudioComplete,
  upsertAudioSegment,
} from '@/c-utils/audio-utils';
import LoadingBar from '@/c-components/ChatUi/LoadingBar';
import { ChatContentItem, ChatContentItemType } from '@/c-types/chatUi';
import { normalizeLegacyBlockCompatList } from '@/c-utils/chatUiCompat';
import { getDynamicApiBaseUrl } from '@/config/environment';
import { useShifu, useUserStore } from '@/store';
import { toast } from '@/hooks/useToast';
import { attachSseBusinessResponseFallback } from '@/lib/request';
import { useTranslation } from 'react-i18next';
import { PreviewVariablesMap, savePreviewVariables } from './variableStorage';
import {
  buildPreviewInteractionUserInput,
  resolvePreviewGeneratedBlockBid,
  resolvePreviewRequestBlockIndex,
} from './preview-submission';

interface InteractionParseResult {
  variableName?: string;
  buttonTexts?: string[];
  buttonValues?: string[];
  placeholder?: string;
  isMultiSelect?: boolean;
}

interface StartPreviewParams {
  shifuBid?: string;
  outlineBid?: string;
  mdflow?: string;
  user_input?: Record<string, any>;
  variables?: Record<string, any>;
  block_index?: number;
  max_block_count?: number;
  systemVariableKeys?: string[];
  visual_mode?: boolean;
}

enum PREVIEW_SSE_OUTPUT_TYPE {
  ELEMENT = 'element',
  INTERACTION = 'interaction',
  CONTENT = 'content',
  DONE = 'done',
  TEXT_END = 'text_end',
  ERROR = 'error',
  AUDIO_SEGMENT = 'audio_segment',
  AUDIO_COMPLETE = 'audio_complete',
}

type PreviewSseResponseData = {
  type?: string;
  event_type?: string;
  content?: unknown;
  data?: unknown;
  generated_block_bid?: unknown;
  is_terminal?: unknown;
};

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
    console.warn('Failed to parse preview payload object:', error);
  }
  return null;
};

const resolveResponsePayload = (
  response: PreviewSseResponseData,
): Record<string, unknown> | null => {
  return (
    parseObjectPayload<Record<string, unknown>>(response.content) ||
    parseObjectPayload<Record<string, unknown>>(response.data)
  );
};

const resolveResponseStringPayload = (
  response: PreviewSseResponseData,
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
  response: PreviewSseResponseData,
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

const readNumberField = (
  payload: Record<string, unknown>,
  keys: string[],
): number | null => {
  const value = readPayloadField(payload, keys);
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const parsedValue = Number(value);
    if (Number.isFinite(parsedValue)) {
      return parsedValue;
    }
  }
  return null;
};

const readStringField = (
  payload: Record<string, unknown>,
  keys: string[],
): string | null => {
  const value = readPayloadField(payload, keys);
  return typeof value === 'string' ? value : null;
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

const normalizeAudioSegmentData = (
  payloadLike: unknown,
): AudioSegmentData | null => {
  const payload = parseObjectPayload<Record<string, unknown>>(payloadLike);
  if (!payload) {
    return null;
  }
  const segmentIndex = readNumberField(payload, [
    'segment_index',
    'segmentIndex',
  ]);
  const audioData = readStringField(payload, ['audio_data', 'audioData']);
  if (segmentIndex === null || !audioData) {
    return null;
  }

  const durationMs =
    readNumberField(payload, ['duration_ms', 'durationMs']) ?? 0;
  const isFinal = readBooleanField(payload, ['is_final', 'isFinal']) ?? false;
  const position = readNumberField(payload, ['position']);
  const elementId = readStringField(payload, ['element_id', 'elementId']);
  const slideId = readStringField(payload, ['slide_id', 'slideId']);
  const avContractValue = readPayloadField(payload, [
    'av_contract',
    'avContract',
  ]);

  return {
    segment_index: segmentIndex,
    audio_data: audioData,
    duration_ms: durationMs,
    is_final: isFinal,
    position: position ?? undefined,
    element_id: elementId ?? undefined,
    slide_id: slideId ?? undefined,
    av_contract:
      avContractValue && typeof avContractValue === 'object'
        ? (avContractValue as Record<string, any>)
        : null,
  };
};

const normalizeAudioCompleteData = (
  payloadLike: unknown,
): AudioCompleteData | null => {
  const payload = parseObjectPayload<Record<string, unknown>>(payloadLike);
  if (!payload) {
    return null;
  }
  const audioUrl = readStringField(payload, ['audio_url', 'audioUrl']) || '';
  const audioBid = readStringField(payload, ['audio_bid', 'audioBid']) || '';
  const durationMs =
    readNumberField(payload, ['duration_ms', 'durationMs']) ?? 0;
  const position = readNumberField(payload, ['position']);
  const slideId = readStringField(payload, ['slide_id', 'slideId']);
  const avContractValue = readPayloadField(payload, [
    'av_contract',
    'avContract',
  ]);

  return {
    audio_url: audioUrl,
    audio_bid: audioBid,
    duration_ms: durationMs,
    position: position ?? undefined,
    slide_id: slideId ?? undefined,
    av_contract:
      avContractValue && typeof avContractValue === 'object'
        ? (avContractValue as Record<string, any>)
        : null,
  };
};

const resolveElementPayload = (
  response: PreviewSseResponseData,
): Partial<StudyRecordItem> | null => {
  return resolveResponsePayload(response) as Partial<StudyRecordItem> | null;
};

const resolveElementBid = (
  elementRecord: Partial<StudyRecordItem> | null,
  response: PreviewSseResponseData,
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

const buildVariablesSnapshot = (
  variables?: Record<string, unknown>,
): PreviewVariablesMap => {
  if (!variables) {
    return {};
  }
  return Object.entries(variables).reduce<PreviewVariablesMap>((acc, entry) => {
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

const resolvePreviewItemBid = (
  item?: Pick<ChatContentItem, 'generated_block_bid' | 'element_bid'> | null,
): string => {
  if (!item) {
    return '';
  }
  return item.generated_block_bid || item.element_bid || '';
};

const isPreviewActionableItem = (
  item?: Pick<
    ChatContentItem,
    'type' | 'generated_block_bid' | 'element_bid'
  > | null,
): boolean => {
  const resolvedBid = resolvePreviewItemBid(item);
  if (!resolvedBid || resolvedBid === 'loading') {
    return false;
  }
  return (
    item?.type === ChatContentItemType.CONTENT ||
    item?.type === ChatContentItemType.INTERACTION
  );
};

const resolveLatestPreviewActionableItem = (
  items: ChatContentItem[],
): ChatContentItem | undefined => {
  return [...items].reverse().find(item => isPreviewActionableItem(item));
};

export function usePreviewChat() {
  const { t } = useTranslation();
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
  const sseParams = useRef<StartPreviewParams>({});
  const sseRef = useRef<any>(null);
  const ttsSseRef = useRef<Record<string, any>>({});
  const isStreamingRef = useRef(false);
  const doneTerminalStateRef = useRef<boolean | null>(null);
  const [variablesSnapshot, setVariablesSnapshot] =
    useState<PreviewVariablesMap>({});
  const interactionParserRef = useRef(createInteractionParser());
  const autoSubmittedBlocksRef = useRef<Set<string>>(new Set());
  const tryAutoSubmitInteractionRef = useRef<
    (blockId: string, content?: string | null) => void
  >(() => {});
  const continuePreviewFromLatestStateRef = useRef<
    (latestActionableItem?: ChatContentItem) => boolean
  >(() => false);
  const submittedInteractionBlockBidRef = useRef<string | null>(null);
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

  const removeAutoSubmittedBlocks = useCallback((blockIds: string[]) => {
    if (!blockIds?.length) {
      return;
    }
    blockIds.forEach(id => {
      if (id) {
        autoSubmittedBlocksRef.current.delete(id);
      }
    });
  }, []);
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
        const normalizedNext = normalizeLegacyBlockCompatList(next);
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
    setVariablesSnapshot(prev => {
      const mergedVariables = {
        ...((sseParams.current.variables as PreviewVariablesMap) || prev),
        [name]: value,
      };
      sseParams.current.variables = mergedVariables;
      return mergedVariables;
    });
  }, []);

  const persistVariables = useCallback(
    ({
      shifuBid,
      systemVariableKeys,
      variables,
    }: {
      shifuBid?: string;
      systemVariableKeys?: string[];
      variables?: PreviewVariablesMap;
    }) => {
      const resolvedVariables =
        variables ||
        (sseParams.current.variables as PreviewVariablesMap) ||
        variablesSnapshot;
      const resolvedShifuBid = shifuBid || sseParams.current.shifuBid;
      const resolvedSystemKeys =
        systemVariableKeys || sseParams.current.systemVariableKeys || [];
      if (!resolvedShifuBid) {
        return;
      }
      savePreviewVariables(
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

  const buildAutoSendParams = useCallback(
    (
      info: InteractionParseResult | null,
      rawValue: string,
    ): OnSendContentParams | null => {
      if (!info?.variableName) {
        return null;
      }
      const normalized = (rawValue ?? '').toString().trim();
      if (!normalized) {
        return null;
      }

      if (info.isMultiSelect) {
        const tokens = splitPresetValues(normalized);
        if (!tokens.length) {
          return null;
        }
        const selectedValues: string[] = [];
        const customInputs: string[] = [];
        for (const token of tokens) {
          const mapped = normalizeButtonValue(token, info);
          if (mapped) {
            selectedValues.push(mapped.value);
            continue;
          }
          if (info.placeholder) {
            customInputs.push(token);
            continue;
          }
          return null;
        }
        if (!selectedValues.length && !customInputs.length) {
          return null;
        }
        return {
          variableName: info.variableName,
          selectedValues: selectedValues.length ? selectedValues : undefined,
          inputText: customInputs.length ? customInputs.join(', ') : undefined,
        };
      }

      const mapped = normalizeButtonValue(normalized, info);
      if (mapped) {
        return {
          variableName: info.variableName,
          buttonText: mapped.display || normalized,
          selectedValues: [mapped.value],
        };
      }

      if (info.placeholder) {
        return {
          variableName: info.variableName,
          inputText: normalized,
        };
      }
      return null;
    },
    [normalizeButtonValue, splitPresetValues],
  );

  const closeTtsStream = useCallback((blockId: string) => {
    const source = ttsSseRef.current[blockId];
    if (!source) {
      return;
    }
    source.close();
    delete ttsSseRef.current[blockId];
  }, []);

  const closeAllTtsStreams = useCallback(() => {
    Object.values(ttsSseRef.current).forEach(source => {
      source?.close?.();
    });
    ttsSseRef.current = {};
  }, []);

  const stopPreview = useCallback(() => {
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }
    closeAllTtsStreams();
    isStreamingRef.current = false;
    currentStreamingElementBidRef.current = null;
    setIsLoading(false);
  }, [closeAllTtsStreams]);

  const resetPreview = useCallback(() => {
    stopPreview();
    setTrackedContentList([]);
    setError(null);
    currentContentRef.current = '';
    currentContentIdRef.current = null;
    currentStreamingElementBidRef.current = null;
    submittedInteractionBlockBidRef.current = null;
    autoSubmittedBlocksRef.current.clear();
    setVariablesSnapshot({});
  }, [stopPreview, setTrackedContentList]);

  const ensureContentItem = useCallback(
    (blockId: string) => {
      if (currentContentIdRef.current === blockId) {
        return blockId;
      }
      currentContentIdRef.current = blockId;
      setTrackedContentList(prev => [
        ...prev.filter(item => item.generated_block_bid !== 'loading'),
        {
          element_bid: blockId,
          generated_block_bid: blockId,
          content: '',
          readonly: false,
          type: ChatContentItemType.CONTENT,
        },
      ]);
      return blockId;
    },
    [setTrackedContentList],
  );

  const ensureAudioItem = useCallback(
    (
      items: ChatContentItem[],
      blockId: string,
      defaults: Partial<ChatContentItem> = {},
    ) => {
      const hasTarget = items.some(
        item => item.generated_block_bid === blockId,
      );
      if (hasTarget) {
        return items;
      }

      return [
        ...items.filter(item => item.generated_block_bid !== 'loading'),
        {
          element_bid: blockId,
          generated_block_bid: blockId,
          content: '',
          readonly: false,
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

  const finalizePreviewItems = useCallback(() => {
    let latestActionableItem: ChatContentItem | undefined;
    flushSync(() => {
      setTrackedContentList((prev: ChatContentItem[]) => {
        let updatedList = [...prev].filter(
          item => item.generated_block_bid !== 'loading',
        );
        latestActionableItem = resolveLatestPreviewActionableItem(updatedList);
        const latestActionableBid = resolvePreviewItemBid(latestActionableItem);
        if (latestActionableBid) {
          updatedList = appendLikeStatusIfMissing(
            updatedList,
            latestActionableBid,
          );
        }
        return updatedList;
      });
    });
    return latestActionableItem;
  }, [appendLikeStatusIfMissing, setTrackedContentList]);

  const shouldContinueFromLatestActionableItem = useCallback(
    (latestActionableItem?: ChatContentItem) => {
      if (latestActionableItem?.type !== ChatContentItemType.INTERACTION) {
        return true;
      }
      const submittedInteractionBlockBid =
        submittedInteractionBlockBidRef.current;
      return Boolean(
        submittedInteractionBlockBid &&
        resolvePreviewItemBid(latestActionableItem) ===
          submittedInteractionBlockBid,
      );
    },
    [],
  );

  const stopPreviewAndContinueIfNeeded = useCallback(
    (latestActionableItem?: ChatContentItem) => {
      const shouldContinue =
        shouldContinueFromLatestActionableItem(latestActionableItem);
      stopPreview();
      if (!shouldContinue) {
        return false;
      }
      return continuePreviewFromLatestStateRef.current(latestActionableItem);
    },
    [shouldContinueFromLatestActionableItem, stopPreview],
  );

  const upsertElementPreviewItem = useCallback(
    (response: PreviewSseResponseData) => {
      const elementRecord = resolveElementPayload(response);
      const itemBid = resolveElementBid(elementRecord, response);
      if (!itemBid) {
        return;
      }

      const elementType = resolveElementType(elementRecord);
      const generatedBlockBid = resolvePreviewGeneratedBlockBid({
        elementGeneratedBlockBid: elementRecord?.generated_block_bid,
        responseGeneratedBlockBid: response.generated_block_bid,
        fallbackBid: itemBid,
      });
      const elementContent =
        typeof elementRecord?.content === 'string' ? elementRecord.content : '';
      const isInteractionElement = elementType === ELEMENT_TYPE.INTERACTION;
      const interactionInfo = isInteractionElement
        ? parseInteractionBlock(elementContent)
        : null;
      const variableName = interactionInfo?.variableName;
      const currentVariables = (sseParams.current.variables ||
        {}) as PreviewVariablesMap;
      const rawValue =
        variableName && currentVariables ? currentVariables[variableName] : '';
      const autoParams =
        rawValue && interactionInfo
          ? buildAutoSendParams(interactionInfo, rawValue)
          : null;
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
          item =>
            item.element_bid === itemBid ||
            item.generated_block_bid === itemBid,
        );

        if (
          previousStreamingElementBid &&
          previousStreamingElementBid !== itemBid
        ) {
          const previousItem = nextList.find(
            item =>
              item.element_bid === previousStreamingElementBid ||
              item.generated_block_bid === previousStreamingElementBid,
          );
          const previousItemBid = resolvePreviewItemBid(previousItem);
          if (isPreviewActionableItem(previousItem) && previousItemBid) {
            completedElementBid = previousItemBid;
          }
        }

        if (!completedElementBid && !hasIncomingItem) {
          const latestActionableItem =
            resolveLatestPreviewActionableItem(nextList);
          const latestActionableBid =
            resolvePreviewItemBid(latestActionableItem);
          if (latestActionableBid && latestActionableBid !== itemBid) {
            completedElementBid = latestActionableBid;
          }
        }

        if (completedElementBid) {
          nextList = appendLikeStatusIfMissing(nextList, completedElementBid);
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
          user_input: autoParams
            ? resolveInteractionSubmission(autoParams).userInput
            : '',
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
            user_input: nextItem.user_input || previousItem.user_input || '',
          };
          return updatedList;
        }

        return [...nextList, nextItem];
      });
      currentStreamingElementBidRef.current = itemBid;

      if (isInteractionElement) {
        tryAutoSubmitInteractionRef.current(itemBid, elementContent);
      }
    },
    [
      appendLikeStatusIfMissing,
      buildAutoSendParams,
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
        const response = JSON.parse(
          normalizedPayload,
        ) as PreviewSseResponseData;
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
          responseType === PREVIEW_SSE_OUTPUT_TYPE.ELEMENT ||
          responseType === PREVIEW_SSE_OUTPUT_TYPE.INTERACTION ||
          responseType === PREVIEW_SSE_OUTPUT_TYPE.CONTENT
        ) {
          setTrackedContentList(prev =>
            prev.filter(item => item.generated_block_bid !== 'loading'),
          );
        }

        if (responseType === PREVIEW_SSE_OUTPUT_TYPE.ELEMENT) {
          upsertElementPreviewItem(response);
        } else if (responseType === PREVIEW_SSE_OUTPUT_TYPE.INTERACTION) {
          const interactionContent = resolveResponseStringPayload(response);
          const interactionInfo = parseInteractionBlock(interactionContent);
          const variableName = interactionInfo?.variableName;
          const currentVariables = (sseParams.current.variables ||
            {}) as PreviewVariablesMap;
          const rawValue =
            variableName && currentVariables
              ? currentVariables[variableName]
              : undefined;
          const autoParams =
            rawValue && interactionInfo
              ? buildAutoSendParams(interactionInfo, rawValue)
              : null;

          setTrackedContentList((prev: ChatContentItem[]) => {
            const currentBlockBid =
              blockId || currentContentIdRef.current || '';
            if (!currentBlockBid) {
              return prev;
            }
            const interactionBlock: ChatContentItem = {
              element_bid: currentBlockBid,
              generated_block_bid: currentBlockBid,
              content: interactionContent,
              readonly: false,
              user_input: autoParams
                ? resolveInteractionSubmission(autoParams).userInput
                : '',
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
                nextList = appendLikeStatusIfMissing(nextList, lastContentBid);
              }
            }

            const hitIndex = nextList.findIndex(
              item =>
                item.generated_block_bid === currentBlockBid ||
                item.element_bid === currentBlockBid,
            );
            if (hitIndex > -1) {
              const updatedList = [...nextList];
              updatedList[hitIndex] = {
                ...updatedList[hitIndex],
                ...interactionBlock,
                user_input:
                  interactionBlock.user_input ||
                  updatedList[hitIndex].user_input,
              };
              return appendLikeStatusIfMissing(updatedList, currentBlockBid);
            }

            nextList = [...nextList, interactionBlock];
            return appendLikeStatusIfMissing(nextList, currentBlockBid);
          });
          const interactionBlockBid =
            blockId || currentContentIdRef.current || '';
          if (interactionBlockBid) {
            tryAutoSubmitInteractionRef.current(
              interactionBlockBid,
              interactionContent,
            );
          }
        } else if (responseType === PREVIEW_SSE_OUTPUT_TYPE.CONTENT) {
          const markdownPayload = resolveResponseStringPayload(response);
          const contentId = ensureContentItem(
            blockId || currentContentIdRef.current || 'preview-content',
          );
          const prevText = currentContentRef.current || '';
          const delta = fixMarkdownStream(prevText, markdownPayload || '');
          const nextText = prevText + delta;
          currentContentRef.current = nextText;
          const displayText = maskIncompleteMermaidBlock(nextText);
          setTrackedContentList(prev =>
            prev.map(item =>
              item.generated_block_bid === contentId
                ? { ...item, content: displayText }
                : item,
            ),
          );
        } else if (responseType === PREVIEW_SSE_OUTPUT_TYPE.DONE) {
          const doneIsTerminal = resolveDoneIsTerminal(response);
          const latestActionableItem = finalizePreviewItems();
          doneTerminalStateRef.current = doneIsTerminal;
          currentContentIdRef.current = null;
          currentContentRef.current = '';
          currentStreamingElementBidRef.current = null;
          if (doneIsTerminal === true) {
            stopPreviewAndContinueIfNeeded(latestActionableItem);
          }
        } else if (responseType === PREVIEW_SSE_OUTPUT_TYPE.TEXT_END) {
          const latestActionableItem = finalizePreviewItems();
          currentContentIdRef.current = null;
          currentContentRef.current = '';
          currentStreamingElementBidRef.current = null;
          stopPreviewAndContinueIfNeeded(latestActionableItem);
        } else if (responseType === PREVIEW_SSE_OUTPUT_TYPE.ERROR) {
          const errorMessage =
            resolveResponseStringPayload(response) ||
            t('module.preview.llmError');
          toast({
            title: t('module.preview.llmError'),
            description: errorMessage,
            variant: 'destructive',
          });
          setError(errorMessage);
          stopPreview();
        } else if (responseType === PREVIEW_SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
          const audioSegment = normalizeAudioSegmentData(
            resolveResponsePayload(response),
          );
          if (blockId && audioSegment) {
            setTrackedContentList(prevState =>
              upsertAudioSegment(
                prevState,
                blockId,
                audioSegment,
                ensureAudioItem,
              ),
            );
          }
        } else if (responseType === PREVIEW_SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
          const audioComplete = normalizeAudioCompleteData(
            resolveResponsePayload(response),
          );
          if (!audioComplete) {
            return;
          }
          const normalizedAudioComplete = {
            ...audioComplete,
            audio_url: audioComplete.audio_url || undefined,
          };
          if (blockId) {
            setTrackedContentList(prevState =>
              upsertAudioComplete(
                prevState,
                blockId,
                normalizedAudioComplete,
                ensureAudioItem,
              ),
            );
          }
        }
      } catch (err) {
        console.warn('preview SSE handling error:', err);
      }
    },
    [
      appendLikeStatusIfMissing,
      buildAutoSendParams,
      ensureAudioItem,
      ensureContentItem,
      finalizePreviewItems,
      parseInteractionBlock,
      stopPreviewAndContinueIfNeeded,
      setTrackedContentList,
      stopPreview,
      t,
      upsertElementPreviewItem,
    ],
  );

  useEffect(() => {
    return () => {
      stopPreview();
    };
  }, [stopPreview]);

  const startPreview = useCallback(
    async ({
      shifuBid,
      outlineBid,
      mdflow,
      block_index,
      user_input,
      variables,
      max_block_count,
      systemVariableKeys,
      visual_mode = false,
    }: StartPreviewParams) => {
      const normalizedUserInput =
        user_input &&
        Object.values(user_input).some(value =>
          Array.isArray(value)
            ? value.length > 0
            : value !== undefined && value !== null && `${value}`.trim() !== '',
        )
          ? user_input
          : undefined;
      const mergedParams: StartPreviewParams = {
        ...sseParams.current,
        shifuBid,
        outlineBid,
        mdflow,
        block_index,
        variables,
        max_block_count,
        systemVariableKeys,
        visual_mode,
      };
      const {
        shifuBid: finalShifuBid,
        outlineBid: finalOutlineBid,
        mdflow: finalMdflow,
        block_index: finalBlockIndex = 0,
        variables: finalVariables = {},
        max_block_count: finalMaxBlockCount,
        visual_mode: finalVisualMode = false,
      } = mergedParams;
      sseParams.current = mergedParams;
      setVariablesSnapshot(buildVariablesSnapshot(finalVariables));
      submittedInteractionBlockBidRef.current = normalizedUserInput
        ? `${finalBlockIndex}`
        : null;

      if (!finalShifuBid || !finalOutlineBid) {
        setError('Invalid preview params');
        return;
      }

      if (
        typeof finalMaxBlockCount === 'number' &&
        finalMaxBlockCount >= 0 &&
        finalBlockIndex >= finalMaxBlockCount
      ) {
        stopPreview();
        return;
      }

      stopPreview();
      doneTerminalStateRef.current = null;
      const resolvedBaseUrl = await resolveBaseUrl();
      if (!resolvedBaseUrl) {
        setError('Missing API base URL');
        return;
      }
      setTrackedContentList(prev => [
        ...prev.filter(item => item.generated_block_bid !== 'loading'),
        {
          element_bid: 'loading',
          generated_block_bid: 'loading',
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
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
          'X-Request-ID': uuidv4().replace(/-/g, ''),
        };
        if (tokenValue) {
          headers.Authorization = `Bearer ${tokenValue}`;
          headers.Token = tokenValue;
        }
        const payload: Record<string, unknown> = {
          block_index: finalBlockIndex,
          content: finalMdflow,
          variables: finalVariables,
          visual_mode: finalVisualMode,
        };
        if (normalizedUserInput) {
          payload.user_input = normalizedUserInput;
        }
        const source = new SSE(
          `${resolvedBaseUrl}/api/learn/shifu/${finalShifuBid}/preview/${finalOutlineBid}`,
          {
            headers,
            payload: JSON.stringify(payload),
            method: 'POST',
          },
        );
        sseRef.current = source;
        attachSseBusinessResponseFallback(source, {
          onHandled: error => {
            if (sseRef.current !== source) {
              return;
            }
            setError(error.message || t('module.preview.llmError'));
            stopPreview();
          },
        });
        source.addEventListener('message', event => {
          const raw = event?.data;
          if (!raw) return;
          const payload = String(raw).trim();
          if (payload) {
            handlePayload(payload);
            setIsLoading(false);
          }
        });
        source.addEventListener('error', err => {
          if (sseRef.current !== source) {
            return;
          }
          console.error('[preview sse error]', err);
          const latestActionableItem = finalizePreviewItems();
          const hasReceivedNonTerminalDone =
            doneTerminalStateRef.current === false;
          if (hasReceivedNonTerminalDone) {
            stopPreviewAndContinueIfNeeded(latestActionableItem);
            return;
          }
          // Treat abrupt stream closure as success only for non-interaction blocks.
          // Interaction submissions must receive the block-level done marker first.
          const shouldContinuePreviewOnAbruptClose =
            doneTerminalStateRef.current === null &&
            latestActionableItem?.type !== ChatContentItemType.INTERACTION;
          if (shouldContinuePreviewOnAbruptClose) {
            const didContinue =
              continuePreviewFromLatestStateRef.current(latestActionableItem);
            if (didContinue) {
              return;
            }
            stopPreview();
            return;
          }
          setError('Preview stream error');
          stopPreview();
        });
        source.stream();
      } catch (err) {
        console.error('preview stream error', err);
        setError((err as Error)?.message || 'Preview failed');
        stopPreview();
        setIsLoading(false);
      }
    },
    [
      finalizePreviewItems,
      handlePayload,
      resolveBaseUrl,
      setTrackedContentList,
      stopPreview,
      stopPreviewAndContinueIfNeeded,
      t,
    ],
  );

  const continuePreviewFromLatestState = useCallback(
    (latestActionableItem?: ChatContentItem) => {
      if (!shouldContinueFromLatestActionableItem(latestActionableItem)) {
        return false;
      }
      const nextIndex = (sseParams.current?.block_index || 0) + 1;
      const totalBlocks = sseParams.current?.max_block_count;
      if (
        typeof totalBlocks === 'number' &&
        totalBlocks >= 0 &&
        nextIndex >= totalBlocks
      ) {
        return false;
      }
      startPreview({
        ...sseParams.current,
        block_index: nextIndex,
      });
      return true;
    },
    [shouldContinueFromLatestActionableItem, startPreview],
  );

  useEffect(() => {
    continuePreviewFromLatestStateRef.current = continuePreviewFromLatestState;
  }, [continuePreviewFromLatestState]);

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
        needChangeItemIndex = newList.findIndex(
          item => item.generated_block_bid === blockBid,
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

  const prefillInteractionBlock = useCallback(
    (blockBid: string, params: OnSendContentParams) => {
      setTrackedContentList(prev =>
        prev.map(item =>
          item.generated_block_bid === blockBid
            ? {
                ...item,
                readonly: false,
                user_input: resolveInteractionSubmission(params).userInput,
              }
            : item,
        ),
      );
    },
    [setTrackedContentList],
  );

  // Resolve the last actionable block id and skip helper rows.
  const resolveLastActionableBlockBid = useCallback(
    (items: ChatContentItem[]) => {
      const lastActionableItem = [...items].reverse().find(item => {
        const generatedBlockBid = item.generated_block_bid || item.element_bid;
        if (!generatedBlockBid || generatedBlockBid === 'loading') {
          return false;
        }

        return (
          item.type !== ChatContentItemType.LIKE_STATUS &&
          item.type !== ChatContentItemType.ASK
        );
      });

      return (
        lastActionableItem?.generated_block_bid ||
        lastActionableItem?.element_bid ||
        ''
      );
    },
    [],
  );

  const performSend = useCallback(
    (
      content: OnSendContentParams,
      blockBid: string,
      options?: { skipStreamCheck?: boolean; skipConfirm?: boolean },
    ) => {
      if (!options?.skipStreamCheck && isStreamingRef.current) {
        showOutputInProgressToast();
        return false;
      }

      const { variableName } = content;
      const normalizedVariableName =
        typeof variableName === 'string' ? variableName : '';
      const hasVariableName = Boolean(normalizedVariableName);
      const listUpdateContent =
        typeof variableName === 'string'
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
      if (isReGenerate && !options?.skipConfirm) {
        setPendingRegenerate({ content: listUpdateContent, blockBid });
        setShowRegenerateConfirm(true);
        return false;
      }

      const { newList, needChangeItemIndex } = updateContentListWithUserOperate(
        listUpdateContent,
        blockBid,
      );

      if (!options?.skipStreamCheck) {
        if (needChangeItemIndex === -1) {
          setTrackedContentList(newList);
        }
      } else {
        prefillInteractionBlock(blockBid, content);
      }

      const { values } = resolveInteractionSubmission(content);

      if (!values.length) {
        return false;
      }

      const nextValue = values.join(',');

      if (hasVariableName) {
        const nextVariables: PreviewVariablesMap = {
          ...(sseParams.current.variables as PreviewVariablesMap),
          [normalizedVariableName]: nextValue,
        };
        sseParams.current.variables = nextVariables;
        setVariablesSnapshot(buildVariablesSnapshot(nextVariables));
        savePreviewVariables(
          sseParams.current.shifuBid,
          { [normalizedVariableName]: nextValue },
          sseParams.current.systemVariableKeys || [],
        );
      }

      const requestVariables: PreviewVariablesMap =
        (sseParams.current.variables as PreviewVariablesMap) || {};
      const userInputPayload = buildPreviewInteractionUserInput(
        normalizedVariableName,
        values,
      );

      const needReGenerate = isReGenerate && needChangeItemIndex !== -1;
      if (needReGenerate) {
        const removedBlockIds = currentList
          .slice(needChangeItemIndex)
          .map(item => item.generated_block_bid)
          .filter((item): item is string => Boolean(item));
        if (removedBlockIds.length) {
          removeAutoSubmittedBlocks(removedBlockIds);
        }
      }

      const nextParams: StartPreviewParams = {
        ...sseParams.current,
        block_index: resolvePreviewRequestBlockIndex(
          blockBid,
          sseParams.current.block_index ?? 0,
        ),
        variables: requestVariables,
      };
      if (userInputPayload) {
        nextParams.user_input = userInputPayload;
      } else if ('user_input' in nextParams) {
        delete nextParams.user_input;
      }
      startPreview(nextParams);
      return true;
    },
    [
      removeAutoSubmittedBlocks,
      setTrackedContentList,
      showOutputInProgressToast,
      startPreview,
      updateContentListWithUserOperate,
      prefillInteractionBlock,
      resolveLastActionableBlockBid,
    ],
  );

  const onRefresh = useCallback(
    async (generatedBlockBid: string) => {
      if (isStreamingRef.current) {
        showOutputInProgressToast();
        return;
      }

      const originalList = [...contentListRef.current];
      const newList = [...originalList];
      const needChangeItemIndex = newList.findIndex(
        item => item.generated_block_bid === generatedBlockBid,
      );
      if (needChangeItemIndex === -1) {
        return;
      }

      const nextBlockIndex = resolvePreviewRequestBlockIndex(
        generatedBlockBid,
        needChangeItemIndex,
      );

      const removedBlockIds = originalList
        .slice(needChangeItemIndex)
        .map(item => item.generated_block_bid)
        .filter((item): item is string => Boolean(item));
      if (removedBlockIds.length) {
        removeAutoSubmittedBlocks(removedBlockIds);
      }

      newList.length = needChangeItemIndex;
      setTrackedContentList(newList);
      const latestMdflow = resolveLatestMdflow();
      startPreview({
        ...sseParams.current,
        mdflow: latestMdflow,
        block_index: nextBlockIndex,
      });
    },
    [
      resolveLatestMdflow,
      removeAutoSubmittedBlocks,
      setTrackedContentList,
      showOutputInProgressToast,
      startPreview,
    ],
  );

  const onSend = useCallback(
    (content: OnSendContentParams, blockBid: string) => {
      performSend(content, blockBid);
    },
    [performSend],
  );

  const tryAutoSubmitInteraction = useCallback(
    (blockId: string, content?: string | null) => {
      if (!content || autoSubmittedBlocksRef.current.has(blockId)) {
        return;
      }
      const parsedInfo = parseInteractionBlock(content);
      const variableName = parsedInfo?.variableName;
      if (!variableName) {
        return;
      }
      const currentVariables = (sseParams.current.variables ||
        {}) as PreviewVariablesMap;
      const rawValue = currentVariables[variableName];
      if (!rawValue) {
        return;
      }
      const sendParams = buildAutoSendParams(parsedInfo, rawValue);
      if (!sendParams) {
        return;
      }
      autoSubmittedBlocksRef.current.add(blockId);
      const delay = parsedInfo?.isMultiSelect ? 1000 : 600;
      setTimeout(() => {
        performSend(sendParams, blockId, {
          skipStreamCheck: true,
          skipConfirm: true,
        });
      }, delay);
    },
    [buildAutoSendParams, parseInteractionBlock, performSend],
  );

  useEffect(() => {
    tryAutoSubmitInteractionRef.current = tryAutoSubmitInteraction;
  }, [tryAutoSubmitInteraction]);

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
      if (!shifuBid || !blockId) {
        return null;
      }

      const existingItem = contentListRef.current.find(
        item => item.generated_block_bid === blockId,
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

      setTrackedContentList(prevState =>
        ensureAudioItem(
          prevState.map(item => {
            if (item.generated_block_bid !== blockId) {
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

      const resolvedBaseUrl = await resolveBaseUrl();
      const tokenValue = useUserStore.getState().getToken();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'X-Request-ID': uuidv4().replace(/-/g, ''),
      };
      if (tokenValue) {
        headers.Authorization = `Bearer ${tokenValue}`;
        headers.Token = tokenValue;
      }

      return new Promise((resolve, reject) => {
        const source = new SSE(
          `${resolvedBaseUrl}/api/learn/shifu/${shifuBid}/tts/preview?preview_mode=true`,
          {
            headers,
            payload: JSON.stringify({ text: text || '' }),
            method: 'POST',
          },
        );
        ttsSseRef.current[blockId] = source;
        attachSseBusinessResponseFallback(source, {
          onHandled: error => {
            setTrackedContentList(prevState =>
              ensureAudioItem(
                prevState.map(item => {
                  if (item.generated_block_bid !== blockId) {
                    return item;
                  }
                  return {
                    ...item,
                    isAudioStreaming: false,
                  };
                }),
                blockId,
              ),
            );
            closeTtsStream(blockId);
            reject(error);
          },
        });

        source.addEventListener('message', event => {
          const raw = event?.data;
          if (!raw) return;
          const payload = String(raw).trim();
          if (!payload) return;

          try {
            const response = JSON.parse(payload);
            if (response?.type === PREVIEW_SSE_OUTPUT_TYPE.AUDIO_SEGMENT) {
              const audioPayload = response.content ?? response.data;
              const audioSegment = normalizeAudioSegmentData(audioPayload);
              if (!audioSegment) {
                return;
              }
              setTrackedContentList(prevState =>
                upsertAudioSegment(
                  prevState,
                  blockId,
                  audioSegment,
                  ensureAudioItem,
                ),
              );
              return;
            }

            if (response?.type === PREVIEW_SSE_OUTPUT_TYPE.AUDIO_COMPLETE) {
              const audioPayload = response.content ?? response.data;
              const audioComplete = normalizeAudioCompleteData(audioPayload);
              if (!audioComplete) {
                return;
              }
              const normalizedAudioComplete = {
                ...audioComplete,
                audio_url: audioComplete.audio_url || undefined,
              };
              setTrackedContentList(prevState =>
                upsertAudioComplete(
                  prevState,
                  blockId,
                  normalizedAudioComplete,
                  ensureAudioItem,
                ),
              );
              closeTtsStream(blockId);
              resolve(audioComplete ?? null);
            }
          } catch (err) {
            console.warn('preview audio stream parse error:', err);
          }
        });

        source.addEventListener('error', err => {
          console.error('[preview audio sse error]', err);
          setTrackedContentList(prevState =>
            ensureAudioItem(
              prevState.map(item => {
                if (item.generated_block_bid !== blockId) {
                  return item;
                }
                return {
                  ...item,
                  isAudioStreaming: false,
                };
              }),
              blockId,
            ),
          );
          closeTtsStream(blockId);
          reject(new Error('Preview audio stream failed'));
        });

        source.stream();
      });
    },
    [closeTtsStream, ensureAudioItem, resolveBaseUrl, setTrackedContentList],
  );

  return {
    items,
    isLoading,
    isStreaming: isStreamingRef.current,
    error,
    startPreview,
    stopPreview,
    resetPreview,
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
