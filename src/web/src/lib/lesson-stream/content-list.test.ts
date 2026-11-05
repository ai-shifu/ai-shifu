import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import {
  applyElementToList,
  type ElementPlacementPolicy,
  isLoadingItem,
  LOADING_ITEM_BID,
  matchesElementBid,
  withoutLoadingItem,
} from './content-list';

const item = (
  fields: Partial<ChatContentItem> & Pick<ChatContentItem, 'element_bid'>,
): ChatContentItem => ({
  content: '',
  type: ChatContentItemType.CONTENT,
  ...fields,
});

describe('lesson stream content list', () => {
  it('recognizes the learner and debug loading placeholders', () => {
    expect(isLoadingItem(item({ element_bid: LOADING_ITEM_BID }))).toBe(true);
    expect(
      isLoadingItem(
        item({
          element_bid: LOADING_ITEM_BID,
          generated_block_bid: LOADING_ITEM_BID,
        }),
      ),
    ).toBe(true);
    expect(
      isLoadingItem(item({ element_bid: 'el-1', generated_block_bid: 'b-1' })),
    ).toBe(false);
  });

  it('removes only the loading placeholder and keeps order', () => {
    const first = item({ element_bid: 'el-1' });
    const second = item({ element_bid: 'el-2' });
    expect(
      withoutLoadingItem([
        first,
        item({ element_bid: LOADING_ITEM_BID }),
        second,
      ]),
    ).toEqual([first, second]);
  });

  it('matches an element by bid and never by an empty bid', () => {
    const element = item({ element_bid: 'el-1' });
    expect(matchesElementBid(element, 'el-1')).toBe(true);
    expect(matchesElementBid(element, 'el-2')).toBe(false);
    expect(matchesElementBid(item({ element_bid: '' }), '')).toBe(false);
  });
});

describe('applyElementToList', () => {
  const finalize = (items: ChatContentItem[], bid: string) =>
    items.map(row =>
      row.element_bid === bid ? { ...row, is_final: true } : row,
    );
  const policy = (
    overrides: Partial<ElementPlacementPolicy> = {},
  ): ElementPlacementPolicy => ({
    completedElementBid: '',
    finalize,
    matches: row => row.element_bid === 'b',
    merge: (previous, next) => ({ ...previous, ...next }),
    ...overrides,
  });

  it('appends an element the list does not hold', () => {
    const list = [item({ element_bid: 'a' })];
    const result = applyElementToList(
      list,
      item({ element_bid: 'b', content: 'new' }),
      policy(),
    );
    expect(result.map(row => row.element_bid)).toEqual(['a', 'b']);
    expect(list).toHaveLength(1);
  });

  it('merges into the matched row in place', () => {
    const list = [
      item({ element_bid: 'b', content: 'old', user_input: 'kept' }),
      item({ element_bid: 'c' }),
    ];
    const result = applyElementToList(
      list,
      item({ element_bid: 'b', content: 'new', user_input: '' }),
      policy({
        merge: (previous, next) => ({
          ...previous,
          ...next,
          user_input: previous.user_input || '',
        }),
      }),
    );
    expect(result.map(row => row.element_bid)).toEqual(['b', 'c']);
    expect(result[0]).toMatchObject({ content: 'new', user_input: 'kept' });
    expect(list[0].content).toBe('old');
  });

  it('finalizes the element it follows before placing the new one', () => {
    const result = applyElementToList(
      [item({ element_bid: 'a' })],
      item({ element_bid: 'b' }),
      policy({ completedElementBid: 'a' }),
    );
    expect(result[0].is_final).toBe(true);
    expect(result[1].is_final).toBeUndefined();
  });

  it('asks a function policy for the completed element against the incoming list', () => {
    const seen: string[][] = [];
    const result = applyElementToList(
      [item({ element_bid: 'a' })],
      item({ element_bid: 'b' }),
      policy({
        completedElementBid: rows => {
          seen.push(rows.map(row => row.element_bid));
          return 'a';
        },
      }),
    );
    expect(seen).toEqual([['a']]);
    expect(result[0].is_final).toBe(true);
  });

  it('skips finalize when no element is completed', () => {
    const calls: string[] = [];
    applyElementToList(
      [item({ element_bid: 'a' })],
      item({ element_bid: 'b' }),
      {
        ...policy(),
        finalize: (rows, bid) => {
          calls.push(bid);
          return rows;
        },
      },
    );
    expect(calls).toEqual([]);
  });
});
