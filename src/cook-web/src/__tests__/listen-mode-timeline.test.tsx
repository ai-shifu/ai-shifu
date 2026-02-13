import { renderHook } from '@testing-library/react';
jest.mock('@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook', () => ({
  ChatContentItemType: {
    CONTENT: 'content',
    INTERACTION: 'interaction',
    ASK: 'ask',
    LIKE_STATUS: 'likeStatus',
  },
}));

import {
  useListenContentData,
  type AudioInteractionItem,
} from '@/app/c/[[...id]]/Components/ChatUi/useListenMode';
import {
  ChatContentItemType,
  type ChatContentItem,
} from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';
import type { ListenSlideData } from '@/c-api/studyV2';

const makeAudio = (position: number) => ({
  position,
  audio_url: `https://example.com/audio-${position}.mp3`,
  audio_bid: `audio-${position}`,
  duration_ms: 1000,
});

const makeContent = (
  generated_block_bid: string,
  content: string,
  positions: number[],
  avContract?: ChatContentItem['avContract'],
): ChatContentItem => ({
  type: ChatContentItemType.CONTENT,
  generated_block_bid,
  content,
  audios: positions.map(makeAudio),
  avContract,
  customRenderBar: () => null,
});

const makeInteraction = (
  generated_block_bid: string,
  content = '?[Continue//continue]',
): ChatContentItem => ({
  type: ChatContentItemType.INTERACTION,
  generated_block_bid,
  content,
  customRenderBar: () => null,
});

const pickAudioEntries = (list: AudioInteractionItem[], bid: string) =>
  list.filter(
    item =>
      item.type === ChatContentItemType.CONTENT &&
      item.generated_block_bid === bid,
  );

