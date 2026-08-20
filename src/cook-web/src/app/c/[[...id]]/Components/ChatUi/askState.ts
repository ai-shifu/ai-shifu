import { BLOCK_TYPE } from '@/c-api/studyV2';
import type { AudioTrack } from '@/c-utils/audio-utils';

export interface AskMessage {
  type: typeof BLOCK_TYPE.ASK | typeof BLOCK_TYPE.ANSWER;
  content: string;
  isStreaming?: boolean;
  element_bid?: string;
  generated_block_bid?: string;
  shouldUseTypewriter?: boolean;
  audioUrl?: string;
  audioTracks?: AudioTrack[];
  audioDurationMs?: number;
  isAudioStreaming?: boolean;
  isAudioBackfillReady?: boolean;
  listenAudioBackfillMode?: 'listen' | 'block';
}

interface AskAnchorLike {
  parent_element_bid?: string;
  anchor_element_bid?: string;
  ask_list?: unknown[];
}

export const EMPTY_ASK_MESSAGE_LIST: AskMessage[] = [];

export const normalizeAskMessageList = (askList: AskMessage[] = []) =>
  askList.map(item => ({
    ...item,
    content: item.content || '',
    shouldUseTypewriter: item.shouldUseTypewriter ?? false,
  }));

export const areAskMessageListsEqual = (
  previousList: AskMessage[] = [],
  nextList: AskMessage[] = [],
) => {
  if (previousList === nextList) {
    return true;
  }

  if (previousList.length !== nextList.length) {
    return false;
  }

  return previousList.every((item, index) => {
    const nextItem = nextList[index];

    return (
      item.type === nextItem?.type &&
      item.content === nextItem?.content &&
      item.element_bid === nextItem?.element_bid &&
      item.generated_block_bid === nextItem?.generated_block_bid &&
      item.isStreaming === nextItem?.isStreaming &&
      item.shouldUseTypewriter === nextItem?.shouldUseTypewriter &&
      item.audioUrl === nextItem?.audioUrl &&
      item.audioTracks === nextItem?.audioTracks &&
      item.audioDurationMs === nextItem?.audioDurationMs &&
      item.isAudioStreaming === nextItem?.isAudioStreaming &&
      item.isAudioBackfillReady === nextItem?.isAudioBackfillReady &&
      item.listenAudioBackfillMode === nextItem?.listenAudioBackfillMode
    );
  });
};

export const hasStreamingAskMessage = (askList: AskMessage[] = []) =>
  askList.some(item => Boolean(item.isStreaming));

export const resolveAskAnchorElementBid = (item: AskAnchorLike) => {
  const directAnchorElementBid =
    typeof item.anchor_element_bid === 'string' ? item.anchor_element_bid : '';

  if (directAnchorElementBid) {
    return directAnchorElementBid;
  }

  if (Array.isArray(item.ask_list)) {
    const matchedAskMessage = item.ask_list.find(askMessage => {
      const anchorElementBid = (
        askMessage as Record<string, unknown> & {
          anchor_element_bid?: string;
        }
      ).anchor_element_bid;

      return typeof anchorElementBid === 'string' && Boolean(anchorElementBid);
    });

    if (matchedAskMessage) {
      return (
        (
          matchedAskMessage as Record<string, unknown> & {
            anchor_element_bid?: string;
          }
        ).anchor_element_bid || ''
      );
    }
  }

  return item.parent_element_bid || '';
};

export const buildAskListByAnchorElementBid = <T extends AskAnchorLike>(
  items: T[] = [],
) => {
  const askMapping = new Map<string, AskMessage[]>();

  items.forEach(item => {
    const askList = Array.isArray(item.ask_list)
      ? normalizeAskMessageList(item.ask_list as unknown as AskMessage[])
      : EMPTY_ASK_MESSAGE_LIST;

    if (!askList.length) {
      return;
    }

    const anchorElementBid = resolveAskAnchorElementBid(item);

    if (!anchorElementBid) {
      return;
    }

    askMapping.set(anchorElementBid, askList);
  });

  return askMapping;
};
