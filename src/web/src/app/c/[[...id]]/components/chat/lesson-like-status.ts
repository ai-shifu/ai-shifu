import {
  LESSON_FEEDBACK_INTERACTION_MARKER,
  LIKE_STATUS,
  type ElementType,
  type LikeStatus,
} from '@/api/learning';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';

/**
 * Like-status rows of the learner lesson list: one per rated element, placed
 * right after it. Pure list helpers, shared by the run hook and its tests.
 */

export const isLessonFeedbackContent = (content?: string | null) =>
  Boolean(content?.includes(LESSON_FEEDBACK_INTERACTION_MARKER));

export const createLikeStatusItem = (
  parentElementBid: string,
  likeStatus: LikeStatus = LIKE_STATUS.NONE,
): ChatContentItem => ({
  parent_element_bid: parentElementBid,
  element_bid: '',
  content: '',
  like_status: likeStatus,
  type: ChatContentItemType.LIKE_STATUS,
});

export const shouldAttachLikeStatusByElement = ({
  elementBid,
  elementType,
  content,
}: {
  elementBid?: string | null;
  elementType?: ElementType | null;
  content?: string | null;
}) => {
  if (!elementBid) {
    return false;
  }

  if (!elementType) {
    return false;
  }

  return !isLessonFeedbackContent(content);
};

export const upsertLikeStatusByParent = (
  items: ChatContentItem[],
  params: {
    parentElementBid: string;
    likeStatus?: LikeStatus | null;
    insertAfterElementBid?: string;
  },
) => {
  const { parentElementBid, insertAfterElementBid } = params;
  if (!parentElementBid) {
    return items;
  }

  const resolvedLikeStatus = params.likeStatus ?? LIKE_STATUS.NONE;
  const hitIndex = items.findIndex(
    item =>
      item.type === ChatContentItemType.LIKE_STATUS &&
      item.parent_element_bid === parentElementBid,
  );

  if (hitIndex >= 0) {
    if (items[hitIndex].like_status === resolvedLikeStatus) {
      return items;
    }
    const nextItems = [...items];
    nextItems[hitIndex] = {
      ...nextItems[hitIndex],
      like_status: resolvedLikeStatus,
    };
    return nextItems;
  }

  const nextItems = [...items];
  const anchorElementBid = insertAfterElementBid || parentElementBid;
  const anchorIndex = nextItems.findIndex(
    item => item.element_bid === anchorElementBid,
  );
  const nextLikeStatusItem = createLikeStatusItem(
    parentElementBid,
    resolvedLikeStatus,
  );

  if (anchorIndex >= 0) {
    nextItems.splice(anchorIndex + 1, 0, nextLikeStatusItem);
    return nextItems;
  }

  nextItems.push(nextLikeStatusItem);
  return nextItems;
};

export const removeLikeStatusByParent = (
  items: ChatContentItem[],
  parentElementBid: string,
) => {
  if (!parentElementBid) {
    return items;
  }

  const hitIndex = items.findIndex(
    item =>
      item.type === ChatContentItemType.LIKE_STATUS &&
      item.parent_element_bid === parentElementBid,
  );

  if (hitIndex < 0) {
    return items;
  }

  const nextItems = [...items];
  nextItems.splice(hitIndex, 1);
  return nextItems;
};

export const finalizeLikeStatusByParent = (
  items: ChatContentItem[],
  parentElementBid: string,
) => {
  if (!parentElementBid) {
    return items;
  }

  const targetItem = items.find(item => item.element_bid === parentElementBid);
  if (!targetItem) {
    return items;
  }

  const elementType =
    typeof targetItem.element_type === 'string'
      ? targetItem.element_type
      : undefined;
  const shouldAttachLikeStatus = shouldAttachLikeStatusByElement({
    elementBid: parentElementBid,
    elementType,
    content: targetItem.content,
  });

  if (!shouldAttachLikeStatus) {
    return removeLikeStatusByParent(items, parentElementBid);
  }

  return upsertLikeStatusByParent(items, {
    parentElementBid,
    likeStatus: targetItem.like_status,
    insertAfterElementBid: parentElementBid,
  });
};
