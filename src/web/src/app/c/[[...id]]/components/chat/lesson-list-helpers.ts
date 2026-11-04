import {
  BLOCK_TYPE,
  type ListenSlideData,
  type StudyRecordItem,
} from '@/api/learning';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';

/**
 * Pure list helpers of the learner lesson conversation: follow-up (ask)
 * blocks under their anchor element, listen-mode slide merging, and the
 * identity bids an element record is cached under.
 */

export const upsertAskMessageByParent = (
  items: ChatContentItem[],
  params: {
    parentElementBid: string;
    messageType: typeof BLOCK_TYPE.ASK | typeof BLOCK_TYPE.ANSWER;
    messageElementBid?: string;
    messageGeneratedBlockBid?: string;
    messageContent: string;
    messagePayload?: StudyRecordItem['payload'];
    isHistory?: boolean;
    insertionMode?: 'anchor' | 'sequence';
    /** Whether a newly created ask block starts expanded (desktop only). */
    autoExpandAskBlock: boolean;
  },
) => {
  const { parentElementBid, messageType, messageContent } = params;
  if (!parentElementBid) {
    return items;
  }
  const shouldAutoExpandAskBlock = params.autoExpandAskBlock;

  const resolvedMessageElementBid =
    params.messageElementBid ||
    params.messageGeneratedBlockBid ||
    `${messageType}-${parentElementBid}`;
  const nextMessage: ChatContentItem = {
    element_bid: resolvedMessageElementBid,
    generated_block_bid:
      params.messageGeneratedBlockBid || resolvedMessageElementBid,
    parent_element_bid: parentElementBid,
    type: messageType,
    content: messageContent,
    payload: params.messagePayload,
    ...(params.messagePayload?.interaction_mode === 'live_voice'
      ? { interaction_mode: 'live_voice' as const }
      : {}),
    readonly: true,
    customRenderBar: () => null,
    user_input: '',
    isHistory: params.isHistory,
  };

  const nextItems = [...items];
  const askBlockIndex = nextItems.findIndex(
    item =>
      item.type === ChatContentItemType.ASK &&
      item.parent_element_bid === parentElementBid,
  );

  if (askBlockIndex >= 0) {
    const existingAskBlock = nextItems[askBlockIndex];
    const existingAskList = Array.isArray(existingAskBlock.ask_list)
      ? [...existingAskBlock.ask_list]
      : [];
    const existingMessageIndex = existingAskList.findIndex(
      message => message.element_bid === resolvedMessageElementBid,
    );
    if (existingMessageIndex >= 0) {
      existingAskList[existingMessageIndex] = {
        ...existingAskList[existingMessageIndex],
        ...nextMessage,
      };
    } else {
      existingAskList.push(nextMessage);
    }
    nextItems[askBlockIndex] = {
      ...existingAskBlock,
      ask_list: existingAskList,
      isAskExpanded: existingAskBlock.isAskExpanded ?? shouldAutoExpandAskBlock,
    };
    return nextItems;
  }

  const nextAskBlock: ChatContentItem = {
    element_bid: '',
    parent_element_bid: parentElementBid,
    type: ChatContentItemType.ASK,
    content: '',
    isAskExpanded: shouldAutoExpandAskBlock,
    ask_list: [nextMessage],
    readonly: false,
    customRenderBar: () => null,
    user_input: '',
  };
  if (params.insertionMode === 'sequence') {
    nextItems.push(nextAskBlock);
    return nextItems;
  }
  const likeStatusIndex = nextItems.findIndex(
    item =>
      item.parent_element_bid === parentElementBid &&
      item.type === ChatContentItemType.LIKE_STATUS,
  );
  const parentContentIndex =
    likeStatusIndex >= 0
      ? likeStatusIndex
      : nextItems.findIndex(item => item.element_bid === parentElementBid);

  if (parentContentIndex < 0) {
    nextItems.push(nextAskBlock);
    return nextItems;
  }

  nextItems.splice(parentContentIndex + 1, 0, nextAskBlock);
  return nextItems;
};

export const sortSlidesByTimeline = (slides: ListenSlideData[] = []) => {
  return [...slides].sort(
    (a, b) =>
      Number(a.slide_index ?? 0) - Number(b.slide_index ?? 0) ||
      Number(a.audio_position ?? 0) - Number(b.audio_position ?? 0),
  );
};

export const mergeListenSlides = (
  ...slideLists: Array<ListenSlideData[] | undefined>
) => {
  const slideById = new Map<string, ListenSlideData>();
  slideLists.flat().forEach(slide => {
    if (!slide?.slide_id) {
      return;
    }
    slideById.set(slide.slide_id, {
      ...(slideById.get(slide.slide_id) ?? {}),
      ...slide,
    });
  });
  return sortSlidesByTimeline([...slideById.values()]);
};

export const resolveElementCacheIdentityBids = (
  record: StudyRecordItem,
  itemBid: string,
) => {
  const primaryBid =
    record.is_new === false && record.target_element_bid
      ? record.target_element_bid
      : itemBid;
  return primaryBid ? [primaryBid] : [];
};

export const itemMatchesElementCacheIdentity = (
  item: ChatContentItem,
  identityBids: Set<string>,
) =>
  Boolean(
    identityBids.has(item.element_bid) ||
    (item.target_element_bid && identityBids.has(item.target_element_bid)),
  );
