import { renderHook } from '@testing-library/react';

jest.mock('@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook', () => ({
  ChatContentItemType: {
    CONTENT: 'content',
    INTERACTION: 'interaction',
    ASK: 'ask',
    LIKE_STATUS: 'likeStatus',
  },
}));

jest.mock('markdown-flow-ui/renderer', () => ({
  splitContentSegments: (raw: string) => {
    const prefix = 'SANDBOX:';
    if (raw.startsWith(prefix)) {
      return [{ type: 'sandbox', value: raw.slice(prefix.length) }];
    }
    return [{ type: 'markdown', value: raw }];
  },
}));

import { useListenContentData } from '@/app/c/[[...id]]/Components/ChatUi/useListenMode';
import {
  ChatContentItemType,
  type ChatContentItem,
} from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';

const makeContent = (
  generated_block_bid: string,
  content: string,
): ChatContentItem => ({
  type: ChatContentItemType.CONTENT,
  generated_block_bid,
  content,
  audios: [],
  customRenderBar: () => null,
});

describe('listen-mode html table segmentation', () => {
  it('wraps <table> returned as a markdown segment into a sandbox slide', () => {
    const items = [
      makeContent(
        'block-table-markdown',
        '<table border="1"><tr><td>A</td></tr></table>',
      ),
    ];
    const { result } = renderHook(() => useListenContentData(items));

    expect(result.current.slideItems).toHaveLength(1);
    const firstSegment = result.current.slideItems[0].segments[0];
    expect(firstSegment.type).toBe('sandbox');
    expect(String(firstSegment.value)).toContain('<table');
    expect(String(firstSegment.value)).toContain('<div>');
  });

  it('wraps <table> returned as a sandbox segment into a sandbox-root container', () => {
    const items = [
      makeContent(
        'block-table-sandbox',
        'SANDBOX:<table><tr><td>B</td></tr></table>',
      ),
    ];
    const { result } = renderHook(() => useListenContentData(items));

    expect(result.current.slideItems).toHaveLength(1);
    const firstSegment = result.current.slideItems[0].segments[0];
    expect(firstSegment.type).toBe('sandbox');
    expect(String(firstSegment.value)).toContain('<table');
    expect(String(firstSegment.value)).toContain('<div>');
  });

  it('extracts markdown pipe tables from markdown segments with surrounding text', () => {
    const items = [
      makeContent(
        'block-markdown-pipe-table',
        [
          'Before table narrative.',
          '',
          '| 历史时期 | 主要特点 |',
          '| --- | --- |',
          '| 古代 | 祭祀与祈福 |',
          '',
          'After table narrative.',
        ].join('\n'),
      ),
    ];
    const { result } = renderHook(() => useListenContentData(items));

    expect(result.current.slideItems).toHaveLength(1);
    const firstSegment = result.current.slideItems[0].segments[0];
    expect(firstSegment.type).toBe('sandbox');
    expect(String(firstSegment.value)).toContain('<table>');
    expect(String(firstSegment.value)).toContain('历史时期');
    expect(String(firstSegment.value)).not.toContain('Before table narrative.');
    expect(String(firstSegment.value)).not.toContain('After table narrative.');
  });
});
