import { act, renderHook } from '@testing-library/react';

jest.mock('@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook', () => ({
  ChatContentItemType: {
    CONTENT: 'content',
    INTERACTION: 'interaction',
    ASK: 'ask',
    LIKE_STATUS: 'likeStatus',
  },
}));

import {
  useListenAudioSequence,
  type AudioInteractionItem,
} from '@/app/c/[[...id]]/Components/ChatUi/useListenMode';
import { ChatContentItemType } from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';

describe('useListenAudioSequence silent visual slides', () => {
  it('stops on intermediate slides without audio', () => {
    let currentSlide = 0;
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 5 }, () => ({}))),
      getIndices: jest.fn(() => ({ h: currentSlide })),
      slide: jest.fn((page: number) => {
        currentSlide = page;
      }),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const baseItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-1',
      content: 'Hello',
      audios: [
        { position: 0, audio_url: 'https://example.com/a0.mp3' },
        { position: 1, audio_url: 'https://example.com/a1.mp3' },
      ],
      customRenderBar: () => null,
    };

    const audioAndInteractionList: AudioInteractionItem[] = [
      { ...baseItem, page: 0, audioPosition: 0 },
      { ...baseItem, page: 2, audioPosition: 1 },
    ];

    const contentByBid = new Map<string, any>([['block-1', baseItem]]);
    const audioContentByBid = new Map<string, any>([['block-1', baseItem]]);

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList,
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid,
        audioContentByBid,
        previewMode: false,
        shouldRenderEmptyPpt: false,
        getNextContentBid: () => null,
        goToBlock: () => false,
        resolveContentBid: (bid: string | null) => bid,
        isAudioPlaying: false,
        setIsAudioPlaying: () => undefined,
      }),
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });

    act(() => {
      result.current.handleAudioEnded();
    });

    expect(currentSlide).toBe(1);
    expect(result.current.isAudioSequenceActive).toBe(false);
    expect(result.current.activeAudioBlockBid).toBe(null);
  });
});
