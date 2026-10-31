import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import { stripCustomButtonAfterContent } from '@/lib/custom-button-after-content';

export interface DebugTypewriterCacheEntry {
  content: string;
  isFinished: boolean;
}

export type DebugTypewriterCache = Record<string, DebugTypewriterCacheEntry>;

export const normalizeDebugTypewriterContent = (content?: string | null) =>
  stripCustomButtonAfterContent(content) || '';

const getItemContent = (item: ChatContentItem) =>
  normalizeDebugTypewriterContent(item.content);

export const isDebugTextContentItem = (item: ChatContentItem) =>
  item.type === ChatContentItemType.CONTENT && item.element_type === 'text';

const isDebugLikeStatusItem = (item: ChatContentItem) =>
  item.type === ChatContentItemType.LIKE_STATUS;

const resolveParentElementBid = (item: ChatContentItem) =>
  item.parent_element_bid || item.parent_block_bid || '';

export const shouldEnableDebugTypewriter = (
  item: ChatContentItem,
  cacheEntry?: DebugTypewriterCacheEntry,
) => {
  if (!isDebugTextContentItem(item) || item.shouldUseTypewriter !== true) {
    return false;
  }

  if (!cacheEntry) {
    return true;
  }

  const currentContent = getItemContent(item);
  const hasAppendedContentBeyondCache =
    currentContent.length > cacheEntry.content.length &&
    currentContent.startsWith(cacheEntry.content);

  if (!item.is_final) {
    return true;
  }

  return !cacheEntry.isFinished || hasAppendedContentBeyondCache;
};

const shouldTrackDebugTypewriter = (
  item: ChatContentItem,
  cacheEntry?: DebugTypewriterCacheEntry,
) =>
  isDebugTextContentItem(item) &&
  (item.shouldUseTypewriter === true || Boolean(cacheEntry));

export const syncDebugTypewriterCache = (
  items: ChatContentItem[],
  previousCache: DebugTypewriterCache,
): DebugTypewriterCache => {
  const nextCache: DebugTypewriterCache = {};

  items.forEach(item => {
    const itemBid = item.element_bid || '';
    if (!itemBid) {
      return;
    }

    const previousEntry = previousCache[itemBid];
    if (!shouldTrackDebugTypewriter(item, previousEntry)) {
      return;
    }

    const content = getItemContent(item);
    if (previousEntry?.content === content) {
      nextCache[itemBid] = previousEntry;
      return;
    }

    nextCache[itemBid] = {
      content,
      isFinished: false,
    };
  });

  return nextCache;
};

export const isDebugTextContentItemReady = (
  item: ChatContentItem,
  cache: DebugTypewriterCache,
) => {
  if (!isDebugTextContentItem(item)) {
    return true;
  }

  const itemBid = item.element_bid || '';
  const cacheEntry = itemBid ? cache[itemBid] : undefined;
  if (!cacheEntry) {
    return item.shouldUseTypewriter !== true;
  }

  return (
    Boolean(item.is_final) &&
    cacheEntry.isFinished &&
    cacheEntry.content === getItemContent(item)
  );
};

export const buildVisibleDebugItems = (
  items: ChatContentItem[],
  cache: DebugTypewriterCache,
) => {
  const visibleItems: ChatContentItem[] = [];
  const itemByBid = new Map<string, ChatContentItem>();

  items.forEach(item => {
    const itemBid = item.element_bid || item.generated_block_bid || '';
    if (itemBid) {
      itemByBid.set(itemBid, item);
    }
  });

  for (const item of items) {
    if (isDebugLikeStatusItem(item)) {
      const parentElementBid = resolveParentElementBid(item);
      const parentItem = parentElementBid
        ? itemByBid.get(parentElementBid)
        : undefined;

      // Keep helper rows aligned with the finished text block only.
      if (!parentItem || !isDebugTextContentItem(parentItem)) {
        continue;
      }

      if (!isDebugTextContentItemReady(parentItem, cache)) {
        break;
      }

      visibleItems.push(item);
      continue;
    }

    visibleItems.push(item);
    if (!isDebugTextContentItemReady(item, cache)) {
      break;
    }
  }

  return visibleItems;
};
