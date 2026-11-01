import type { OnSendContentParams } from 'markdown-flow-ui/renderer';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import { resolveInteractionSubmission } from './interaction-user-input';

/** Rendering helpers do not advance the lesson's interaction position. */
const resolveLastActionableElementBid = (items: ChatContentItem[]) =>
  [...items]
    .reverse()
    .find(
      item =>
        item.element_bid &&
        item.element_bid !== 'loading' &&
        item.type !== ChatContentItemType.LIKE_STATUS &&
        item.type !== ChatContentItemType.ASK,
    )?.element_bid || '';

export const requiresInteractionRewind = (
  items: ChatContentItem[],
  elementBid: string,
) => {
  const last = resolveLastActionableElementBid(items);
  return Boolean(last) && last !== elementBid;
};

/** Both learner and Debug preserve the chosen control and replace its suffix. */
export const updateInteractionItems = (
  items: ChatContentItem[],
  content: OnSendContentParams,
  elementBid: string,
  {
    truncateFollowingItems,
    preserveHelpers = false,
  }: {
    truncateFollowingItems: boolean;
    preserveHelpers?: boolean;
  },
): { items: ChatContentItem[]; index: number } => {
  const next = [...items];
  let index = next.findIndex(item => item.element_bid === elementBid);
  const variableName = content.variableName;
  if (index < 0 && variableName) {
    const matches = next.flatMap((item, i) =>
      item.content?.includes(variableName) ? [i] : [],
    );
    if (matches.length === 1) index = matches[0];
  }
  if (index < 0) return { items: next, index };
  next[index] = {
    ...next[index],
    readonly: false,
    user_input: resolveInteractionSubmission(content).userInput,
  };
  if (truncateFollowingItems) {
    const helpers = preserveHelpers
      ? next
          .slice(index + 1)
          .filter(
            item =>
              (item.parent_element_bid === elementBid ||
                item.parent_block_bid === elementBid) &&
              (item.type === ChatContentItemType.LIKE_STATUS ||
                item.type === ChatContentItemType.ASK),
          )
      : [];
    next.length = index + 1;
    next.push(...helpers);
  }
  return { items: next, index };
};
