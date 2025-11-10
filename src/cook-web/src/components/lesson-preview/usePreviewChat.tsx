'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import { SSE } from 'sse.js';
import { v4 as uuidv4 } from 'uuid';
import { OnSendContentParams } from 'markdown-flow-ui';
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
import {
  PreviewVariablesMap,
  savePreviewVariables,
} from './variableStorage';

interface StartPreviewParams {
  shifuBid?: string;
  outlineBid?: string;
  mdflow?: string;
  user_input?: Record<string, any>;
  variables?: Record<string, any>;
  block_index?: number;
  max_block_count?: number;
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
          setTrackedContentList((prev: ChatContentItem[]) => {
            const interactionBlock: ChatContentItem = {
              generated_block_bid: blockId,
              content: response.data?.mdflow ?? '',
              readonly: false,
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
    }: StartPreviewParams) => {
      const mergedParams = {
        ...sseParams.current,
        shifuBid,
        outlineBid,
        mdflow,
        block_index,
        user_input,
        variables,
        max_block_count,
      };
      const {
        shifuBid: finalShifuBid,
        outlineBid: finalOutlineBid,
        mdflow: finalMdflow,
        block_index: finalBlockIndex = 0,
        user_input: finalUserInput = {},
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
        const source = new SSE(
          `${baseURL}/api/learn/shifu/${finalShifuBid}/preview/${finalOutlineBid}`,
          {
            headers,
            payload: JSON.stringify({
              block_index: finalBlockIndex,
              content: finalMdflow,
              user_input: finalUserInput,
              variables: finalVariables,
            }),
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
      if (isStreamingRef.current) {
        showOutputInProgressToast();
        return;
      }

      const { variableName, buttonText, inputText } = content;
      let isReGenerate = false;
      const currentList = contentListRef.current;
      if (currentList.length > 0) {
        isReGenerate =
          blockBid !== currentList[currentList.length - 1].generated_block_bid;
      }

      const { newList, needChangeItemIndex } = updateContentListWithUserOperate(
        content,
        blockBid,
      );

      if (needChangeItemIndex === -1) {
        setTrackedContentList(newList);
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

      if (variableName && values.length > 0) {
        const nextValue = values[values.length - 1] ?? '';
        const nextVariables: PreviewVariablesMap = {
          ...(sseParams.current.variables as PreviewVariablesMap),
          [variableName]: nextValue,
        };
        sseParams.current.variables = nextVariables;
        savePreviewVariables(
          sseParams.current.shifuBid,
          sseParams.current.outlineBid,
          nextVariables,
        );
      }

      startPreview({
        ...sseParams.current,
        user_input: {
          [variableName as string]: values,
        },
        block_index:
          isReGenerate && needChangeItemIndex !== -1
            ? Number(newList[needChangeItemIndex].generated_block_bid)
            : (sseParams.current.block_index || 0) + 1,
      });
    },
    [startPreview, setTrackedContentList, updateContentListWithUserOperate],
  );

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