describe('useListenContentData timeline mapping', () => {
  let warnSpy: jest.SpyInstance;

  beforeAll(() => {
    warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterAll(() => {
    warnSpy.mockRestore();
  });

  it('maps single-block visual->text->visual->text by audio position', () => {
    const items = [
      makeContent(
        'block-1',
        '<svg><text>v1</text></svg>\nNarration A.\n<svg><text>v2</text></svg>\nNarration B.',
        [0, 1],
      ),
    ];
    const { result } = renderHook(() => useListenContentData(items));

    const audioEntries = pickAudioEntries(
      result.current.audioAndInteractionList,
      'block-1',
    );
    expect(audioEntries).toHaveLength(2);
    expect(audioEntries[0].audioPosition).toBe(0);
    expect(audioEntries[0].page).toBe(0);
    expect(audioEntries[1].audioPosition).toBe(1);
    expect(audioEntries[1].page).toBe(1);

    const hasTextSlide = result.current.slideItems.some(({ segments }) =>
      segments.some(segment => segment.type === 'text'),
    );
    expect(hasTextSlide).toBe(false);
  });

  it('pairs cross-block narration with previous block visual', () => {
    const items = [
      makeContent('block-a', '<svg><text>A</text></svg>', []),
      makeContent('block-b', 'Narration for previous visual.', [0]),
    ];
    const { result } = renderHook(() => useListenContentData(items));
    const audioEntries = pickAudioEntries(
      result.current.audioAndInteractionList,
      'block-b',
    );

    expect(audioEntries).toHaveLength(1);
    expect(audioEntries[0].page).toBe(0);
  });

  it('keeps block-local mapping when text follows a new visual in next block', () => {
    const items = [
      makeContent('block-a', 'Narration before any visual.', [0]),
      makeContent('block-b', '<svg><text>B</text></svg>\nNarration B.', [0]),
    ];
    const { result } = renderHook(() => useListenContentData(items));
    const audioEntriesA = pickAudioEntries(
      result.current.audioAndInteractionList,
      'block-a',
    );
    const audioEntriesB = pickAudioEntries(
      result.current.audioAndInteractionList,
      'block-b',
    );

    expect(audioEntriesA).toHaveLength(1);
    expect(audioEntriesA[0].page).toBe(0);
    expect(audioEntriesB).toHaveLength(1);
    expect(audioEntriesB[0].page).toBe(0);
  });

  it('treats markdown images as visual boundaries for mapping', () => {
    const items = [
      makeContent(
        'block-img',
        '![alt](https://example.com/a.png)\nNarration after image.',
        [0],
      ),
    ];
    const { result } = renderHook(() => useListenContentData(items));
    const audioEntries = pickAudioEntries(
      result.current.audioAndInteractionList,
      'block-img',
    );

    expect(result.current.slideItems).toHaveLength(1);
    expect(audioEntries).toHaveLength(1);
    expect(audioEntries[0].page).toBe(0);
  });

  it('queues multiple interactions on the same timeline page', () => {
    const items = [
      makeContent('block-queue', '<svg><text>Q</text></svg>\nNarration.', [0]),
      makeInteraction('interaction-1', '?[One//one]'),
      makeInteraction('interaction-2', '?[Two//two]'),
    ];
    const { result } = renderHook(() => useListenContentData(items));
    const interactionQueue = result.current.interactionByPage.get(0) || [];

    expect(interactionQueue).toHaveLength(2);
    expect(interactionQueue[0].generated_block_bid).toBe('interaction-1');
    expect(interactionQueue[1].generated_block_bid).toBe('interaction-2');
  });

  it('prefers backend slides for render pages and keeps audio slide ids', () => {
    const content = makeContent(
      'block-backend',
      'Narration A. Narration B.',
      [0, 1],
    );
    content.audioSlideIdByPosition = {
      0: 'slide-0',
      1: 'slide-1',
    };
    const backendSlides: ListenSlideData[] = [
      {
        slide_id: 'slide-0',
        generated_block_bid: 'block-backend',
        slide_index: 0,
        audio_position: 0,
        visual_kind: 'sandbox',
        segment_type: 'sandbox',
        segment_content: '<div>Slide A</div>',
        source_span: [0, 10],
        is_placeholder: false,
      },
      {
        slide_id: 'slide-1',
        generated_block_bid: 'block-backend',
        slide_index: 1,
        audio_position: 1,
        visual_kind: 'sandbox',
        segment_type: 'sandbox',
        segment_content: '<div>Slide B</div>',
        source_span: [11, 20],
        is_placeholder: false,
      },
    ];

    const { result } = renderHook(() =>
      useListenContentData([content], backendSlides),
    );
    const audioEntries = pickAudioEntries(
      result.current.audioAndInteractionList,
      'block-backend',
    );

    expect(result.current.slideItems).toHaveLength(2);
    expect(result.current.slideItems[0].segments[0].value).toContain('Slide A');
    expect(result.current.slideItems[1].segments[0].value).toContain('Slide B');
    expect(audioEntries).toHaveLength(2);
    expect(audioEntries[0].page).toBe(0);
    expect(audioEntries[0].audioSlideId).toBe('slide-0');
    expect(audioEntries[1].page).toBe(1);
    expect(audioEntries[1].audioSlideId).toBe('slide-1');
  });

  it('uses av_contract speakable positions when audio payload is partial', () => {
    const avContract: NonNullable<ChatContentItem['avContract']> = {
      visual_boundaries: [
        {
          kind: 'svg',
          position: 0,
          block_bid: 'block-contract',
          source_span: [0, 20],
        },
        {
          kind: 'svg',
          position: 1,
          block_bid: 'block-contract',
          source_span: [30, 50],
        },
      ],
      speakable_segments: [
        {
          position: 0,
          text: 'Narration A',
          after_visual_kind: 'svg',
          block_bid: 'block-contract',
          source_span: [21, 29],
        },
        {
          position: 1,
          text: 'Narration B',
          after_visual_kind: 'svg',
          block_bid: 'block-contract',
          source_span: [51, 60],
        },
      ],
    };
    const items = [
      makeContent(
        'block-contract',
        '<svg><text>v1</text></svg>\nNarration A.\n<svg><text>v2</text></svg>\nNarration B.',
        [0],
        avContract,
      ),
    ];
    const { result } = renderHook(() => useListenContentData(items));
    const audioEntries = pickAudioEntries(
      result.current.audioAndInteractionList,
      'block-contract',
    );

    expect(audioEntries).toHaveLength(2);
    expect(audioEntries[0].audioPosition).toBe(0);
    expect(audioEntries[1].audioPosition).toBe(1);
  });

  it('keeps content and interaction timeline order by source sequence', () => {
    const items = [
      makeContent('block-order-a', 'Narration A.', [0]),
      makeInteraction('interaction-order', '?[Continue//continue]'),
      makeContent('block-order-b', 'Narration B.', [0]),
    ];
    const { result } = renderHook(() => useListenContentData(items));
    const sequence = result.current.audioAndInteractionList.map(item =>
      item.type === ChatContentItemType.INTERACTION
        ? `interaction:${item.generated_block_bid}`
        : `content:${item.generated_block_bid}`,
    );

    expect(sequence).toEqual([
      'content:block-order-a',
      'interaction:interaction-order',
      'content:block-order-b',
    ]);
  });

  it('includes av_contract-only content before interaction entries', () => {
    const avContract: NonNullable<ChatContentItem['avContract']> = {
      visual_boundaries: [
        {
          kind: 'svg',
          position: 0,
          block_bid: 'block-contract-only',
          source_span: [0, 20],
        },
      ],
      speakable_segments: [
        {
          position: 0,
          text: 'Narration A',
          after_visual_kind: 'svg',
          block_bid: 'block-contract-only',
          source_span: [21, 29],
        },
      ],
    };
    const items = [
      makeContent(
        'block-contract-only',
        '<svg><text>v1</text></svg>\nNarration A.',
        [],
        avContract,
      ),
      makeInteraction('interaction-after-contract'),
    ];
    const { result } = renderHook(() => useListenContentData(items));
    const sequence = result.current.audioAndInteractionList.map(item =>
      item.type === ChatContentItemType.INTERACTION
        ? `interaction:${item.generated_block_bid}`
        : `content:${item.generated_block_bid}`,
    );

    expect(sequence).toEqual([
      'content:block-contract-only',
      'interaction:interaction-after-contract',
    ]);
  });

  it('deduplicates queue units by block+position and patches latest payload', () => {
    const first = makeContent('block-dup', 'Narration A.', [0]);
    const second = makeContent('block-dup', 'Narration A updated.', [0]);
    second.audioTracksByPosition = {
      0: {
        audioUrl: 'https://example.com/new.mp3',
        isAudioStreaming: false,
      },
    };

    const items = [first, second];
    const { result } = renderHook(() => useListenContentData(items));
    const audioEntries = pickAudioEntries(
      result.current.audioAndInteractionList,
      'block-dup',
    );

    expect(audioEntries).toHaveLength(1);
    expect(audioEntries[0].content).toBe('Narration A updated.');
    expect(audioEntries[0].audioTracksByPosition?.[0]?.audioUrl).toBe(
      'https://example.com/new.mp3',
    );
  });

  it('renders gfm tables without outer pipes as visual segments', () => {
    const items = [
      makeContent('block-table', 'Name | Score\n--- | ---\nAlice | 95', [0]),
    ];
    const { result } = renderHook(() => useListenContentData(items));

    expect(result.current.slideItems).toHaveLength(1);
    const firstSegment = result.current.slideItems[0].segments[0];
    expect(firstSegment.type).toBe('sandbox');
    expect(String(firstSegment.value)).toContain('<table>');
  });

  it('renders text-only content as blank fallback slide', () => {
    const items = [
      makeContent('block-text', '# Title\n\nOnly text content.', [0]),
    ];
    const { result } = renderHook(() => useListenContentData(items));

    expect(result.current.slideItems).toHaveLength(1);
    const firstSegment = result.current.slideItems[0].segments[0];
    expect(firstSegment.type).toBe('sandbox');
    expect(String(firstSegment.value)).toContain('<div');
    const audioEntries = pickAudioEntries(
      result.current.audioAndInteractionList,
      'block-text',
    );
    expect(audioEntries).toHaveLength(1);
    expect(audioEntries[0].page).toBe(0);
  });

  it('renders html tables split by embedded <img> tags as visual segments', () => {
    const items = [
      makeContent(
        'block-html-table',
        '<table><tr><td>A</td><td><img src="https://example.com/a.png" /></td></tr></table>',
        [0],
      ),
    ];
    const { result } = renderHook(() => useListenContentData(items));

    expect(result.current.slideItems).toHaveLength(1);
    const firstSegment = result.current.slideItems[0].segments[0];
    expect(firstSegment.type).toBe('sandbox');
    expect(String(firstSegment.value)).toContain('<table');
  });
});
