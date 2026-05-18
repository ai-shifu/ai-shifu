import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { syncCustomButtonAfterContent } from './chatUiUtils';
import { normalizeReadModeDisplayItem } from './readModeItems';

type ProjectAskMessage = Partial<ChatContentItem> & {
  element_bid?: string;
};

interface ProjectReadModeItemsParams {
  items: ChatContentItem[];
  askListByAnchorElementBid: Record<string, ProjectAskMessage[]>;
  mobileStyle: boolean;
  askButtonMarkup: string;
}

interface ProjectListenModeItemsParams {
  items: ChatContentItem[];
  askButtonMarkup: string;
}

const projectContentButton = ({
  item,
  mobileStyle,
  shouldShowButton,
  askButtonMarkup,
}: {
  item: ChatContentItem;
  mobileStyle: boolean;
  shouldShowButton: boolean;
  askButtonMarkup: string;
}): ChatContentItem => {
  if (item.type !== ChatContentItemType.CONTENT) {
    return item;
  }

  const projectedContent = syncCustomButtonAfterContent({
    content: item.content,
    buttonMarkup: askButtonMarkup,
    shouldShowButton: mobileStyle && shouldShowButton,
  });

  if (projectedContent === (item.content ?? '')) {
    return item;
  }

  return {
    ...item,
    content: projectedContent,
  };
};

const shouldProjectCanonicalItem = (item: ChatContentItem) => {
  if (item.type !== ChatContentItemType.CONTENT) {
    return true;
  }
  if (item.is_renderable !== false) {
    return true;
  }
  return Boolean(item.content?.trim());
};

const getHiddenContentElementBids = (items: ChatContentItem[]) => {
  const hiddenElementBids = new Set<string>();

  items.forEach(item => {
    if (
      item.type === ChatContentItemType.CONTENT &&
      item.element_bid &&
      !shouldProjectCanonicalItem(item)
    ) {
      hiddenElementBids.add(item.element_bid);
    }
  });

  return hiddenElementBids;
};

const shouldProjectModeItem = (
  item: ChatContentItem,
  hiddenContentElementBids: Set<string>,
) => {
  if (
    (item.type === ChatContentItemType.ASK ||
      item.type === ChatContentItemType.LIKE_STATUS) &&
    item.parent_element_bid &&
    hiddenContentElementBids.has(item.parent_element_bid)
  ) {
    return false;
  }

  return shouldProjectCanonicalItem(item);
};

export const projectReadModeItems = ({
  items,
  askListByAnchorElementBid,
  mobileStyle,
  askButtonMarkup,
}: ProjectReadModeItemsParams) => {
  const hiddenContentElementBids = getHiddenContentElementBids(items);
  const projectableItems = items
    .filter(item => shouldProjectModeItem(item, hiddenContentElementBids))
    .map(normalizeReadModeDisplayItem);
  const existingAskAnchorSet = new Set<string>();
  const likeStatusAnchorSet = new Set<string>();
  const finalizedParentElementBids = new Set<string>();

  projectableItems.forEach(item => {
    if (item.type === ChatContentItemType.ASK && item.parent_element_bid) {
      existingAskAnchorSet.add(item.parent_element_bid);
      finalizedParentElementBids.add(item.parent_element_bid);
    }

    if (
      item.type === ChatContentItemType.LIKE_STATUS &&
      item.parent_element_bid
    ) {
      likeStatusAnchorSet.add(item.parent_element_bid);
      finalizedParentElementBids.add(item.parent_element_bid);
    }
  });

  const insertedAskAnchorSet = new Set<string>();
  const nextItems: ChatContentItem[] = [];

  projectableItems.forEach(item => {
    if (item.type === ChatContentItemType.ASK) {
      const anchorElementBid = item.parent_element_bid || '';
      const storedAskList = anchorElementBid
        ? askListByAnchorElementBid[anchorElementBid]
        : undefined;

      nextItems.push(
        storedAskList
          ? {
              ...item,
              ask_list: storedAskList as ChatContentItem[],
            }
          : item,
      );

      if (anchorElementBid) {
        insertedAskAnchorSet.add(anchorElementBid);
      }

      return;
    }

    const projectedItem = projectContentButton({
      item,
      mobileStyle,
      askButtonMarkup,
      shouldShowButton:
        Boolean(item.isHistory) ||
        finalizedParentElementBids.has(item.element_bid),
    });

    nextItems.push(projectedItem);

    const anchorElementBid =
      item.type === ChatContentItemType.LIKE_STATUS
        ? item.parent_element_bid || ''
        : item.element_bid || '';

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
      item.type === ChatContentItemType.LIKE_STATUS ||
      (!likeStatusAnchorSet.has(anchorElementBid) &&
        (item.type === ChatContentItemType.CONTENT ||
          item.type === ChatContentItemType.INTERACTION));

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

export const projectListenModeItems = ({
  items,
  askButtonMarkup,
}: ProjectListenModeItemsParams) => {
  const hiddenContentElementBids = getHiddenContentElementBids(items);
  const projectableItems = items.filter(item =>
    shouldProjectModeItem(item, hiddenContentElementBids),
  );
  let hasChanges = projectableItems.length !== items.length;
  const nextItems = projectableItems.map(item => {
    if (item.type !== ChatContentItemType.CONTENT) {
      return item;
    }
    const sanitizedContent = syncCustomButtonAfterContent({
      content: item.content,
      buttonMarkup: askButtonMarkup,
      shouldShowButton: false,
    });
    if (sanitizedContent === (item.content ?? '')) {
      return item;
    }
    hasChanges = true;
    return {
      ...item,
      content: sanitizedContent,
    };
  });

  return hasChanges ? nextItems : items;
};
