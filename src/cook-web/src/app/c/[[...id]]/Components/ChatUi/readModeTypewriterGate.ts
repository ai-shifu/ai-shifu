import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { stripCustomButtonAfterContent } from './chatUiUtils';

export interface ReadModeTypewriterCacheEntry {
  content: string;
  isFinished: boolean;
}

export interface ReadModeTypewriterKeepAliveOptions {
  previousKeepAliveElementBid: string;
  previousOutputInProgress: boolean;
  isOutputInProgress: boolean;
  currentStreamingElementBid: string;
}

export type ReadModeTypewriterCache = Record<
  string,
  ReadModeTypewriterCacheEntry
>;

export const normalizeReadModeTypewriterContent = (content?: string | null) =>
  stripCustomButtonAfterContent(content) || '';

const getItemContent = (item: ChatContentItem) =>
  normalizeReadModeTypewriterContent(item.content);

export const isReadModeTextContentItem = (item: ChatContentItem) =>
  item.type === ChatContentItemType.CONTENT && item.element_type === 'text';

export const shouldEnableReadModeTypewriter = (
  item: ChatContentItem,
  cacheEntry?: ReadModeTypewriterCacheEntry,
  options?: {
    keepAliveWhileStreaming?: boolean;
  },
) => {
  if (!isReadModeTextContentItem(item) || item.shouldUseTypewriter !== true) {
    return false;
  }

  if (!cacheEntry) {
    return true;
  }

  const currentContent = getItemContent(item);
  const hasAppendedContentBeyondCache =
    currentContent.length > cacheEntry.content.length &&
    currentContent.startsWith(cacheEntry.content);

  // Keep typewriter session alive for non-final streamed text so later
  // appended chunks can continue from the current display state.
  if (!item.is_final || options?.keepAliveWhileStreaming) {
    return true;
  }

  return !cacheEntry.isFinished || hasAppendedContentBeyondCache;
};

export const shouldTrackReadModeTypewriter = (
  item: ChatContentItem,
  cacheEntry?: ReadModeTypewriterCacheEntry,
) =>
  isReadModeTextContentItem(item) &&
  (item.shouldUseTypewriter === true || Boolean(cacheEntry));

export const resolveReadModeTypewriterKeepAliveElementBid = ({
  previousKeepAliveElementBid,
  previousOutputInProgress,
  isOutputInProgress,
  currentStreamingElementBid,
}: ReadModeTypewriterKeepAliveOptions) => {
  if (!isOutputInProgress) {
    return '';
  }

  if (!previousOutputInProgress) {
    return currentStreamingElementBid || '';
  }

  return currentStreamingElementBid || previousKeepAliveElementBid;
};

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
    return item.shouldUseTypewriter !== true;
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
