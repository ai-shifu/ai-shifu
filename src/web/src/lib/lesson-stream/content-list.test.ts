import { ChatContentItemType, type ChatContentItem } from '@/types/chat-ui';
import {
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
