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
  useListenPpt,
  type AudioInteractionItem,
} from '@/app/c/[[...id]]/Components/ChatUi/useListenMode';
import { ChatContentItemType } from '@/app/c/[[...id]]/Components/ChatUi/useChatLogicHook';

describe('useListenAudioSequence silent visual slides', () => {
  it('shows target visual page while waiting for audio readiness', () => {
    jest.useFakeTimers();
    try {
      let currentSlide = 0;
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 3 }, () => ({}))),
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

      const noAudioItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-no-audio',
        content: 'No audio yet',
        audios: [],
        isAudioStreaming: false,
        customRenderBar: () => null,
      };

      const { result } = renderHook(() =>
        useListenAudioSequence({
          audioAndInteractionList: [
            { ...noAudioItem, page: 1, audioPosition: 0 },
          ],
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([['block-no-audio', noAudioItem]]),
          audioContentByBid: new Map([['block-no-audio', noAudioItem]]),
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

      expect(deck.slide).toHaveBeenCalledWith(1);
      expect(currentSlide).toBe(1);
      expect(result.current.isAudioSequenceActive).toBe(true);

      act(() => {
        jest.advanceTimersByTime(500);
      });

      expect(currentSlide).toBe(1);
      expect(result.current.isAudioSequenceActive).toBe(true);
    } finally {
      jest.useRealTimers();
    }
  });

  it('keeps waiting and resumes when audio arrives late', () => {
    jest.useFakeTimers();
    try {
      let currentSlide = 0;
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 3 }, () => ({}))),
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
        generated_block_bid: 'block-late-audio',
        content: 'Late audio',
        audios: [],
        customRenderBar: () => null,
      };

      const { result, rerender } = renderHook(
        ({ item }: { item: any }) =>
          useListenAudioSequence({
            audioAndInteractionList: [{ ...item, page: 1, audioPosition: 0 }],
            deckRef: deckRef as any,
            currentPptPageRef: currentPptPageRef as any,
            activeBlockBidRef: activeBlockBidRef as any,
            pendingAutoNextRef: pendingAutoNextRef as any,
            shouldStartSequenceRef: shouldStartSequenceRef as any,
            contentByBid: new Map([[item.generated_block_bid, item]]),
            audioContentByBid: new Map([[item.generated_block_bid, item]]),
            previewMode: false,
            shouldRenderEmptyPpt: false,
            getNextContentBid: () => null,
            goToBlock: () => false,
            resolveContentBid: (bid: string | null) => bid,
            isAudioPlaying: false,
            setIsAudioPlaying: () => undefined,
          }),
        {
          initialProps: { item: baseItem },
        },
      );

      act(() => {
        result.current.startSequenceFromIndex(0);
      });

      expect(currentSlide).toBe(1);
      expect(result.current.isAudioSequenceActive).toBe(true);
      expect(result.current.activeAudioBlockBid).toBe(null);

      // Beyond the previous ~9.6s cap, sequence should still be waiting.
      act(() => {
        jest.advanceTimersByTime(12000);
      });
      expect(result.current.isAudioSequenceActive).toBe(true);
      expect(result.current.activeAudioBlockBid).toBe(null);

      const lateAudioItem: any = {
        ...baseItem,
        audios: [{ position: 0, audio_url: 'https://example.com/late.mp3' }],
      };

      act(() => {
        rerender({ item: lateAudioItem });
      });

      // Next retry tick should pick up playable audio and activate the block.
      act(() => {
        jest.advanceTimersByTime(600);
      });
      expect(result.current.activeAudioBlockBid).toBe('block-late-audio');
      expect(result.current.isAudioSequenceActive).toBe(true);
    } finally {
      jest.useRealTimers();
    }
  });

  it('pauses sequence on audio error and prevents auto-advance', () => {
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };
    const setIsAudioPlaying = jest.fn();
    const goToBlock = jest.fn(() => true);

    const firstItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-1',
      content: 'First',
      audios: [{ position: 0, audio_url: 'https://example.com/a1.mp3' }],
      customRenderBar: () => null,
    };
    const secondItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-2',
      content: 'Second',
      audios: [{ position: 0, audio_url: 'https://example.com/a2.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [
          { ...firstItem, page: 0, audioPosition: 0 },
          { ...secondItem, page: 1, audioPosition: 0 },
        ],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([
          ['block-1', firstItem],
          ['block-2', secondItem],
        ]),
        audioContentByBid: new Map([
          ['block-1', firstItem],
          ['block-2', secondItem],
        ]),
        previewMode: false,
        shouldRenderEmptyPpt: false,
        getNextContentBid: () => null,
        goToBlock,
        resolveContentBid: (bid: string | null) => bid,
        isAudioPlaying: false,
        setIsAudioPlaying,
      }),
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });
    expect(result.current.activeAudioBlockBid).toBe('block-1');

    act(() => {
      result.current.handleAudioError();
    });
    expect(setIsAudioPlaying).toHaveBeenCalledWith(false);
    expect(result.current.activeAudioBlockBid).toBe('block-1');

    act(() => {
      result.current.handleAudioEnded();
    });
    expect(result.current.activeAudioBlockBid).toBe('block-1');
    expect(goToBlock).not.toHaveBeenCalled();
  });

  it('keeps interaction blocked until explicit resolve', () => {
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const interactionItem: any = {
      type: ChatContentItemType.INTERACTION,
      generated_block_bid: 'interaction-1',
      content: '?[Continue//continue]',
      customRenderBar: () => null,
    };
    const contentItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-1',
      content: 'Audio after interaction',
      audios: [{ position: 0, audio_url: 'https://example.com/a1.mp3' }],
      customRenderBar: () => null,
    };
    const lateContentItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-2',
      content: 'Late content',
      audios: [{ position: 0, audio_url: 'https://example.com/a2.mp3' }],
      customRenderBar: () => null,
    };

    const initialList: AudioInteractionItem[] = [
      { ...interactionItem, page: 0 },
      { ...contentItem, page: 0, audioPosition: 0 },
    ];
    const appendedList: AudioInteractionItem[] = [
      { ...interactionItem, page: 0 },
      { ...contentItem, page: 0, audioPosition: 0 },
      { ...lateContentItem, page: 1, audioPosition: 0 },
    ];

    const { result, rerender } = renderHook(
      ({ list }: { list: AudioInteractionItem[] }) =>
        useListenAudioSequence({
          audioAndInteractionList: list,
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([
            ['block-1', contentItem],
            ['block-2', lateContentItem],
          ]),
          audioContentByBid: new Map([
            ['block-1', contentItem],
            ['block-2', lateContentItem],
          ]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      {
        initialProps: {
          list: initialList,
        },
      },
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });

    expect(result.current.sequenceInteraction?.generated_block_bid).toBe(
      'interaction-1',
    );
    expect(result.current.activeAudioBlockBid).toBe(null);

    act(() => {
      rerender({ list: appendedList });
    });

    // Still blocked by interaction even after list updates.
    expect(result.current.sequenceInteraction?.generated_block_bid).toBe(
      'interaction-1',
    );
    expect(result.current.activeAudioBlockBid).toBe(null);

    act(() => {
      result.current.handlePlay();
    });

    // Play must not bypass interaction blocking.
    expect(result.current.sequenceInteraction?.generated_block_bid).toBe(
      'interaction-1',
    );
    expect(result.current.activeAudioBlockBid).toBe(null);

    act(() => {
      result.current.continueAfterInteraction();
    });

    expect(result.current.sequenceInteraction).toBe(null);
    expect(result.current.activeAudioBlockBid).toBe('block-1');
  });

  it('waits on next visual without audio and resumes when late audio arrives', () => {
    jest.useFakeTimers();
    try {
      let currentSlide = 0;
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
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

      const imageItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-image',
        content: 'Image narration',
        audios: [{ position: 0, audio_url: 'https://example.com/image.mp3' }],
        customRenderBar: () => null,
      };
      const htmlItemWithoutAudio: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-html',
        content: 'HTML narration pending',
        audios: [],
        customRenderBar: () => null,
      };
      const htmlItemWithAudio: any = {
        ...htmlItemWithoutAudio,
        audios: [{ position: 0, audio_url: 'https://example.com/html.mp3' }],
      };

      const { result, rerender } = renderHook(
        ({ htmlItem }: { htmlItem: any }) =>
          useListenAudioSequence({
            audioAndInteractionList: [
              { ...imageItem, page: 0, audioPosition: 0 },
              { ...htmlItem, page: 1, audioPosition: 0 },
            ],
            deckRef: deckRef as any,
            currentPptPageRef: currentPptPageRef as any,
            activeBlockBidRef: activeBlockBidRef as any,
            pendingAutoNextRef: pendingAutoNextRef as any,
            shouldStartSequenceRef: shouldStartSequenceRef as any,
            contentByBid: new Map([
              ['block-image', imageItem],
              ['block-html', htmlItem],
            ]),
            audioContentByBid: new Map([
              ['block-image', imageItem],
              ['block-html', htmlItem],
            ]),
            previewMode: false,
            shouldRenderEmptyPpt: false,
            getNextContentBid: () => null,
            goToBlock: () => false,
            resolveContentBid: (bid: string | null) => bid,
            isAudioPlaying: false,
            setIsAudioPlaying: () => undefined,
          }),
        {
          initialProps: {
            htmlItem: htmlItemWithoutAudio,
          },
        },
      );

      act(() => {
        result.current.startSequenceFromIndex(0);
      });
      expect(result.current.activeAudioBlockBid).toBe('block-image');

      act(() => {
        result.current.handleAudioEnded();
      });

      // Move to html page but wait there for audio.
      expect(currentSlide).toBe(1);
      expect(result.current.activeAudioBlockBid).toBe(null);
      expect(result.current.isAudioSequenceActive).toBe(true);

      act(() => {
        jest.advanceTimersByTime(500);
      });
      expect(result.current.activeAudioBlockBid).toBe(null);
      expect(result.current.isAudioSequenceActive).toBe(true);

      act(() => {
        rerender({ htmlItem: htmlItemWithAudio });
      });

      act(() => {
        jest.advanceTimersByTime(600);
      });
      expect(result.current.activeAudioBlockBid).toBe('block-html');
      expect(result.current.isAudioSequenceActive).toBe(true);
    } finally {
      jest.useRealTimers();
    }
  });

  it('does not auto-start from older pages when user is on a newer slide', () => {
    let currentSlide = 1;
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
      getIndices: jest.fn(() => ({ h: currentSlide })),
      slide: jest.fn((page: number) => {
        currentSlide = page;
      }),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 1 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: true };

    const olderPageItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-old',
      content: 'Older page',
      audios: [{ position: 0, audio_url: 'https://example.com/old.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [
          { ...olderPageItem, page: 0, audioPosition: 0 },
        ],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([['block-old', olderPageItem]]),
        audioContentByBid: new Map([['block-old', olderPageItem]]),
        previewMode: false,
        shouldRenderEmptyPpt: false,
        getNextContentBid: () => null,
        goToBlock: () => false,
        resolveContentBid: (bid: string | null) => bid,
        isAudioPlaying: false,
        setIsAudioPlaying: () => undefined,
      }),
    );

    expect(currentSlide).toBe(1);
    expect(deck.slide).not.toHaveBeenCalled();
    expect(result.current.isAudioSequenceActive).toBe(false);
    expect(result.current.activeAudioBlockBid).toBe(null);
  });

  it('advances across intermediate visual-only pages to next audio unit', () => {
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

    expect(currentSlide).toBe(2);
    expect(result.current.isAudioSequenceActive).toBe(true);
    expect(result.current.activeAudioBlockBid).toBe('block-1');
  });

  it('advances one slide for trailing silent visuals after final audio', () => {
    let currentSlide = 0;
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 3 }, () => ({}))),
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
      generated_block_bid: 'block-tail',
      content: 'Narration',
      audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [{ ...baseItem, page: 0, audioPosition: 0 }],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([['block-tail', baseItem]]),
        audioContentByBid: new Map([['block-tail', baseItem]]),
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

  it('does not watchdog-advance when player reports active playback', () => {
    jest.useFakeTimers();
    try {
      let currentSlide = 0;
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 3 }, () => ({}))),
        getIndices: jest.fn(() => ({ h: currentSlide })),
        slide: jest.fn((page: number) => {
          currentSlide = page;
        }),
      };

      const deckRef = { current: deck };
      const currentPptPageRef = { current: 0 };
      const activeBlockBidRef = { current: 'block-1' as string | null };
      const pendingAutoNextRef = { current: false };
      const shouldStartSequenceRef = { current: false };
      const goToBlock = jest.fn(() => true);

      const baseItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-1',
        content: 'Long narration',
        audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
        customRenderBar: () => null,
      };
      const audioAndInteractionList: AudioInteractionItem[] = [
        { ...baseItem, page: 0, audioPosition: 0 },
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
          getNextContentBid: () => 'block-2',
          goToBlock,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      );

      act(() => {
        result.current.audioPlayerRef.current = {
          togglePlay: jest.fn(),
          play: jest.fn(),
          pause: jest.fn(),
          getPlaybackState: () => ({
            isPlaying: true,
            isLoading: false,
            isWaitingForSegment: false,
            hasAudio: true,
            isPaused: false,
          }),
        };
      });

      act(() => {
        result.current.startSequenceFromIndex(0);
      });

      act(() => {
        jest.advanceTimersByTime(9000);
      });

      expect(goToBlock).not.toHaveBeenCalled();
      expect(result.current.isAudioSequenceActive).toBe(true);
      expect(result.current.activeAudioBlockBid).toBe('block-1');
    } finally {
      jest.useRealTimers();
    }
  });

  it('does not watchdog-advance after playback has started once', () => {
    jest.useFakeTimers();
    try {
      let currentSlide = 0;
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 3 }, () => ({}))),
        getIndices: jest.fn(() => ({ h: currentSlide })),
        slide: jest.fn((page: number) => {
          currentSlide = page;
        }),
      };

      const deckRef = { current: deck };
      const currentPptPageRef = { current: 0 };
      const activeBlockBidRef = { current: 'block-1' as string | null };
      const pendingAutoNextRef = { current: false };
      const shouldStartSequenceRef = { current: false };
      const goToBlock = jest.fn(() => true);
      const setIsAudioPlaying = jest.fn();

      const baseItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-1',
        content: 'Narration',
        audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
        customRenderBar: () => null,
      };
      const audioAndInteractionList: AudioInteractionItem[] = [
        { ...baseItem, page: 0, audioPosition: 0 },
      ];

      const contentByBid = new Map<string, any>([['block-1', baseItem]]);
      const audioContentByBid = new Map<string, any>([['block-1', baseItem]]);

      const { result, rerender } = renderHook(
        ({ isAudioPlaying }: { isAudioPlaying: boolean }) =>
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
            getNextContentBid: () => 'block-2',
            goToBlock,
            resolveContentBid: (bid: string | null) => bid,
            isAudioPlaying,
            setIsAudioPlaying,
          }),
        {
          initialProps: {
            isAudioPlaying: false,
          },
        },
      );

      act(() => {
        result.current.startSequenceFromIndex(0);
      });

      act(() => {
        rerender({ isAudioPlaying: true });
      });

      act(() => {
        rerender({ isAudioPlaying: false });
      });

      act(() => {
        jest.advanceTimersByTime(25000);
      });

      expect(goToBlock).not.toHaveBeenCalled();
      expect(result.current.isAudioSequenceActive).toBe(true);
      expect(result.current.activeAudioBlockBid).toBe('block-1');
    } finally {
      jest.useRealTimers();
    }
  });

  it('uses duration-aware watchdog timeout for long audio', () => {
    jest.useFakeTimers();
    try {
      let currentSlide = 0;
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 3 }, () => ({}))),
        getIndices: jest.fn(() => ({ h: currentSlide })),
        slide: jest.fn((page: number) => {
          currentSlide = page;
        }),
      };

      const deckRef = { current: deck };
      const currentPptPageRef = { current: 0 };
      const activeBlockBidRef = { current: 'block-1' as string | null };
      const pendingAutoNextRef = { current: false };
      const shouldStartSequenceRef = { current: false };
      const goToBlock = jest.fn(() => true);

      const baseItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-1',
        content: 'Long narration',
        audios: [
          {
            position: 0,
            audio_url: 'https://example.com/a0.mp3',
            duration_ms: 15000,
          },
        ],
        audioTracksByPosition: {
          0: {
            audioUrl: 'https://example.com/a0.mp3',
            audioDurationMs: 15000,
          },
        },
        customRenderBar: () => null,
      };
      const audioAndInteractionList: AudioInteractionItem[] = [
        { ...baseItem, page: 0, audioPosition: 0 },
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
          getNextContentBid: () => 'block-2',
          goToBlock,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      );

      act(() => {
        result.current.startSequenceFromIndex(0);
      });

      act(() => {
        jest.advanceTimersByTime(9000);
      });
      expect(goToBlock).not.toHaveBeenCalled();

      act(() => {
        jest.advanceTimersByTime(11000);
      });
      expect(goToBlock).not.toHaveBeenCalled();
      expect(currentSlide).toBe(0);
      expect(result.current.isAudioSequenceActive).toBe(true);
      expect(result.current.activeAudioBlockBid).toBe('block-1');
    } finally {
      jest.useRealTimers();
    }
  });

  it('keeps sequence continuity when list index shifts', () => {
    let currentSlide = 0;
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
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

    const firstItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-1',
      content: 'First',
      audios: [{ position: 0, audio_url: 'https://example.com/a1.mp3' }],
      customRenderBar: () => null,
    };
    const secondItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-2',
      content: 'Second',
      audios: [{ position: 0, audio_url: 'https://example.com/a2.mp3' }],
      customRenderBar: () => null,
    };

    const baseList: AudioInteractionItem[] = [
      { ...firstItem, page: 0, audioPosition: 0 },
      { ...secondItem, page: 1, audioPosition: 0 },
    ];

    const shiftedList: AudioInteractionItem[] = [
      {
        type: ChatContentItemType.INTERACTION,
        generated_block_bid: 'interaction-1',
        content: '?[go//go]',
        page: 0,
        customRenderBar: () => null,
      } as any,
      { ...firstItem, page: 0, audioPosition: 0 },
      { ...secondItem, page: 1, audioPosition: 0 },
    ];

    const { result, rerender } = renderHook(
      ({ list }: { list: AudioInteractionItem[] }) =>
        useListenAudioSequence({
          audioAndInteractionList: list,
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([
            ['block-1', firstItem],
            ['block-2', secondItem],
          ]),
          audioContentByBid: new Map([
            ['block-1', firstItem],
            ['block-2', secondItem],
          ]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      {
        initialProps: {
          list: baseList,
        },
      },
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });
    expect(result.current.activeAudioBlockBid).toBe('block-1');

    act(() => {
      rerender({ list: shiftedList });
    });

    act(() => {
      result.current.handleAudioEnded();
    });

    expect(result.current.activeAudioBlockBid).toBe('block-2');
    expect(result.current.isAudioSequenceActive).toBe(true);
  });

  it('ignores stale audio-ended events from previous audio token', () => {
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const firstItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-1',
      content: 'First',
      audios: [{ position: 0, audio_url: 'https://example.com/a1.mp3' }],
      customRenderBar: () => null,
    };
    const secondItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-2',
      content: 'Second',
      audios: [{ position: 0, audio_url: 'https://example.com/a2.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [
          { ...firstItem, page: 0, audioPosition: 0 },
          { ...secondItem, page: 1, audioPosition: 0 },
        ],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([
          ['block-1', firstItem],
          ['block-2', secondItem],
        ]),
        audioContentByBid: new Map([
          ['block-1', firstItem],
          ['block-2', secondItem],
        ]),
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
    const token1 = result.current.audioSequenceToken;
    expect(result.current.activeAudioBlockBid).toBe('block-1');

    act(() => {
      result.current.handleAudioEnded(token1);
    });

    const token2 = result.current.audioSequenceToken;
    expect(token2).toBeGreaterThan(token1);
    expect(result.current.activeAudioBlockBid).toBe('block-2');
    expect(result.current.isAudioSequenceActive).toBe(true);

    act(() => {
      result.current.handleAudioEnded(token1);
    });

    expect(result.current.activeAudioBlockBid).toBe('block-2');
    expect(result.current.isAudioSequenceActive).toBe(true);
  });

  it('continues after interaction through visual gap to delayed next audio', () => {
    let currentSlide = 0;
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
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

    const interactionItem: any = {
      type: ChatContentItemType.INTERACTION,
      generated_block_bid: 'interaction-1',
      content: '?[continue//continue]',
      customRenderBar: () => null,
    };
    const firstAudioItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-1',
      content: 'First audio',
      audios: [{ position: 0, audio_url: 'https://example.com/a1.mp3' }],
      customRenderBar: () => null,
    };
    const htmlItemWithoutAudio: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-2',
      content: 'HTML without audio',
      audios: [],
      customRenderBar: () => null,
    };
    const htmlItemWithAudio: any = {
      ...htmlItemWithoutAudio,
      audios: [{ position: 0, audio_url: 'https://example.com/a2.mp3' }],
    };

    const initialList: AudioInteractionItem[] = [
      { ...interactionItem, page: 0 },
      { ...firstAudioItem, page: 0, audioPosition: 0 },
      { ...htmlItemWithoutAudio, page: 2, audioPosition: 0 },
    ];
    const nextList: AudioInteractionItem[] = [
      ...initialList.slice(0, 2),
      { ...htmlItemWithAudio, page: 2, audioPosition: 0 },
    ];

    const { result, rerender } = renderHook(
      ({ list }: { list: AudioInteractionItem[] }) =>
        useListenAudioSequence({
          audioAndInteractionList: list,
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([
            ['block-1', firstAudioItem],
            ['block-2', htmlItemWithAudio],
          ]),
          audioContentByBid: new Map([
            ['block-1', firstAudioItem],
            ['block-2', htmlItemWithAudio],
          ]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      {
        initialProps: {
          list: initialList,
        },
      },
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });

    expect(result.current.sequenceInteraction?.generated_block_bid).toBe(
      'interaction-1',
    );
    expect(result.current.activeAudioBlockBid).toBe(null);

    act(() => {
      result.current.continueAfterInteraction();
    });

    expect(result.current.activeAudioBlockBid).toBe('block-1');

    act(() => {
      result.current.handleAudioEnded();
    });

    expect(currentSlide).toBe(2);
    expect(result.current.sequenceInteraction).toBe(null);
    expect(result.current.activeAudioBlockBid).toBe(null);
    expect(result.current.isAudioSequenceActive).toBe(true);

    act(() => {
      rerender({ list: nextList });
    });

    expect(result.current.activeAudioBlockBid).toBe('block-2');
    expect(result.current.isAudioSequenceActive).toBe(true);
    expect(currentSlide).toBe(2);
  });

  it('continues to the correct next unit when list shifts during interaction', () => {
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const audio1: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-1',
      content: 'Audio 1',
      audios: [{ position: 0, audio_url: 'https://example.com/a1.mp3' }],
      customRenderBar: () => null,
    };
    const interaction: any = {
      type: ChatContentItemType.INTERACTION,
      generated_block_bid: 'interaction-1',
      content: '?[Continue//continue]',
      customRenderBar: () => null,
    };
    const audio2: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-2',
      content: 'Audio 2',
      audios: [{ position: 0, audio_url: 'https://example.com/a2.mp3' }],
      customRenderBar: () => null,
    };
    const insertedA: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-insert-a',
      content: 'Inserted A',
      audios: [{ position: 0, audio_url: 'https://example.com/ins-a.mp3' }],
      customRenderBar: () => null,
    };
    const insertedB: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-insert-b',
      content: 'Inserted B',
      audios: [{ position: 0, audio_url: 'https://example.com/ins-b.mp3' }],
      customRenderBar: () => null,
    };

    const baseList: AudioInteractionItem[] = [
      { ...audio1, page: 0, audioPosition: 0 },
      { ...interaction, page: 0 },
      { ...audio2, page: 1, audioPosition: 0 },
    ];

    const shiftedList: AudioInteractionItem[] = [
      { ...insertedA, page: 0, audioPosition: 0 },
      { ...insertedB, page: 0, audioPosition: 0 },
      ...baseList,
    ];

    const { result, rerender } = renderHook(
      ({ list }: { list: AudioInteractionItem[] }) =>
        useListenAudioSequence({
          audioAndInteractionList: list,
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([
            ['block-1', audio1],
            ['block-2', audio2],
            ['block-insert-a', insertedA],
            ['block-insert-b', insertedB],
          ]),
          audioContentByBid: new Map([
            ['block-1', audio1],
            ['block-2', audio2],
            ['block-insert-a', insertedA],
            ['block-insert-b', insertedB],
          ]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      {
        initialProps: {
          list: baseList,
        },
      },
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });
    expect(result.current.activeAudioBlockBid).toBe('block-1');

    act(() => {
      result.current.handleAudioEnded();
    });
    expect(result.current.sequenceInteraction?.generated_block_bid).toBe(
      'interaction-1',
    );
    expect(result.current.activeAudioBlockBid).toBe(null);

    act(() => {
      rerender({ list: shiftedList });
    });

    act(() => {
      result.current.continueAfterInteraction();
    });

    // Should advance past the interaction in the shifted list (index-based
    // next pointer would replay block-1 here).
    expect(result.current.sequenceInteraction).toBe(null);
    expect(result.current.activeAudioBlockBid).toBe('block-2');
    expect(result.current.isAudioSequenceActive).toBe(true);
  });

  it('waits after resolving tail interaction until the next unit arrives', () => {
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const audio1: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-1',
      content: 'Audio 1',
      audios: [{ position: 0, audio_url: 'https://example.com/a1.mp3' }],
      customRenderBar: () => null,
    };
    const interaction: any = {
      type: ChatContentItemType.INTERACTION,
      generated_block_bid: 'interaction-1',
      content: '?[Continue//continue]',
      customRenderBar: () => null,
    };
    const audio2: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-2',
      content: 'Audio 2',
      audios: [{ position: 0, audio_url: 'https://example.com/a2.mp3' }],
      customRenderBar: () => null,
    };

    const baseList: AudioInteractionItem[] = [
      { ...audio1, page: 0, audioPosition: 0 },
      { ...interaction, page: 0 },
    ];

    const appendedList: AudioInteractionItem[] = [
      ...baseList,
      { ...audio2, page: 1, audioPosition: 0 },
    ];

    const { result, rerender } = renderHook(
      ({ list }: { list: AudioInteractionItem[] }) =>
        useListenAudioSequence({
          audioAndInteractionList: list,
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([
            ['block-1', audio1],
            ['block-2', audio2],
          ]),
          audioContentByBid: new Map([
            ['block-1', audio1],
            ['block-2', audio2],
          ]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      {
        initialProps: {
          list: baseList,
        },
      },
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });
    expect(result.current.activeAudioBlockBid).toBe('block-1');

    act(() => {
      result.current.handleAudioEnded();
    });
    expect(result.current.sequenceInteraction?.generated_block_bid).toBe(
      'interaction-1',
    );

    act(() => {
      result.current.continueAfterInteraction();
    });

    // No next unit yet; keep sequence active but with no active audio.
    expect(result.current.sequenceInteraction).toBe(null);
    expect(result.current.activeAudioBlockBid).toBe(null);
    expect(result.current.isAudioSequenceActive).toBe(true);

    act(() => {
      rerender({ list: appendedList });
    });

    expect(result.current.activeAudioBlockBid).toBe('block-2');
    expect(result.current.isAudioSequenceActive).toBe(true);
  });

  it('resumes correctly when resolved tail interaction is removed from list', () => {
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const audio1: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-1',
      content: 'Audio 1',
      audios: [{ position: 0, audio_url: 'https://example.com/a1.mp3' }],
      customRenderBar: () => null,
    };
    const interaction: any = {
      type: ChatContentItemType.INTERACTION,
      generated_block_bid: 'interaction-1',
      content: '?[Continue//continue]',
      customRenderBar: () => null,
    };
    const audio2: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-2',
      content: 'Audio 2',
      audios: [{ position: 0, audio_url: 'https://example.com/a2.mp3' }],
      customRenderBar: () => null,
    };

    const baseList: AudioInteractionItem[] = [
      { ...audio1, page: 0, audioPosition: 0 },
      { ...interaction, page: 0 },
    ];

    // Interaction disappears after submit, and next audio is appended.
    const updatedList: AudioInteractionItem[] = [
      { ...audio1, page: 0, audioPosition: 0 },
      { ...audio2, page: 1, audioPosition: 0 },
    ];

    const { result, rerender } = renderHook(
      ({ list }: { list: AudioInteractionItem[] }) =>
        useListenAudioSequence({
          audioAndInteractionList: list,
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([
            ['block-1', audio1],
            ['block-2', audio2],
          ]),
          audioContentByBid: new Map([
            ['block-1', audio1],
            ['block-2', audio2],
          ]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      {
        initialProps: {
          list: baseList,
        },
      },
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });
    expect(result.current.activeAudioBlockBid).toBe('block-1');

    act(() => {
      result.current.handleAudioEnded();
    });
    expect(result.current.sequenceInteraction?.generated_block_bid).toBe(
      'interaction-1',
    );

    act(() => {
      result.current.continueAfterInteraction();
    });

    expect(result.current.activeAudioBlockBid).toBe(null);
    expect(result.current.isAudioSequenceActive).toBe(true);

    act(() => {
      rerender({ list: updatedList });
    });

    expect(result.current.activeAudioBlockBid).toBe('block-2');
    expect(result.current.isAudioSequenceActive).toBe(true);
  });

  it('starts from current page when bootstrap reset is triggered', () => {
    let currentSlide = 0;
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
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

    const oldItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-old',
      content: 'Old audio',
      audios: [{ position: 0, audio_url: 'https://example.com/old.mp3' }],
      customRenderBar: () => null,
    };
    const nextItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-next',
      content: 'Next audio',
      audios: [{ position: 0, audio_url: 'https://example.com/next.mp3' }],
      customRenderBar: () => null,
    };

    const baseList: AudioInteractionItem[] = [
      { ...oldItem, page: 0, audioPosition: 0 },
      { ...nextItem, page: 1, audioPosition: 0 },
    ];

    const { result, rerender } = renderHook(
      ({ list }: { list: AudioInteractionItem[] }) =>
        useListenAudioSequence({
          audioAndInteractionList: list,
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([
            ['block-old', oldItem],
            ['block-next', nextItem],
          ]),
          audioContentByBid: new Map([
            ['block-old', oldItem],
            ['block-next', nextItem],
          ]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      {
        initialProps: {
          list: baseList,
        },
      },
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });
    expect(result.current.activeAudioBlockBid).toBe('block-old');

    act(() => {
      currentSlide = 1;
      currentPptPageRef.current = 1;
      shouldStartSequenceRef.current = true;
      rerender({ list: [...baseList] });
    });

    expect(result.current.activeAudioBlockBid).toBe('block-next');
    expect(currentSlide).toBe(1);
  });

  it('prefers the active slide block when multiple audio units share a page', () => {
    let currentSlide = 1;
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 2 }, () => ({}))),
      getIndices: jest.fn(() => ({ h: currentSlide })),
      getCurrentSlide: jest.fn(() => ({
        getAttribute: (name: string) =>
          name === 'data-generated-block-bid' ? 'block-next' : null,
      })),
      slide: jest.fn((page: number) => {
        currentSlide = page;
      }),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 1 };
    const activeBlockBidRef = { current: 'block-next' as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const oldItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-old',
      content: 'Old audio',
      audios: [{ position: 0, audio_url: 'https://example.com/old.mp3' }],
      customRenderBar: () => null,
    };
    const nextItem: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-next',
      content: 'Next audio',
      audios: [{ position: 0, audio_url: 'https://example.com/next.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [
          { ...oldItem, page: 1, audioPosition: 0 },
          { ...nextItem, page: 1, audioPosition: 0 },
        ],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([
          ['block-old', oldItem],
          ['block-next', nextItem],
        ]),
        audioContentByBid: new Map([
          ['block-old', oldItem],
          ['block-next', nextItem],
        ]),
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
      result.current.handlePlay();
    });

    expect(result.current.activeAudioBlockBid).toBe('block-next');
    expect(result.current.isAudioSequenceActive).toBe(true);
    expect(currentSlide).toBe(1);
  });

  it('keeps pending auto-next when current block has no immediate successor yet', () => {
    jest.useFakeTimers();
    try {
      let currentSlide = 0;
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 1 }, () => ({}))),
        getIndices: jest.fn(() => ({ h: currentSlide })),
        slide: jest.fn((page: number) => {
          currentSlide = page;
        }),
      };

      const deckRef = { current: deck };
      const currentPptPageRef = { current: 0 };
      const activeBlockBidRef = { current: 'block-1' as string | null };
      const pendingAutoNextRef = { current: false };
      const shouldStartSequenceRef = { current: false };
      const goToBlock = jest.fn(() => false);

      const onlyItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-1',
        content: 'Only block for now',
        audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
        customRenderBar: () => null,
      };

      const { result } = renderHook(() =>
        useListenAudioSequence({
          audioAndInteractionList: [{ ...onlyItem, page: 0, audioPosition: 0 }],
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([['block-1', onlyItem]]),
          audioContentByBid: new Map([['block-1', onlyItem]]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock,
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

      // After the last audio ends, the sequence now waits briefly for the
      // list to grow (in case more content blocks arrive via SSE).
      expect(result.current.isAudioSequenceActive).toBe(true);

      // Advance past the 10-second growth wait timeout.
      act(() => {
        jest.advanceTimersByTime(10_000);
      });

      expect(result.current.isAudioSequenceActive).toBe(false);
      expect(pendingAutoNextRef.current).toBe(true);
      expect(goToBlock).not.toHaveBeenCalled();
    } finally {
      jest.useRealTimers();
    }
  });

  it('advances by visible slide when mapped page drifts before audio end', () => {
    let currentSlide = 0;
    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => Array.from({ length: 2 }, () => ({}))),
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

    const item: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-drift',
      content: 'Narration',
      audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
      customRenderBar: () => null,
    };

    const { result, rerender } = renderHook(
      ({ list }: { list: AudioInteractionItem[] }) =>
        useListenAudioSequence({
          audioAndInteractionList: list,
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([['block-drift', item]]),
          audioContentByBid: new Map([['block-drift', item]]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      {
        initialProps: {
          list: [{ ...item, page: 0, audioPosition: 0 }],
        },
      },
    );

    act(() => {
      result.current.startSequenceFromIndex(0);
    });
    expect(currentSlide).toBe(0);

    // Simulate stream remapping the active unit to a later page while the user
    // is still viewing page 0.
    act(() => {
      rerender({ list: [{ ...item, page: 1, audioPosition: 0 }] });
    });

    act(() => {
      result.current.handleAudioEnded();
    });

    expect(currentSlide).toBe(1);
    expect(result.current.isAudioSequenceActive).toBe(false);
  });

  it('prunes cross-realm-like empty sandbox slides during runtime remap', () => {
    const emptySlide = document.createElement('section');
    const emptyWrapper = document.createElement('div');
    emptyWrapper.className = 'content-render-iframe-sandbox';
    const emptyIframe = document.createElement('iframe');
    emptyWrapper.appendChild(emptyIframe);
    emptySlide.appendChild(emptyWrapper);

    const fakeSandboxContainer = {
      nodeType: Node.ELEMENT_NODE,
      textContent: '',
      childNodes: [],
      querySelector: () => null,
    };
    Object.defineProperty(emptyIframe, 'contentDocument', {
      configurable: true,
      value: {
        querySelector: () => fakeSandboxContainer,
      },
    });

    const visualSlide = document.createElement('section');
    const visualContainer = document.createElement('div');
    visualContainer.className = 'content-render-svg';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    svg.appendChild(rect);
    visualContainer.appendChild(svg);
    visualSlide.appendChild(visualContainer);

    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => [emptySlide, visualSlide]),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const item: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-remap',
      content: 'Narration',
      audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [{ ...item, page: 0, audioPosition: 0 }],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([['block-remap', item]]),
        audioContentByBid: new Map([['block-remap', item]]),
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
      result.current.refreshRuntimePageRemap();
    });

    expect(result.current.resolveRuntimeSequencePage(0)).toBe(1);
    expect(result.current.resolveRuntimeSequencePage(1)).toBe(1);
  });

  it('prunes sandbox iframes with empty document body even without sandbox container', () => {
    const emptySlide = document.createElement('section');
    const emptyWrapper = document.createElement('div');
    emptyWrapper.className = 'content-render-iframe-sandbox';
    const emptyIframe = document.createElement('iframe');
    emptyWrapper.appendChild(emptyIframe);
    emptySlide.appendChild(emptyWrapper);

    const emptyDoc = document.implementation.createHTMLDocument('empty');
    emptyDoc.body.innerHTML = '';
    Object.defineProperty(emptyIframe, 'contentDocument', {
      configurable: true,
      value: emptyDoc,
    });

    const visualSlide = document.createElement('section');
    const visualContainer = document.createElement('div');
    visualContainer.className = 'content-render-svg';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    svg.appendChild(rect);
    visualContainer.appendChild(svg);
    visualSlide.appendChild(visualContainer);

    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => [emptySlide, visualSlide]),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const item: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-empty-iframe-body',
      content: 'Narration',
      audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [{ ...item, page: 0, audioPosition: 0 }],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([['block-empty-iframe-body', item]]),
        audioContentByBid: new Map([['block-empty-iframe-body', item]]),
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
      result.current.refreshRuntimePageRemap();
    });

    expect(emptySlide.classList.contains('listen-runtime-pruned-slide')).toBe(
      true,
    );
    expect(result.current.resolveRuntimeSequencePage(0)).toBe(1);
  });

  it('prunes sandbox iframe slides with nested empty wrappers in sandbox container', () => {
    const emptySlide = document.createElement('section');
    const emptyIframe = document.createElement('iframe');
    emptySlide.appendChild(emptyIframe);

    const emptyDoc = document.implementation.createHTMLDocument(
      'nested-empty-wrapper',
    );
    emptyDoc.body.innerHTML =
      '<div id="root"><div class="sandbox-wrapper"><div class="sandbox-container"><div></div></div></div></div>';
    Object.defineProperty(emptyIframe, 'contentDocument', {
      configurable: true,
      value: emptyDoc,
    });

    const visualSlide = document.createElement('section');
    const visualContainer = document.createElement('div');
    visualContainer.className = 'content-render-svg';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    svg.appendChild(rect);
    visualContainer.appendChild(svg);
    visualSlide.appendChild(visualContainer);

    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => [emptySlide, visualSlide]),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const item: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-empty-iframe-nested-wrapper',
      content: 'Narration',
      audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [{ ...item, page: 0, audioPosition: 0 }],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([['block-empty-iframe-nested-wrapper', item]]),
        audioContentByBid: new Map([
          ['block-empty-iframe-nested-wrapper', item],
        ]),
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
      result.current.refreshRuntimePageRemap();
    });

    expect(emptySlide.classList.contains('listen-runtime-pruned-slide')).toBe(
      true,
    );
    expect(result.current.resolveRuntimeSequencePage(0)).toBe(1);
  });

  it('prunes sandbox iframe placeholders without document and without source hints', () => {
    const emptySlide = document.createElement('section');
    const emptyWrapper = document.createElement('div');
    emptyWrapper.className = 'content-render-iframe-sandbox';
    const emptyIframe = document.createElement('iframe');
    emptyWrapper.appendChild(emptyIframe);
    emptySlide.appendChild(emptyWrapper);

    const visualSlide = document.createElement('section');
    const visualContainer = document.createElement('div');
    visualContainer.className = 'content-render-svg';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    svg.appendChild(rect);
    visualContainer.appendChild(svg);
    visualSlide.appendChild(visualContainer);

    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => [emptySlide, visualSlide]),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const item: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-empty-iframe-no-doc',
      content: 'Narration',
      audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [{ ...item, page: 0, audioPosition: 0 }],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([['block-empty-iframe-no-doc', item]]),
        audioContentByBid: new Map([['block-empty-iframe-no-doc', item]]),
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
      result.current.refreshRuntimePageRemap();
    });

    expect(emptySlide.classList.contains('listen-runtime-pruned-slide')).toBe(
      true,
    );
    expect(result.current.resolveRuntimeSequencePage(0)).toBe(1);
  });

  it('keeps sandbox iframes playable when iframe body contains table content', () => {
    const tableSlide = document.createElement('section');
    const tableWrapper = document.createElement('div');
    tableWrapper.className = 'content-render-iframe-sandbox';
    const tableIframe = document.createElement('iframe');
    tableWrapper.appendChild(tableIframe);
    tableSlide.appendChild(tableWrapper);

    const tableDoc = document.implementation.createHTMLDocument('table');
    tableDoc.body.innerHTML = '<table><tr><td>A</td></tr></table>';
    Object.defineProperty(tableIframe, 'contentDocument', {
      configurable: true,
      value: tableDoc,
    });

    const fallbackSlide = document.createElement('section');
    const fallbackContainer = document.createElement('div');
    fallbackContainer.className = 'content-render-svg';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    svg.appendChild(rect);
    fallbackContainer.appendChild(svg);
    fallbackSlide.appendChild(fallbackContainer);

    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => [tableSlide, fallbackSlide]),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const item: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-table-iframe-body',
      content: 'Narration',
      audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [{ ...item, page: 0, audioPosition: 0 }],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([['block-table-iframe-body', item]]),
        audioContentByBid: new Map([['block-table-iframe-body', item]]),
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
      result.current.refreshRuntimePageRemap();
    });

    expect(tableSlide.classList.contains('listen-runtime-pruned-slide')).toBe(
      false,
    );
    expect(result.current.resolveRuntimeSequencePage(0)).toBe(0);
  });

  it('prunes fully empty section slides during runtime remap', () => {
    const emptySlide = document.createElement('section');

    const visualSlide = document.createElement('section');
    const visualContainer = document.createElement('div');
    visualContainer.className = 'content-render-svg';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    svg.appendChild(rect);
    visualContainer.appendChild(svg);
    visualSlide.appendChild(visualContainer);

    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => [emptySlide, visualSlide]),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const item: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-empty-section',
      content: 'Narration',
      audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [{ ...item, page: 0, audioPosition: 0 }],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([['block-empty-section', item]]),
        audioContentByBid: new Map([['block-empty-section', item]]),
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
      result.current.refreshRuntimePageRemap();
    });

    expect(emptySlide.classList.contains('listen-runtime-pruned-slide')).toBe(
      true,
    );
    expect(emptySlide.getAttribute('data-runtime-pruned')).toBe('1');
    expect(result.current.resolveRuntimeSequencePage(0)).toBe(1);
    expect(result.current.resolveRuntimeSequencePage(1)).toBe(1);
  });

  it('does not keep slides pruned when all runtime slides are empty', () => {
    const emptySlide = document.createElement('section');

    const deck: any = {
      sync: jest.fn(),
      layout: jest.fn(),
      getSlides: jest.fn(() => [emptySlide]),
      getIndices: jest.fn(() => ({ h: 0 })),
      slide: jest.fn(),
    };

    const deckRef = { current: deck };
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: false };

    const item: any = {
      type: ChatContentItemType.CONTENT,
      generated_block_bid: 'block-single-empty',
      content: 'Narration',
      audios: [{ position: 0, audio_url: 'https://example.com/a0.mp3' }],
      customRenderBar: () => null,
    };

    const { result } = renderHook(() =>
      useListenAudioSequence({
        audioAndInteractionList: [{ ...item, page: 0, audioPosition: 0 }],
        deckRef: deckRef as any,
        currentPptPageRef: currentPptPageRef as any,
        activeBlockBidRef: activeBlockBidRef as any,
        pendingAutoNextRef: pendingAutoNextRef as any,
        shouldStartSequenceRef: shouldStartSequenceRef as any,
        contentByBid: new Map([['block-single-empty', item]]),
        audioContentByBid: new Map([['block-single-empty', item]]),
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
      result.current.refreshRuntimePageRemap();
    });

    expect(result.current.resolveRuntimeSequencePage(0)).toBe(0);
    expect(emptySlide.classList.contains('listen-runtime-pruned-slide')).toBe(
      false,
    );
    expect(emptySlide.getAttribute('data-runtime-pruned')).toBeNull();
  });

  it('starts from anchored new content instead of stale active block', () => {
    jest.useFakeTimers();
    try {
      let currentSlide = 0;
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 4 }, () => ({}))),
        getIndices: jest.fn(() => ({ h: currentSlide })),
        getCurrentSlide: jest.fn(() => ({
          getAttribute: (name: string) =>
            name === 'data-generated-block-bid' ? 'block-old' : null,
        })),
        slide: jest.fn((page: number) => {
          currentSlide = page;
        }),
      };

      const deckRef = { current: deck };
      const currentPptPageRef = { current: 0 };
      const activeBlockBidRef = { current: 'block-old' as string | null };
      const pendingAutoNextRef = { current: false };
      const shouldStartSequenceRef = { current: true };
      const sequenceStartAnchorIndexRef = { current: 1 };

      const oldItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-old',
        content: 'Old block',
        audios: [{ position: 0, audio_url: 'https://example.com/old.mp3' }],
        customRenderBar: () => null,
      };
      const newItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-new',
        content: 'New block',
        audios: [{ position: 0, audio_url: 'https://example.com/new.mp3' }],
        customRenderBar: () => null,
      };

      const { result } = renderHook(() =>
        useListenAudioSequence({
          audioAndInteractionList: [
            { ...oldItem, page: 0, audioPosition: 0 },
            { ...newItem, page: 1, audioPosition: 0 },
          ],
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          sequenceStartAnchorIndexRef: sequenceStartAnchorIndexRef as any,
          contentByBid: new Map([
            ['block-old', oldItem],
            ['block-new', newItem],
          ]),
          audioContentByBid: new Map([
            ['block-old', oldItem],
            ['block-new', newItem],
          ]),
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
        jest.advanceTimersByTime(1);
      });

      expect(deck.slide).toHaveBeenCalledWith(1);
      expect(result.current.activeAudioBlockBid).toBe('block-new');
      expect(sequenceStartAnchorIndexRef.current).toBe(null);
    } finally {
      jest.useRealTimers();
    }
  });

  it('falls back to rebuilt list head when anchor index is out of range', () => {
    jest.useFakeTimers();
    try {
      let currentSlide = 0;
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 2 }, () => ({}))),
        getIndices: jest.fn(() => ({ h: currentSlide })),
        getCurrentSlide: jest.fn(() => ({
          getAttribute: () => null,
        })),
        slide: jest.fn((page: number) => {
          currentSlide = page;
        }),
      };

      const deckRef = { current: deck };
      const currentPptPageRef = { current: 0 };
      const activeBlockBidRef = { current: null as string | null };
      const pendingAutoNextRef = { current: false };
      const shouldStartSequenceRef = { current: true };
      const sequenceStartAnchorIndexRef = { current: 99 };

      const newItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-rebuilt',
        content: 'Rebuilt list item',
        audios: [{ position: 0, audio_url: 'https://example.com/new.mp3' }],
        customRenderBar: () => null,
      };

      const { result } = renderHook(() =>
        useListenAudioSequence({
          audioAndInteractionList: [{ ...newItem, page: 0, audioPosition: 0 }],
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          sequenceStartAnchorIndexRef: sequenceStartAnchorIndexRef as any,
          contentByBid: new Map([['block-rebuilt', newItem]]),
          audioContentByBid: new Map([['block-rebuilt', newItem]]),
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
        jest.advanceTimersByTime(1);
      });

      expect(deck.slide).toHaveBeenCalledWith(0);
      expect(result.current.activeAudioBlockBid).toBe('block-rebuilt');
      expect(sequenceStartAnchorIndexRef.current).toBe(null);
    } finally {
      jest.useRealTimers();
    }
  });

  it('triggers manual play fallback when player is paused-but-idle', () => {
    jest.useFakeTimers();
    try {
      const deck: any = {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 2 }, () => ({}))),
        getIndices: jest.fn(() => ({ h: 0 })),
        slide: jest.fn(),
      };

      const deckRef = { current: deck };
      const currentPptPageRef = { current: 0 };
      const activeBlockBidRef = { current: null as string | null };
      const pendingAutoNextRef = { current: false };
      const shouldStartSequenceRef = { current: false };

      const contentItem: any = {
        type: ChatContentItemType.CONTENT,
        generated_block_bid: 'block-autoplay-fallback',
        content: 'Autoplay fallback',
        audios: [{ position: 0, audio_url: 'https://example.com/a.mp3' }],
        customRenderBar: () => null,
      };

      const playMock = jest.fn();
      const { result } = renderHook(() =>
        useListenAudioSequence({
          audioAndInteractionList: [
            { ...contentItem, page: 0, audioPosition: 0 },
          ],
          deckRef: deckRef as any,
          currentPptPageRef: currentPptPageRef as any,
          activeBlockBidRef: activeBlockBidRef as any,
          pendingAutoNextRef: pendingAutoNextRef as any,
          shouldStartSequenceRef: shouldStartSequenceRef as any,
          contentByBid: new Map([
            [contentItem.generated_block_bid, contentItem],
          ]),
          audioContentByBid: new Map([
            [contentItem.generated_block_bid, contentItem],
          ]),
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => true,
          resolveContentBid: (bid: string | null) => bid,
          isAudioPlaying: false,
          setIsAudioPlaying: () => undefined,
        }),
      );

      act(() => {
        result.current.audioPlayerRef.current = {
          togglePlay: jest.fn(),
          play: playMock,
          pause: jest.fn(),
          getPlaybackState: () => ({
            isPlaying: false,
            isLoading: false,
            isWaitingForSegment: false,
            hasAudio: true,
            // Some players report paused=true before explicit resume.
            // Fallback should still call play().
            isPaused: true,
          }),
        };
      });

      act(() => {
        result.current.startSequenceFromIndex(0);
      });

      act(() => {
        jest.advanceTimersByTime(600);
      });

      expect(playMock).toHaveBeenCalledTimes(1);
    } finally {
      jest.useRealTimers();
    }
  });
});

