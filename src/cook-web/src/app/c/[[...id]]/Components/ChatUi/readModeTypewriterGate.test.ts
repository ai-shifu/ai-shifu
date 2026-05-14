import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { appendCustomButtonAfterContent } from './chatUiUtils';
import {
  buildVisibleReadModeItems,
  isReadModeTextContentItemReady,
  syncReadModeTypewriterCache,
  type ReadModeTypewriterCache,
} from './readModeTypewriterGate';

const createTextItem = (
  overrides: Partial<ChatContentItem> = {},
): ChatContentItem => ({
  type: ChatContentItemType.CONTENT,
  element_bid: 'text-1',
  content: 'First text',
  element_type: 'text',
  is_final: false,
  ...overrides,
});

const createHtmlItem = (
  overrides: Partial<ChatContentItem> = {},
): ChatContentItem => ({
  type: ChatContentItemType.CONTENT,
  element_bid: 'html-1',
  content: '<div>Second block</div>',
  element_type: 'html',
  ...overrides,
});

describe('readModeTypewriterGate', () => {
  it('hides following elements until the current text item is final and typed', () => {
    const firstText = createTextItem();
    const secondHtml = createHtmlItem();

    expect(
      buildVisibleReadModeItems([firstText, secondHtml], {}),
    ).toStrictEqual([firstText]);
  });

  it('reveals following elements after the current text item is final and typed', () => {
    const firstText = createTextItem({ is_final: true });
    const secondHtml = createHtmlItem();
    const cache: ReadModeTypewriterCache = {
      'text-1': {
        content: 'First text',
        isFinished: true,
      },
    };

    expect(
      buildVisibleReadModeItems([firstText, secondHtml], cache),
    ).toStrictEqual([firstText, secondHtml]);
  });

  it('keeps previously tracked streamed text gated even after it becomes history', () => {
    const trackedHistoryText = createTextItem({
      is_final: true,
      isHistory: true,
    });
    const secondHtml = createHtmlItem();
    const cache: ReadModeTypewriterCache = {
      'text-1': {
        content: 'First text',
        isFinished: false,
      },
    };

    expect(isReadModeTextContentItemReady(trackedHistoryText, cache)).toBe(false);
    expect(
      buildVisibleReadModeItems([trackedHistoryText, secondHtml], cache),
    ).toStrictEqual([trackedHistoryText]);
  });

  it('resets the cache entry when a tracked text item receives new content', () => {
    const initialCache: ReadModeTypewriterCache = {
      'text-1': {
        content: 'Old text',
        isFinished: true,
      },
    };

    expect(syncReadModeTypewriterCache([createTextItem()], initialCache)).toStrictEqual(
      {
        'text-1': {
          content: 'First text',
          isFinished: false,
        },
      },
    );
  });

  it('keeps finished state when mobile follow-up button markup is appended', () => {
    const finalizedText = createTextItem({
      is_final: true,
      isHistory: true,
      content: appendCustomButtonAfterContent(
        'First text',
        '<custom-button-after-content><span>Ask</span></custom-button-after-content>',
      ),
    });
    const secondHtml = createHtmlItem();
    const initialCache: ReadModeTypewriterCache = {
      'text-1': {
        content: 'First text',
        isFinished: true,
      },
    };

    expect(
      syncReadModeTypewriterCache([finalizedText, secondHtml], initialCache),
    ).toStrictEqual(initialCache);
    expect(
      buildVisibleReadModeItems([finalizedText, secondHtml], initialCache),
    ).toStrictEqual([finalizedText, secondHtml]);
  });
});
