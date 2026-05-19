import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { stripCustomButtonAfterContent } from '@/c-utils/customButtonAfterContent';

export interface PreviewTypewriterCacheEntry {
  content: string;
  isFinished: boolean;
}

export type PreviewTypewriterCache = Record<
  string,
  PreviewTypewriterCacheEntry
>;

export const normalizePreviewTypewriterContent = (content?: string | null) =>
  stripCustomButtonAfterContent(content) || '';

const getItemContent = (item: ChatContentItem) =>
  normalizePreviewTypewriterContent(item.content);

export const isPreviewTextContentItem = (item: ChatContentItem) =>
  item.type === ChatContentItemType.CONTENT && item.element_type === 'text';

const isPreviewLikeStatusItem = (item: ChatContentItem) =>
  item.type === ChatContentItemType.LIKE_STATUS;

const resolveParentElementBid = (item: ChatContentItem) =>
  item.parent_element_bid || item.parent_block_bid || '';

export const shouldEnablePreviewTypewriter = (
  item: ChatContentItem,
  cacheEntry?: PreviewTypewriterCacheEntry,
) => {
  if (!isPreviewTextContentItem(item) || item.shouldUseTypewriter !== true) {
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

const shouldTrackPreviewTypewriter = (
  item: ChatContentItem,
  cacheEntry?: PreviewTypewriterCacheEntry,
) =>
  isPreviewTextContentItem(item) &&
  (item.shouldUseTypewriter === true || Boolean(cacheEntry));

export const syncPreviewTypewriterCache = (
  items: ChatContentItem[],
  previousCache: PreviewTypewriterCache,
): PreviewTypewriterCache => {
  const nextCache: PreviewTypewriterCache = {};

  items.forEach(item => {
    const itemBid = item.element_bid || '';
    if (!itemBid) {
      return;
    }

    const previousEntry = previousCache[itemBid];
    if (!shouldTrackPreviewTypewriter(item, previousEntry)) {
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

export const isPreviewTextContentItemReady = (
  item: ChatContentItem,
  cache: PreviewTypewriterCache,
) => {
  if (!isPreviewTextContentItem(item)) {
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

export const buildVisiblePreviewItems = (
  items: ChatContentItem[],
  cache: PreviewTypewriterCache,
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
    if (isPreviewLikeStatusItem(item)) {
      const parentElementBid = resolveParentElementBid(item);
      const parentItem = parentElementBid
        ? itemByBid.get(parentElementBid)
        : undefined;

      // Keep helper rows aligned with the finished text block only.
      if (!parentItem || !isPreviewTextContentItem(parentItem)) {
        continue;
      }

      if (!isPreviewTextContentItemReady(parentItem, cache)) {
        break;
      }

      visibleItems.push(item);
      continue;
    }

    visibleItems.push(item);
    if (!isPreviewTextContentItemReady(item, cache)) {
      break;
    }
  }

  return visibleItems;
};
