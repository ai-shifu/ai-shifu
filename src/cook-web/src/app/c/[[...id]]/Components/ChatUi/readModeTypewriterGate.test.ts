import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { appendCustomButtonAfterContent } from './chatUiUtils';
import {
  buildVisibleReadModeItems,
  isReadModeTextContentItemReady,
  normalizeReadModeTypewriterContent,
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
  shouldUseTypewriter: true,
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

  it('keeps previously tracked streamed text gated even after typewriter is disabled', () => {
    const trackedText = createTextItem({
      is_final: true,
      shouldUseTypewriter: false,
    });
    const secondHtml = createHtmlItem();
    const cache: ReadModeTypewriterCache = {
      'text-1': {
        content: 'First text',
        isFinished: false,
      },
    };

    expect(isReadModeTextContentItemReady(trackedText, cache)).toBe(false);
    expect(
      buildVisibleReadModeItems([trackedText, secondHtml], cache),
    ).toStrictEqual([trackedText]);
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

  it('treats non-typewriter text items as ready when no cache entry exists', () => {
    const finalizedStaticText = createTextItem({
      is_final: true,
      shouldUseTypewriter: false,
    });
    const secondHtml = createHtmlItem();

    expect(isReadModeTextContentItemReady(finalizedStaticText, {})).toBe(true);
    expect(
      buildVisibleReadModeItems([finalizedStaticText, secondHtml], {}),
    ).toStrictEqual([finalizedStaticText, secondHtml]);
  });

  it('normalizes typewriter cache content by stripping mobile follow-up button markup', () => {
    expect(
      normalizeReadModeTypewriterContent(
        appendCustomButtonAfterContent(
          'First text',
          '<custom-button-after-content><span>Ask</span></custom-button-after-content>',
        ),
      ),
    ).toBe('First text');
  });

  it('keeps finished state when mobile follow-up button markup is appended', () => {
    const finalizedText = createTextItem({
      is_final: true,
      shouldUseTypewriter: false,
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
