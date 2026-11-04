// The constants live in the API module, whose import chain needs the app
// runtime; provide them directly, as the hook tests do.
jest.mock('@/api/learning', () => ({
  BLOCK_TYPE: { ASK: 'ask', ANSWER: 'answer' },
}));

import type { ListenSlideData, StudyRecordItem } from '@/api/learning';
import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import {
  itemMatchesElementCacheIdentity,
  mergeListenSlides,
  resolveElementCacheIdentityBids,
  upsertAskMessageByParent,
} from './lesson-list-helpers';

const content = (element_bid: string): ChatContentItem => ({
  element_bid,
  content: 'Teaching',
  type: ChatContentItemType.CONTENT,
});

const likeRow = (parent: string): ChatContentItem => ({
  element_bid: '',
  parent_element_bid: parent,
  content: '',
  type: ChatContentItemType.LIKE_STATUS,
});

describe('learner ask blocks', () => {
  const ask = {
    parentElementBid: 'a',
    messageType: 'ask' as const,
    messageElementBid: 'q1',
    messageContent: 'Why?',
  };

  it('opens an ask block after the like-status row of its anchor', () => {
    const items = upsertAskMessageByParent(
      [content('a'), likeRow('a'), content('b')],
      { ...ask, autoExpandAskBlock: true },
    );
    expect(items.map(item => item.type)).toEqual([
      ChatContentItemType.CONTENT,
      ChatContentItemType.LIKE_STATUS,
      ChatContentItemType.ASK,
      ChatContentItemType.CONTENT,
    ]);
    expect(items[2]).toMatchObject({
      parent_element_bid: 'a',
      isAskExpanded: true,
      ask_list: [{ element_bid: 'q1', content: 'Why?' }],
    });
  });

  it('starts collapsed when auto-expand is off and updates messages in place', () => {
    const opened = upsertAskMessageByParent([content('a')], {
      ...ask,
      autoExpandAskBlock: false,
    });
    expect(opened[1].isAskExpanded).toBe(false);

    const answered = upsertAskMessageByParent(opened, {
      ...ask,
      messageType: 'answer',
      messageElementBid: 'r1',
      messageContent: 'Because.',
      autoExpandAskBlock: true,
    });
    const updated = upsertAskMessageByParent(answered, {
      ...ask,
      messageContent: 'Why exactly?',
      autoExpandAskBlock: true,
    });
    expect(updated).toHaveLength(2);
    expect(updated[1].isAskExpanded).toBe(false);
    expect(updated[1].ask_list?.map(message => message.content)).toEqual([
      'Why exactly?',
      'Because.',
    ]);
  });

  it('appends in sequence mode and ignores an empty parent', () => {
    const items = [content('a'), content('b')];
    expect(
      upsertAskMessageByParent(items, {
        ...ask,
        insertionMode: 'sequence',
        autoExpandAskBlock: true,
      })[2].type,
    ).toBe(ChatContentItemType.ASK);
    expect(
      upsertAskMessageByParent(items, {
        ...ask,
        parentElementBid: '',
        autoExpandAskBlock: true,
      }),
    ).toBe(items);
  });
});

describe('listen slides and element identity', () => {
  it('merges slides by id and orders them by slide then audio position', () => {
    const slide = (
      slide_id: string,
      slide_index: number,
      audio_position: number,
    ) => ({ slide_id, slide_index, audio_position }) as ListenSlideData;
    const merged = mergeListenSlides(
      [slide('s2', 1, 0), slide('s1', 0, 1)],
      undefined,
      [{ ...slide('s2', 1, 0), segment_type: 'html' } as ListenSlideData],
    );
    expect(merged.map(item => item.slide_id)).toEqual(['s1', 's2']);
    expect(merged[1]).toMatchObject({ segment_type: 'html' });
  });

  it('caches a patch under its target element and matches either bid', () => {
    const patch = {
      is_new: false,
      target_element_bid: 'origin',
    } as StudyRecordItem;
    expect(resolveElementCacheIdentityBids(patch, 'patch')).toEqual(['origin']);
    expect(
      resolveElementCacheIdentityBids({} as StudyRecordItem, 'own'),
    ).toEqual(['own']);
    expect(resolveElementCacheIdentityBids({} as StudyRecordItem, '')).toEqual(
      [],
    );

    const identity = new Set(['origin']);
    expect(itemMatchesElementCacheIdentity(content('origin'), identity)).toBe(
      true,
    );
    expect(
      itemMatchesElementCacheIdentity(
        { ...content('copy'), target_element_bid: 'origin' },
        identity,
      ),
    ).toBe(true);
    expect(itemMatchesElementCacheIdentity(content('other'), identity)).toBe(
      false,
    );
  });
});
