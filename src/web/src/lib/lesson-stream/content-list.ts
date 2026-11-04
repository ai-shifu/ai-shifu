import type { ChatContentItem } from '@/types/chat-ui';

/**
 * Shared list operations for the learner run and editor debug streams.
 *
 * Both hooks render the same element events into a ChatContentItem list; the
 * helpers here are the parts that behave identically in both.
 */

/** Bid of the placeholder row shown while a run waits for its first element. */
export const LOADING_ITEM_BID = 'loading';

/**
 * The learner placeholder sets only element_bid; the debug placeholder sets
 * both bids. Real bids are never 'loading', so either field identifies it.
 */
export const isLoadingItem = (item: ChatContentItem): boolean =>
  item.element_bid === LOADING_ITEM_BID ||
  item.generated_block_bid === LOADING_ITEM_BID;

export const withoutLoadingItem = (
  items: ChatContentItem[],
): ChatContentItem[] => items.filter(item => !isLoadingItem(item));

/** Whether the item is the element with this bid; an empty bid matches nothing. */
export const matchesElementBid = (
  item: ChatContentItem,
  bid: string,
): boolean => Boolean(bid) && item.element_bid === bid;