describe('useListenPpt reset guards', () => {
  it('does not reset to first slide while audio sequence is active', () => {
    const onResetSequence = jest.fn();
    const chatRef = { current: null } as any;
    const deckRef = { current: null } as any;
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: null as string | null };
    const pendingAutoNextRef = { current: false };

    const { rerender } = renderHook(
      ({
        slideBid,
        isAudioSequenceActive,
      }: {
        slideBid: string;
        isAudioSequenceActive: boolean;
      }) =>
        useListenPpt({
          chatRef,
          deckRef,
          currentPptPageRef,
          activeBlockBidRef,
          pendingAutoNextRef,
          slideItems: [
            {
              item: {
                type: ChatContentItemType.CONTENT,
                generated_block_bid: slideBid,
              } as any,
              segments: [{ type: 'markdown', value: '<svg></svg>' }],
            },
          ],
          sectionTitle: 'Section A',
          isLoading: false,
          isAudioPlaying: false,
          isAudioSequenceActive,
          isAudioPlayerBusy: () => false,
          shouldRenderEmptyPpt: false,
          onResetSequence,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: (bid: string | null) => bid,
        }),
      {
        initialProps: {
          slideBid: 'block-a',
          isAudioSequenceActive: false,
        },
      },
    );

    expect(onResetSequence).toHaveBeenCalledTimes(1);

    rerender({
      slideBid: 'block-b',
      isAudioSequenceActive: true,
    });

    expect(onResetSequence).toHaveBeenCalledTimes(1);
  });

  it('requests sequence restart after pending auto-next moves to next block', () => {
    let currentSlide = 0;
    const onResetSequence = jest.fn();
    const chatRef = {
      current: {
        querySelectorAll: () => [],
      },
    } as any;
    const deckRef = {
      current: {
        sync: jest.fn(),
        layout: jest.fn(),
        getSlides: jest.fn(() => Array.from({ length: 2 }, () => ({}))),
        getIndices: jest.fn(() => ({ h: currentSlide })),
        getCurrentSlide: jest.fn(() => ({
          getAttribute: (name: string) =>
            name === 'data-generated-block-bid' ? 'block-a' : null,
        })),
        getTotalSlides: jest.fn(() => 2),
        isFirstSlide: jest.fn(() => currentSlide === 0),
        isLastSlide: jest.fn(() => currentSlide === 1),
        slide: jest.fn((page: number) => {
          currentSlide = page;
        }),
        on: jest.fn(),
        off: jest.fn(),
      },
    } as any;
    const currentPptPageRef = { current: 0 };
    const activeBlockBidRef = { current: 'block-a' as string | null };
    const pendingAutoNextRef = { current: true };
    const goToBlock = jest.fn(() => true);

    renderHook(() =>
      useListenPpt({
        chatRef,
        deckRef,
        currentPptPageRef,
        activeBlockBidRef,
        pendingAutoNextRef,
        slideItems: [
          {
            item: {
              type: ChatContentItemType.CONTENT,
              generated_block_bid: 'block-a',
            } as any,
            segments: [{ type: 'markdown', value: '<svg></svg>' }],
          },
          {
            item: {
              type: ChatContentItemType.CONTENT,
              generated_block_bid: 'block-b',
            } as any,
            segments: [{ type: 'markdown', value: '<svg></svg>' }],
          },
        ],
        sectionTitle: 'Section A',
        isLoading: false,
        isAudioPlaying: false,
        isAudioSequenceActive: true,
        isAudioPlayerBusy: () => false,
        shouldRenderEmptyPpt: false,
        onResetSequence,
        getNextContentBid: () => 'block-b',
        goToBlock,
        resolveContentBid: (bid: string | null) => bid,
      }),
    );

    expect(goToBlock).toHaveBeenCalledWith('block-b');
    expect(pendingAutoNextRef.current).toBe(false);
    expect(onResetSequence).toHaveBeenCalledTimes(1);
  });
});
