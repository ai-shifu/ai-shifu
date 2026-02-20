import { renderHook } from '@testing-library/react';

jest.mock('@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook', () => ({
  ChatContentItemType: {
    CONTENT: 'content',
    INTERACTION: 'interaction',
    ASK: 'ask',
    LIKE_STATUS: 'likeStatus',
  },
}));

import { useListenContentData } from '@/app/c/[[...id]]/Components/ChatUi/useListenMode';
import {
  ChatContentItemType,
  type ChatContentItem,
} from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';

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
): ChatContentItem => ({
  type: ChatContentItemType.CONTENT,
  generated_block_bid,
  content,
  audios: positions.map(makeAudio),
  customRenderBar: () => null,
});

describe('useListenContentData empty sandbox filtering', () => {
  it('ignores empty sandbox placeholders before table visuals', () => {
    const items = [
      makeContent(
        'block-empty-sandbox',
        '<div></div>\n<table><tr><td>A</td></tr></table>\nNarration after table.',
        [0],
      ),
    ];

    const { result } = renderHook(() => useListenContentData(items));
    const slides = result.current.slideItems;
    const audioEntries = result.current.audioAndInteractionList.filter(
      item =>
        item.type === ChatContentItemType.CONTENT &&
        item.generated_block_bid === 'block-empty-sandbox',
    );

    expect(slides).toHaveLength(1);
    expect(slides[0].segments).toHaveLength(1);
    expect(slides[0].segments[0].type).toBe('sandbox');
    expect(String(slides[0].segments[0].value)).toContain('<table');
    expect(audioEntries).toHaveLength(1);
    expect(audioEntries[0].page).toBe(0);
  });

  it('ignores empty sandbox placeholders before iframe visuals', () => {
    const items = [
      makeContent(
        'block-empty-iframe',
        '<div></div>\n<iframe src="https://example.com"></iframe>\nNarration after iframe.',
        [0],
      ),
    ];

    const { result } = renderHook(() => useListenContentData(items));
    const slides = result.current.slideItems;
    const audioEntries = result.current.audioAndInteractionList.filter(
      item =>
        item.type === ChatContentItemType.CONTENT &&
        item.generated_block_bid === 'block-empty-iframe',
    );

    expect(slides).toHaveLength(1);
    expect(slides[0].segments).toHaveLength(1);
    expect(slides[0].segments[0].type).toBe('sandbox');
    expect(String(slides[0].segments[0].value)).toContain('<iframe');
    expect(audioEntries).toHaveLength(1);
    expect(audioEntries[0].page).toBe(0);
  });

  it('ignores empty svg placeholders before table visuals', () => {
    const items = [
      makeContent(
        'block-empty-svg',
        '<svg></svg>\n<table><tr><td>B</td></tr></table>\nNarration after table.',
        [0],
      ),
    ];

    const { result } = renderHook(() => useListenContentData(items));
    const slides = result.current.slideItems;
    const audioEntries = result.current.audioAndInteractionList.filter(
      item =>
        item.type === ChatContentItemType.CONTENT &&
        item.generated_block_bid === 'block-empty-svg',
    );

    expect(slides).toHaveLength(1);
    expect(slides[0].segments).toHaveLength(1);
    expect(slides[0].segments[0].type).toBe('sandbox');
    expect(String(slides[0].segments[0].value)).toContain('<table');
    expect(audioEntries).toHaveLength(1);
    expect(audioEntries[0].page).toBe(0);
  });

  it('ignores malformed empty svg placeholders before table visuals', () => {
    const items = [
      makeContent(
        'block-malformed-svg',
        '<svg< svg=""></svg<>\n<table><tr><td>C</td></tr></table>\nNarration after table.',
        [0],
      ),
    ];

    const { result } = renderHook(() => useListenContentData(items));
    const slides = result.current.slideItems;
    const audioEntries = result.current.audioAndInteractionList.filter(
      item =>
        item.type === ChatContentItemType.CONTENT &&
        item.generated_block_bid === 'block-malformed-svg',
    );

    expect(slides).toHaveLength(1);
    expect(slides[0].segments).toHaveLength(1);
    expect(String(slides[0].segments[0].value)).toContain('<table');
    expect(audioEntries).toHaveLength(1);
    expect(audioEntries[0].page).toBe(0);
  });
});
