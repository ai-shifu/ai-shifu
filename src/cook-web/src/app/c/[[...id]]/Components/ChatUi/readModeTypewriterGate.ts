import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { stripCustomButtonAfterContent } from './chatUiUtils';

export interface ReadModeTypewriterCacheEntry {
  content: string;
  isFinished: boolean;
}

export type ReadModeTypewriterCache = Record<
  string,
  ReadModeTypewriterCacheEntry
>;

const getItemContent = (item: ChatContentItem) =>
  stripCustomButtonAfterContent(item.content) || '';

export const isReadModeTextContentItem = (item: ChatContentItem) =>
  item.type === ChatContentItemType.CONTENT &&
  item.element_type === 'text';

export const shouldTrackReadModeTypewriter = (
  item: ChatContentItem,
  cacheEntry?: ReadModeTypewriterCacheEntry,
) =>
  isReadModeTextContentItem(item) &&
  (!item.isHistory || Boolean(cacheEntry));

export const syncReadModeTypewriterCache = (
  items: ChatContentItem[],
  previousCache: ReadModeTypewriterCache,
): ReadModeTypewriterCache => {
  const nextCache: ReadModeTypewriterCache = {};

  items.forEach(item => {
    const itemBid = item.element_bid || '';
    if (!itemBid) {
      return;
    }

    const previousEntry = previousCache[itemBid];
    if (!shouldTrackReadModeTypewriter(item, previousEntry)) {
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

export const isReadModeTextContentItemReady = (
  item: ChatContentItem,
  cache: ReadModeTypewriterCache,
) => {
  if (!isReadModeTextContentItem(item)) {
    return true;
  }

  const itemBid = item.element_bid || '';
  const cacheEntry = itemBid ? cache[itemBid] : undefined;
  if (!cacheEntry) {
    return item.isHistory === true;
  }

  return (
    Boolean(item.is_final) &&
    cacheEntry.isFinished &&
    cacheEntry.content === getItemContent(item)
  );
};

export const buildVisibleReadModeItems = (
  items: ChatContentItem[],
  cache: ReadModeTypewriterCache,
) => {
  const visibleItems: ChatContentItem[] = [];

  for (const item of items) {
    visibleItems.push(item);
    if (!isReadModeTextContentItemReady(item, cache)) {
      break;
    }
  }

  return visibleItems;
};
