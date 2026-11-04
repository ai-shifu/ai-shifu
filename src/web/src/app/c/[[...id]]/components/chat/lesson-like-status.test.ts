// The constants live in the API module, whose import chain needs the app
// runtime; provide them directly, as the hook tests do.
jest.mock('@/api/learning', () => ({
  LIKE_STATUS: { LIKE: 'like', DISLIKE: 'dislike', NONE: 'none' },
  LESSON_FEEDBACK_INTERACTION_MARKER: '%{{sys_lesson_feedback_score}}',
}));

import {
  LESSON_FEEDBACK_INTERACTION_MARKER,
  LIKE_STATUS,
} from '@/api/learning';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import {
  finalizeLikeStatusByParent,
  removeLikeStatusByParent,
  upsertLikeStatusByParent,
} from './lesson-like-status';

const content = (
  element_bid: string,
  fields: Partial<ChatContentItem> = {},
): ChatContentItem => ({
  element_bid,
  content: 'Teaching',
  element_type: 'text',
  type: ChatContentItemType.CONTENT,
  ...fields,
});

const likeRows = (items: ChatContentItem[]) =>
  items
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => item.type === ChatContentItemType.LIKE_STATUS)
    .map(({ item, index }) => ({
      index,
      parent: item.parent_element_bid,
      status: item.like_status,
    }));

describe('lesson like-status rows', () => {
  it('inserts one row right after its element and updates it in place', () => {
    const items = [content('a'), content('b')];
    const inserted = upsertLikeStatusByParent(items, { parentElementBid: 'a' });
    expect(likeRows(inserted)).toEqual([
      { index: 1, parent: 'a', status: LIKE_STATUS.NONE },
    ]);

    const liked = upsertLikeStatusByParent(inserted, {
      parentElementBid: 'a',
      likeStatus: LIKE_STATUS.LIKE,
    });
    expect(likeRows(liked)).toEqual([
      { index: 1, parent: 'a', status: LIKE_STATUS.LIKE },
    ]);
    expect(
      upsertLikeStatusByParent(liked, {
        parentElementBid: 'a',
        likeStatus: LIKE_STATUS.LIKE,
      }),
    ).toBe(liked);
  });

  it('appends the row when its anchor is missing and ignores an empty parent', () => {
    const items = [content('a')];
    expect(
      likeRows(upsertLikeStatusByParent(items, { parentElementBid: 'x' })),
    ).toEqual([{ index: 1, parent: 'x', status: LIKE_STATUS.NONE }]);
    expect(upsertLikeStatusByParent(items, { parentElementBid: '' })).toBe(
      items,
    );
  });

  it('removes only the row of the given parent', () => {
    const items = upsertLikeStatusByParent(
      upsertLikeStatusByParent([content('a'), content('b')], {
        parentElementBid: 'a',
      }),
      { parentElementBid: 'b' },
    );
    // [a, like(a), b, like(b)] -> [a, b, like(b)]
    expect(likeRows(removeLikeStatusByParent(items, 'a'))).toEqual([
      { index: 2, parent: 'b', status: LIKE_STATUS.NONE },
    ]);
    expect(removeLikeStatusByParent(items, 'missing')).toBe(items);
  });

  it('attaches a row to a finished element but not to lesson feedback', () => {
    const finished = finalizeLikeStatusByParent(
      [content('a', { like_status: LIKE_STATUS.DISLIKE })],
      'a',
    );
    expect(likeRows(finished)).toEqual([
      { index: 1, parent: 'a', status: LIKE_STATUS.DISLIKE },
    ]);

    const feedback = content('fb', {
      element_type: 'interaction',
      content: `?[${LESSON_FEEDBACK_INTERACTION_MARKER} 1|2]`,
    });
    const withStaleRow = upsertLikeStatusByParent([feedback], {
      parentElementBid: 'fb',
    });
    expect(likeRows(finalizeLikeStatusByParent(withStaleRow, 'fb'))).toEqual(
      [],
    );
  });
});
