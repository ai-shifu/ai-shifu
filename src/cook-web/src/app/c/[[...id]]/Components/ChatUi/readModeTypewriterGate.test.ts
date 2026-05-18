import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import { appendCustomButtonAfterContent } from './chatUiUtils';
import {
  buildVisibleReadModeItems,
  isTrailingVisibleReadModeTextItem,
  isReadModeTextContentItemReady,
  normalizeReadModeTypewriterContent,
  resolveReadModeTypewriterKeepAliveElementBid,
  shouldEnableReadModeTypewriter,
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

const createInteractionItem = (
  overrides: Partial<ChatContentItem> = {},
): ChatContentItem => ({
  type: ChatContentItemType.INTERACTION,
  element_bid: 'interaction-1',
  content: '?[Next//_sys_next_chapter]',
  element_type: 'interaction',
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

  it('treats history-like listen mode text as ready even when an unfinished cache entry exists', () => {
    const historyLikeText = createTextItem({
      is_final: true,
      isHistory: true,
      shouldUseTypewriter: false,
      shouldRenderAsHistoryInReadMode: true,
    });
    const secondHtml = createHtmlItem();
    const cache: ReadModeTypewriterCache = {
      'text-1': {
        content: 'First text',
        isFinished: false,
      },
    };

    expect(isReadModeTextContentItemReady(historyLikeText, cache)).toBe(true);
    expect(
      buildVisibleReadModeItems([historyLikeText, secondHtml], cache),
    ).toStrictEqual([historyLikeText, secondHtml]);
    expect(
      syncReadModeTypewriterCache([historyLikeText, secondHtml], cache),
    ).toStrictEqual({});
  });

  it('resets the cache entry when a tracked text item receives new content', () => {
    const initialCache: ReadModeTypewriterCache = {
      'text-1': {
        content: 'Old text',
        isFinished: true,
      },
    };

    expect(
      syncReadModeTypewriterCache([createTextItem()], initialCache),
    ).toStrictEqual({
      'text-1': {
        content: 'First text',
        isFinished: false,
      },
    });
  });

  it('keeps typewriter enabled when the current text content outgrows a finished cache entry', () => {
    const appendedText = createTextItem({
      content: 'First text\n\nSecond text',
    });
    const finishedCacheEntry: ReadModeTypewriterCache['text-1'] = {
      content: 'First text',
      isFinished: true,
    };

    expect(
      shouldEnableReadModeTypewriter(appendedText, finishedCacheEntry),
    ).toBe(true);
  });

  it('keeps typewriter enabled for a non-final text item after the current chunk finishes', () => {
    const unfinishedText = createTextItem({
      content: 'First text',
      is_final: false,
    });
    const finishedCacheEntry: ReadModeTypewriterCache['text-1'] = {
      content: 'First text',
      isFinished: true,
    };

    expect(
      shouldEnableReadModeTypewriter(unfinishedText, finishedCacheEntry),
    ).toBe(true);
  });

  it('keeps typewriter enabled for the trailing streamed text item between segments', () => {
    const finalizedChunk = createTextItem({
      content: 'First text',
      is_final: true,
    });
    const finishedCacheEntry: ReadModeTypewriterCache['text-1'] = {
      content: 'First text',
      isFinished: true,
    };

    expect(
      shouldEnableReadModeTypewriter(finalizedChunk, finishedCacheEntry, {
        keepAliveWhileStreaming: true,
      }),
    ).toBe(true);
  });

  it('does not keep the previous session text alive before the new stream emits its first element', () => {
    expect(
      resolveReadModeTypewriterKeepAliveElementBid({
        isOutputInProgress: true,
        currentStreamingTextElementBid: '',
        currentOutputTextElementBid: '',
      }),
    ).toBe('');
  });

  it('preserves the current session text keep-alive bid between streamed segments', () => {
    expect(
      resolveReadModeTypewriterKeepAliveElementBid({
        isOutputInProgress: true,
        currentStreamingTextElementBid: '',
        currentOutputTextElementBid: 'text-1',
      }),
    ).toBe('text-1');
  });

  it('does not let a later interaction steal the current text keep-alive anchor', () => {
    expect(
      resolveReadModeTypewriterKeepAliveElementBid({
        isOutputInProgress: true,
        currentStreamingTextElementBid: '',
        currentOutputTextElementBid: 'text-1',
      }),
    ).toBe('text-1');
  });

  it('switches keep-alive to the latest streamed text element when a new text starts', () => {
    expect(
      resolveReadModeTypewriterKeepAliveElementBid({
        isOutputInProgress: true,
        currentStreamingTextElementBid: 'text-2',
        currentOutputTextElementBid: 'text-1',
      }),
    ).toBe('text-2');
  });

  it('treats the trailing text item as keep-alive eligible only when it is the last visible item', () => {
    const trailingText = createTextItem({ is_final: true });

    expect(isTrailingVisibleReadModeTextItem([trailingText], 'text-1')).toBe(
      true,
    );
    expect(
      isTrailingVisibleReadModeTextItem(
        [trailingText, createInteractionItem()],
        'text-1',
      ),
    ).toBe(false);
  });

  it('does not re-enable typewriter for a finished text item when content is only rewritten', () => {
    const rewrittenText = createTextItem({
      content: 'Rewritten first text',
      is_final: true,
    });
    const finishedCacheEntry: ReadModeTypewriterCache['text-1'] = {
      content: 'First text',
      isFinished: true,
    };

    expect(
      shouldEnableReadModeTypewriter(rewrittenText, finishedCacheEntry),
    ).toBe(false);
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
