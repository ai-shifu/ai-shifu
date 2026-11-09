import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import { stripCustomButtonAfterContent } from '@/lib/custom-button-after-content';

/** Completion belongs to the conversation finalize/projection pipeline. */
export function getReadingFollowUpAnchors(items: ChatContentItem[]) {
  const finalized = new Set(
    items
      .filter(
        item =>
          item.type === ChatContentItemType.LIKE_STATUS ||
          item.type === ChatContentItemType.ASK,
      )
      .map(item => item.parent_element_bid),
  );
  return new Set(
    items
      .filter(
        item =>
          item.type === ChatContentItemType.CONTENT &&
          Boolean(item.element_bid) &&
          item.element_bid !== 'loading' &&
          !['ask', 'answer', 'interaction'].includes(item.element_type || '') &&
          Boolean(stripCustomButtonAfterContent(item.content)?.trim()) &&
          (item.isHistory || finalized.has(item.element_bid)),
      )
      .map(item => item.element_bid),
  );
}
