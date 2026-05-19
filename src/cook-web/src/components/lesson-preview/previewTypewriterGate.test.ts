import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { LIKE_STATUS } from '@/c-api/studyV2';
import {
  buildVisiblePreviewItems,
  shouldEnablePreviewTypewriter,
  type PreviewTypewriterCache,
} from './previewTypewriterGate';

const buildContentItem = (
  overrides: Partial<ChatContentItem> & Pick<ChatContentItem, 'element_bid'>,
): ChatContentItem => ({
  content: '',
  readonly: false,
  type: ChatContentItemType.CONTENT,
  ...overrides,
});

describe('previewTypewriterGate', () => {
  test('keeps later preview items hidden until the current text block finishes', () => {
    const items: ChatContentItem[] = [
      buildContentItem({
        element_bid: 'text-1',
        content: 'Hello',
        element_type: 'text',
        shouldUseTypewriter: true,
        is_final: true,
      }),
      {
        element_bid: 'text-1-feedback',
        generated_block_bid: 'text-1-feedback',
        parent_element_bid: 'text-1',
        parent_block_bid: 'text-1',
        like_status: LIKE_STATUS.NONE,
        type: ChatContentItemType.LIKE_STATUS,
      },
      buildContentItem({
        element_bid: 'text-2',
        content: 'World',
        element_type: 'text',
        shouldUseTypewriter: false,
        is_final: true,
      }),
    ];

    const unfinishedCache: PreviewTypewriterCache = {
      'text-1': {
        content: 'Hello',
        isFinished: false,
      },
    };

    expect(
      buildVisiblePreviewItems(items, unfinishedCache).map(
        item => item.element_bid,
      ),
    ).toEqual(['text-1']);

    const finishedCache: PreviewTypewriterCache = {
      'text-1': {
        content: 'Hello',
        isFinished: true,
      },
    };

    expect(
      buildVisiblePreviewItems(items, finishedCache).map(
        item => item.element_bid,
      ),
    ).toEqual(['text-1', 'text-1-feedback', 'text-2']);
  });

  test('skips speaker helper rows for non-text preview elements', () => {
    const items: ChatContentItem[] = [
      buildContentItem({
        element_bid: 'html-1',
        content: '<div>Hello</div>',
        element_type: 'html',
        shouldUseTypewriter: false,
        is_final: true,
      }),
      {
        element_bid: 'html-1-feedback',
        generated_block_bid: 'html-1-feedback',
        parent_element_bid: 'html-1',
        parent_block_bid: 'html-1',
        like_status: LIKE_STATUS.NONE,
        type: ChatContentItemType.LIKE_STATUS,
      },
      buildContentItem({
        element_bid: 'text-2',
        content: 'World',
        element_type: 'text',
        shouldUseTypewriter: false,
        is_final: true,
      }),
    ];

    expect(
      buildVisiblePreviewItems(items, {}).map(item => item.element_bid),
    ).toEqual(['html-1', 'text-2']);
  });

  test('keeps preview typewriter enabled when text grows beyond the finished cache', () => {
    const item = buildContentItem({
      element_bid: 'text-1',
      content: 'Hello world',
      element_type: 'text',
      shouldUseTypewriter: true,
      is_final: true,
    });

    expect(
      shouldEnablePreviewTypewriter(item, {
        content: 'Hello',
        isFinished: true,
      }),
    ).toBe(true);

    expect(
      shouldEnablePreviewTypewriter(item, {
        content: 'Hello world',
        isFinished: true,
      }),
    ).toBe(false);
  });
});
