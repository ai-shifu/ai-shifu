import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import {
  buildPreviewBusinessErrorItem,
  replacePreviewLoadingWithBusinessError,
} from './usePreviewChat';

describe('usePreviewChat business error rendering', () => {
  test('replaces loading placeholder with backend business error message', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'loading',
        generated_block_bid: 'loading',
        content: '',
        type: ChatContentItemType.CONTENT,
      },
    ];

    expect(
      replacePreviewLoadingWithBusinessError(
        items,
        '积分余额不足，暂时无法继续调用，请先充值或开通订阅',
      ),
    ).toEqual([
      buildPreviewBusinessErrorItem(
        '积分余额不足，暂时无法继续调用，请先充值或开通订阅',
      ),
    ]);
  });

  test('preserves existing preview items and appends one business error row', () => {
    const items: ChatContentItem[] = [
      {
        element_bid: 'content-1',
        generated_block_bid: 'content-1',
        content: 'Existing content',
        type: ChatContentItemType.CONTENT,
      },
      {
        element_bid: 'loading',
        generated_block_bid: 'loading',
        content: '',
        type: ChatContentItemType.CONTENT,
      },
    ];

    expect(replacePreviewLoadingWithBusinessError(items, '余额不足')).toEqual([
      items[0],
      buildPreviewBusinessErrorItem('余额不足'),
    ]);
  });
});
