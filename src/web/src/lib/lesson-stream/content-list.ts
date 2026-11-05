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

/** How a hook places one element event into its content list. */
export interface ElementPlacementPolicy {
  /**
   * The element whose output the incoming one ends, or '' for none. A function
   * when the choice depends on the list the update applies to.
   */
  completedElementBid: string | ((items: ChatContentItem[]) => string);
  /** Mark the completed element final; each hook keeps its own follow-ups. */
  finalize: (
    items: ChatContentItem[],
    completedElementBid: string,
  ) => ChatContentItem[];
  /** Whether a row already in the list is the incoming element. */
  matches: (item: ChatContentItem) => boolean;
  /** The row that replaces a matched one. */
  merge: (previous: ChatContentItem, next: ChatContentItem) => ChatContentItem;
}

/**
 * Apply one element event to a content list: end the element it follows, then
 * update the incoming element's row in place or append it.
 *
 * The learner and debug streams share these steps but not their rules, which
 * come in through the policy. Pure, so each hook calls it from its own state
 * updater and keeps its own update timing.
 */
export const applyElementToList = (
  items: ChatContentItem[],
  nextItem: ChatContentItem,
  policy: ElementPlacementPolicy,
): ChatContentItem[] => {
  const completedElementBid =
    typeof policy.completedElementBid === 'function'
      ? policy.completedElementBid(items)
      : policy.completedElementBid;
  const list = completedElementBid
    ? policy.finalize(items, completedElementBid)
    : items;

  const hitIndex = list.findIndex(policy.matches);
  if (hitIndex < 0) {
    return [...list, nextItem];
  }
  const nextList = [...list];
  nextList[hitIndex] = policy.merge(nextList[hitIndex], nextItem);
  return nextList;
};
