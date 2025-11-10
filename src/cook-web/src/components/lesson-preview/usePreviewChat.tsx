'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SSE } from 'sse.js';
import { v4 as uuidv4 } from 'uuid';
import { OnSendContentParams } from 'markdown-flow-ui';
import { createInteractionParser } from 'remark-flow';
import LoadingBar from '@/app/c/[[...id]]/Components/ChatUi/LoadingBar';
import {
  ChatContentItem,
  ChatContentItemType,
} from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';
import { LIKE_STATUS } from '@/c-api/studyV2';
import { getStringEnv } from '@/c-utils/envUtils';
import {
  fixMarkdownStream,
  maskIncompleteMermaidBlock,
} from '@/c-utils/markdownUtils';
import { useUserStore } from '@/store';
import { toast } from '@/hooks/useToast';
import { useTranslation } from 'react-i18next';
import { PreviewVariablesMap, savePreviewVariables } from './variableStorage';

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
}

enum PREVIEW_SSE_OUTPUT_TYPE {
  INTERACTION = 'interaction',
  CONTENT = 'content',
  TEXT_END = 'text_end',
}

export function usePreviewChat() {
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const contentListRef = useRef<ChatContentItem[]>([]);
  const [contentList, setContentList] = useState<ChatContentItem[]>([]);
  const currentContentRef = useRef<string>('');
  const currentContentIdRef = useRef<string | null>(null);
  const sseParams = useRef<StartPreviewParams>({});
  const sseRef = useRef<any>(null);
  const isStreamingRef = useRef(false);
  const interactionParserRef = useRef(createInteractionParser());
  const autoSubmittedBlocksRef = useRef<Set<string>>(new Set());
  const tryAutoSubmitInteractionRef = useRef<
    (blockId: string, content?: string | null) => void
  >(() => {});
  const showOutputInProgressToast = useCallback(() => {
    toast({
      title: t('module.chat.outputInProgress'),
    });
  }, [t]);
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
        for (const token of tokens) {
          const mapped = normalizeButtonValue(token, info);
          if (!mapped) {
            return null;
          }
          selectedValues.push(mapped.value);
        }
        if (!selectedValues.length) {
          return null;
        }
        return {
          variableName: info.variableName,
          selectedValues,
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

  const stopPreview = useCallback(() => {
    if (sseRef.current) {
      sseRef.current.close();
      sseRef.current = null;
    }
    isStreamingRef.current = false;
  }, []);

  const resetPreview = useCallback(() => {
    stopPreview();
    setTrackedContentList([]);
    setError(null);
    currentContentRef.current = '';
    currentContentIdRef.current = null;
    autoSubmittedBlocksRef.current.clear();
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

  const handlePayload = useCallback(
    (payload: string) => {
      try {
        const response = JSON.parse(payload);
        const blockId = String(response.generated_block_bid ?? '');
        console.log('response', response);
        if (
          response.type === PREVIEW_SSE_OUTPUT_TYPE.INTERACTION ||
          response.type === PREVIEW_SSE_OUTPUT_TYPE.CONTENT
        ) {
          setTrackedContentList(prev =>
            prev.filter(item => item.generated_block_bid !== 'loading'),
          );
        }

        if (response.type === PREVIEW_SSE_OUTPUT_TYPE.INTERACTION) {
          const interactionContent = response.data?.mdflow ?? '';
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
            const interactionBlock: ChatContentItem = {
              generated_block_bid: blockId,
              content: interactionContent,
              readonly: false,
              defaultButtonText: autoParams?.buttonText || '',
              defaultInputText: autoParams?.inputText || '',
              defaultSelectedValues: autoParams?.selectedValues,
              type: ChatContentItemType.INTERACTION,
            };
            const lastContent = prev[prev.length - 1];
            if (
              lastContent &&
              lastContent.type === ChatContentItemType.CONTENT
            ) {
              return [
                ...prev,
                {
                  parent_block_bid: lastContent.generated_block_bid,
                  generated_block_bid: `${lastContent.generated_block_bid}-feedback`,
                  like_status: LIKE_STATUS.NONE,
                  type: ChatContentItemType.LIKE_STATUS,
                },
                interactionBlock,
              ];
            }
            return [...prev, interactionBlock];
          });
          tryAutoSubmitInteractionRef.current(
            blockId,
            interactionContent,
          );
        } else if (response.type === PREVIEW_SSE_OUTPUT_TYPE.CONTENT) {
          const contentId = ensureContentItem(blockId);
          const prevText = currentContentRef.current || '';
          const delta = fixMarkdownStream(
            prevText,
            response.data?.mdflow || '',
          );
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
        } else if (response.type === PREVIEW_SSE_OUTPUT_TYPE.TEXT_END) {
          currentContentIdRef.current = null;
          currentContentRef.current = '';
          stopPreview();

          setTrackedContentList((prev: ChatContentItem[]) => {
            const updatedList = [...prev].filter(
              item => item.generated_block_bid !== 'loading',
            );

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
              const nextIndex = (sseParams.current?.block_index || 0) + 1;
              const totalBlocks = sseParams.current?.max_block_count;
              if (
                typeof totalBlocks !== 'number' ||
                totalBlocks < 0 ||
                nextIndex < totalBlocks
              ) {
                startPreview({
                  ...sseParams.current,
                  block_index: nextIndex,
                });
              } else {
                stopPreview();
              }
            }
            return updatedList;
          });
        }
      } catch (err) {
        console.warn('preview SSE handling error:', err);
      }
    },
    [ensureContentItem, setTrackedContentList, stopPreview],
  );

  const startPreview = useCallback(
    ({
      shifuBid,
      outlineBid,
      mdflow,
      block_index,
      user_input,
      variables,
      max_block_count,
      systemVariableKeys,
    }: StartPreviewParams) => {
      const normalizedUserInput =
        user_input &&
        Object.values(user_input).some(value =>
          Array.isArray(value)
            ? value.length > 0
            : value !== undefined && value !== null && `${value}`.trim() !== '',
        )
          ? user_input
          : {};
      const mergedParams: StartPreviewParams = {
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
      sseParams.current = mergedParams;

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
      setTrackedContentList(prev => [
        ...prev.filter(item => item.generated_block_bid !== 'loading'),
        {
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

      try {
        let baseURL = getStringEnv('baseURL');
        if (!baseURL || baseURL === '' || baseURL === '/') {
          baseURL = typeof window !== 'undefined' ? window.location.origin : '';
        }
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
        };
        if (normalizedUserInput) {
          payload.user_input = normalizedUserInput;
        }
        const source = new SSE(
          `${baseURL}/api/learn/shifu/${finalShifuBid}/preview/${finalOutlineBid}`,
          {
            headers,
            payload: JSON.stringify(payload),
            method: 'POST',
          },
        );
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
          console.error('[preview sse error]', err);
          setError('Preview stream error');
          stopPreview();
        });
        source.stream();
        sseRef.current = source;
      } catch (err) {
        console.error('preview stream error', err);
        setError((err as Error)?.message || 'Preview failed');
        stopPreview();
        setIsLoading(false);
      }
    },
    [handlePayload, setTrackedContentList, stopPreview],
  );

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
          defaultButtonText: params.buttonText || '',
          defaultInputText: params.inputText || '',
          defaultSelectedValues: params.selectedValues,
        };
        newList.length = needChangeItemIndex + 1;
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
                defaultButtonText: params.buttonText || '',
                defaultInputText: params.inputText || '',
                defaultSelectedValues: params.selectedValues,
              }
            : item,
        ),
      );
    },
    [setTrackedContentList],
  );

  const performSend = useCallback(
    (
      content: OnSendContentParams,
      blockBid: string,
      options?: { skipStreamCheck?: boolean },
    ) => {
      if (!options?.skipStreamCheck && isStreamingRef.current) {
        showOutputInProgressToast();
        return false;
      }

      const { variableName, buttonText, inputText } = content;
      if (!variableName) {
        return false;
      }

      let isReGenerate = false;
      const currentList = contentListRef.current;
      if (currentList.length > 0) {
        isReGenerate =
          blockBid !== currentList[currentList.length - 1].generated_block_bid;
      }
      const { newList, needChangeItemIndex } =
      updateContentListWithUserOperate(content, blockBid);

      if (!options?.skipStreamCheck) {
        if (needChangeItemIndex === -1) {
          setTrackedContentList(newList);
        }
      } else {
        prefillInteractionBlock(blockBid, content);
      }

      let values: string[] = [];
      if (content.selectedValues && content.selectedValues.length > 0) {
        values = [...content.selectedValues];
        if (inputText) {
          values.push(inputText);
        }
      } else if (inputText) {
        values = [inputText];
      } else if (buttonText) {
        values = [buttonText];
      }

      if (!values.length) {
        return false;
      }

      const nextValue = values.join(',');
      const nextVariables: PreviewVariablesMap = {
        ...(sseParams.current.variables as PreviewVariablesMap),
        [variableName]: nextValue,
      };
      sseParams.current.variables = nextVariables;
      savePreviewVariables(
        sseParams.current.shifuBid,
        { [variableName]: nextValue },
        sseParams.current.systemVariableKeys || [],
      );

      startPreview({
        ...sseParams.current,
        user_input: {
          [variableName]: values,
        },
        block_index:
          isReGenerate && needChangeItemIndex !== -1
            ? Number(newList[needChangeItemIndex].generated_block_bid)
            : (sseParams.current.block_index || 0) + 1,
      });
      return true;
    },
    [setTrackedContentList, showOutputInProgressToast, startPreview, updateContentListWithUserOperate, prefillInteractionBlock],
  );

  const onRefresh = useCallback(
    async (generatedBlockBid: string) => {
      if (isStreamingRef.current) {
        showOutputInProgressToast();
        return;
      }

      const newList = [...contentListRef.current];
      const needChangeItemIndex = newList.findIndex(
        item => item.generated_block_bid === generatedBlockBid,
      );
      if (needChangeItemIndex === -1) {
        return;
      }

      const parsedBlockIndex = Number.parseInt(generatedBlockBid, 10);
      const nextBlockIndex = Number.isNaN(parsedBlockIndex)
        ? needChangeItemIndex
        : parsedBlockIndex;

      newList.length = needChangeItemIndex;
      setTrackedContentList(newList);
      startPreview({
        ...sseParams.current,
        block_index: nextBlockIndex,
      });
    },
    [setTrackedContentList, startPreview],
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
        performSend(sendParams, blockId, { skipStreamCheck: true });
      }, delay);
    },
    [buildAutoSendParams, parseInteractionBlock, performSend, prefillInteractionBlock],
  );

  useEffect(() => {
    tryAutoSubmitInteractionRef.current = tryAutoSubmitInteraction;
  }, [tryAutoSubmitInteraction]);

  const nullRenderBar = useCallback(() => null, []);

  const items = useMemo(
    () =>
      contentList.map(item => ({
        ...item,
        customRenderBar: item.customRenderBar || nullRenderBar,
      })),
    [contentList, nullRenderBar],
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
  };
}
