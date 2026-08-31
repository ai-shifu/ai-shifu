import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { stripCustomButtonAfterContent } from './chatUiUtils';

export interface ReadModeTypewriterCacheEntry {
  content: string;
  isFinished: boolean;
  isSuppressed?: boolean;
}

export interface ReadModeTypewriterKeepAliveOptions {
  isOutputInProgress: boolean;
  currentStreamingTextElementBid: string;
  currentOutputTextElementBid: string;
}

export type ReadModeTypewriterCache = Record<
  string,
  ReadModeTypewriterCacheEntry
>;

export interface SyncReadModeTypewriterCacheOptions {
  markFinalTextItemsFinished?: boolean;
  suppressTypewriter?: boolean;
}

export const normalizeReadModeTypewriterContent = (content?: string | null) =>
  stripCustomButtonAfterContent(content) || '';

const getItemContent = (item: ChatContentItem) =>
  normalizeReadModeTypewriterContent(item.content);

export const isReadModeTextContentItem = (item: ChatContentItem) =>
  item.type === ChatContentItemType.CONTENT && item.element_type === 'text';

const isReadModeHistoryLikeTextItem = (item: ChatContentItem) =>
  isReadModeTextContentItem(item) &&
  item.shouldRenderAsHistoryInReadMode === true &&
  item.shouldUseTypewriter !== true;

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

  if (cacheEntry.isSuppressed) {
    return false;
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
) => {
  if (isReadModeHistoryLikeTextItem(item)) {
    // A visibility-suppressed element must stay static across temporary
    // history-like projections. Dropping it here would let the same bid replay
    // from the beginning if it becomes realtime again.
    return cacheEntry?.isSuppressed === true;
  }

  return (
    isReadModeTextContentItem(item) &&
    (item.shouldUseTypewriter === true || Boolean(cacheEntry))
  );
};

export const resolveReadModeTypewriterKeepAliveElementBid = ({
  isOutputInProgress,
  currentStreamingTextElementBid,
  currentOutputTextElementBid,
}: ReadModeTypewriterKeepAliveOptions) => {
  if (!isOutputInProgress) {
    return '';
  }

  // Keep the active typewriter session tied to the latest streamed text
  // element, so non-text elements like interactions do not steal the anchor.
  return currentStreamingTextElementBid || currentOutputTextElementBid || '';
};

export const syncReadModeTypewriterCache = (
  items: ChatContentItem[],
  previousCache: ReadModeTypewriterCache,
  options: SyncReadModeTypewriterCacheOptions = {},
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
    const isSuppressed = Boolean(
      previousEntry?.isSuppressed || options.suppressTypewriter,
    );
    const shouldMarkFinished = Boolean(
      isSuppressed || (options.markFinalTextItemsFinished && item.is_final),
    );
    if (previousEntry?.content === content) {
      if (
        (previousEntry.isFinished || !shouldMarkFinished) &&
        (previousEntry.isSuppressed || !isSuppressed)
      ) {
        nextCache[itemBid] = previousEntry;
        return;
      }

      nextCache[itemBid] = {
        ...previousEntry,
        isFinished: previousEntry.isFinished || shouldMarkFinished,
        ...(isSuppressed ? { isSuppressed: true } : {}),
      };
      return;
    }

    nextCache[itemBid] = {
      content,
      isFinished: shouldMarkFinished,
      ...(isSuppressed ? { isSuppressed: true } : {}),
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

  if (isReadModeHistoryLikeTextItem(item)) {
    return true;
  }

  const itemBid = item.element_bid || '';
  const cacheEntry = itemBid ? cache[itemBid] : undefined;
  if (!cacheEntry) {
    return item.shouldUseTypewriter !== true;
  }

  if (cacheEntry.isSuppressed) {
    return true;
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

export const isTrailingVisibleReadModeTextItem = (
  items: ChatContentItem[],
  elementBid: string,
) => {
  if (!elementBid || !items.length) {
    return false;
  }

  const trailingItem = items[items.length - 1];
  return (
    Boolean(trailingItem) &&
    trailingItem.element_bid === elementBid &&
    isReadModeTextContentItem(trailingItem)
  );
};
