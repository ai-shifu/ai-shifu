import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import type { AskMessage } from './askState';

const normalizeReadModeDisplayItem = (item: ChatContentItem) => {
  if (item.shouldRenderAsHistoryInReadMode !== true) {
    return item;
  }

  return {
    ...item,
    isHistory: true,
    shouldUseTypewriter: false,
  } satisfies ChatContentItem;
};

export const buildReadModeItemsWithAskState = ({
  items,
  askListByAnchorElementBid,
  mobileStyle,
}: {
  items: ChatContentItem[];
  askListByAnchorElementBid: Record<string, AskMessage[]>;
  mobileStyle: boolean;
}) => {
  const existingAskAnchorSet = new Set<string>();
  const likeStatusAnchorSet = new Set<string>();

  items.forEach(item => {
    const normalizedItem = normalizeReadModeDisplayItem(item);

    if (
      normalizedItem.type === ChatContentItemType.ASK &&
      normalizedItem.parent_element_bid
    ) {
      existingAskAnchorSet.add(normalizedItem.parent_element_bid);
    }

    if (
      normalizedItem.type === ChatContentItemType.LIKE_STATUS &&
      normalizedItem.parent_element_bid
    ) {
      likeStatusAnchorSet.add(normalizedItem.parent_element_bid);
    }
  });

  const insertedAskAnchorSet = new Set<string>();
  const nextItems: ChatContentItem[] = [];

  items.forEach(item => {
    const normalizedItem = normalizeReadModeDisplayItem(item);

    if (normalizedItem.type === ChatContentItemType.ASK) {
      const anchorElementBid = normalizedItem.parent_element_bid || '';
      const storedAskList = anchorElementBid
        ? askListByAnchorElementBid[anchorElementBid]
        : undefined;

      nextItems.push(
        storedAskList
          ? ({
              ...normalizedItem,
              ask_list: storedAskList as ChatContentItem[],
            } satisfies ChatContentItem)
          : normalizedItem,
      );

      if (anchorElementBid) {
        insertedAskAnchorSet.add(anchorElementBid);
      }

      return;
    }

    nextItems.push(normalizedItem);

    const anchorElementBid =
      normalizedItem.type === ChatContentItemType.LIKE_STATUS
        ? normalizedItem.parent_element_bid || ''
        : normalizedItem.element_bid || '';

    if (
      !anchorElementBid ||
      existingAskAnchorSet.has(anchorElementBid) ||
      insertedAskAnchorSet.has(anchorElementBid)
    ) {
      return;
    }

    const storedAskList = askListByAnchorElementBid[anchorElementBid];

    if (!storedAskList?.length) {
      return;
    }

    const shouldInsertAfterCurrent =
      normalizedItem.type === ChatContentItemType.LIKE_STATUS ||
      (!likeStatusAnchorSet.has(anchorElementBid) &&
        (normalizedItem.type === ChatContentItemType.CONTENT ||
          normalizedItem.type === ChatContentItemType.INTERACTION));

    if (!shouldInsertAfterCurrent) {
      return;
    }

    nextItems.push({
      element_bid: '',
      parent_element_bid: anchorElementBid,
      type: ChatContentItemType.ASK,
      content: '',
      isAskExpanded: !mobileStyle,
      ask_list: storedAskList as ChatContentItem[],
      readonly: false,
      customRenderBar: () => null,
      user_input: '',
    });
    insertedAskAnchorSet.add(anchorElementBid);
  });

  return nextItems;
};
