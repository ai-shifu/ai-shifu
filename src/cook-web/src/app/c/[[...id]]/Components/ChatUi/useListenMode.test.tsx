import { renderHook, waitFor } from '@testing-library/react';
import type Reveal from 'reveal.js';
import { ChatContentItemType, type ChatContentItem } from '@/c-types/chatUi';
import {
  buildListenAudioSequenceBid,
  resolveListenAudioSourceBid,
  useListenAudioSequence,
  useListenContentData,
  type AudioInteractionItem,
} from './useListenMode';

jest.mock('@/c-api/studyV2', () => ({
  LESSON_FEEDBACK_INTERACTION_MARKER: '%{{sys_lesson_feedback_score}}',
}));

const createContentItem = (
  overrides: Partial<ChatContentItem> = {},
): ChatContentItem => ({
  element_bid: 'content-1',
  type: ChatContentItemType.CONTENT,
  content: 'Narration',
  is_speakable: true,
  ...overrides,
});

const createAudioItem = (
  overrides: Partial<AudioInteractionItem> = {},
): AudioInteractionItem => ({
  ...createContentItem({
    element_bid: buildListenAudioSequenceBid('content-1', 0),
  }),
  page: 0,
  sequenceKind: 'audio',
  audioPosition: 0,
  ...overrides,
});

describe('useListenContentData', () => {
  it('does not create buffering audio sequence items for visual-only content', () => {
    const { result } = renderHook(() =>
      useListenContentData([
        createContentItem({
          element_bid: 'visual-1',
          content: '',
          element_type: 'img',
          is_speakable: false,
        }),
        createContentItem({
          element_bid: 'text-1',
          content: 'Speak this',
          is_speakable: true,
        }),
      ]),
    );

    expect(
      result.current.audioAndInteractionList.map(item => item.element_bid),
    ).toEqual([buildListenAudioSequenceBid('text-1', 0)]);
  });
});

describe('useListenAudioSequence', () => {
  it('resyncs the active slide when a buffering item receives its final page', async () => {
    let currentPage = 0;
    const slide = jest.fn((page: number) => {
      currentPage = page;
    });
    const deckRef = {
      current: {
        getIndices: () => ({ h: currentPage }),
        slide,
      } as unknown as Reveal.Api,
    };
    const currentPptPageRef = { current: 0 };
    const activeElementBidRef = { current: null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: true };
    const contentByBid = new Map<string, ChatContentItem>([
      ['content-1', createContentItem()],
    ]);
    const audioContentByBid = new Map<string, ChatContentItem>([
      ['content-1', createContentItem()],
    ]);
    const setIsAudioPlaying = jest.fn();

    const { rerender, result } = renderHook(
      ({
        audioAndInteractionList,
        sequenceStartSignal,
      }: {
        audioAndInteractionList: AudioInteractionItem[];
        sequenceStartSignal: number;
      }) =>
        useListenAudioSequence({
          audioAndInteractionList,
          deckRef,
          currentPptPageRef,
          activeElementBidRef,
          pendingAutoNextRef,
          shouldStartSequenceRef,
          sequenceStartSignal,
          contentByBid,
          audioContentByBid,
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: resolveListenAudioSourceBid,
          allowAutoPlayback: true,
          isAudioPlaying: false,
          setIsAudioPlaying,
        }),
      {
        initialProps: {
          audioAndInteractionList: [createAudioItem({ page: 0 })],
          sequenceStartSignal: 1,
        },
      },
    );

    await waitFor(() =>
      expect(result.current.activeSequenceElementBid).toBe(
        buildListenAudioSequenceBid('content-1', 0),
      ),
    );

    slide.mockClear();
    rerender({
      audioAndInteractionList: [
        createAudioItem({
          page: 2,
          audioUrl: 'https://example.com/audio.mp3',
        }),
      ],
      sequenceStartSignal: 1,
    });

    await waitFor(() => expect(slide).toHaveBeenCalledWith(2));
  });

  it('does not cache sequence page sync before the deck is mounted', async () => {
    let currentPage = 0;
    const slide = jest.fn((page: number) => {
      currentPage = page;
    });
    const deckRef = {
      current: null as Reveal.Api | null,
    };
    const currentPptPageRef = { current: 0 };
    const activeElementBidRef = { current: null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: true };
    const contentByBid = new Map<string, ChatContentItem>([
      ['content-1', createContentItem()],
    ]);
    const audioContentByBid = new Map<string, ChatContentItem>([
      ['content-1', createContentItem()],
    ]);
    const setIsAudioPlaying = jest.fn();

    const { rerender, result } = renderHook(
      ({
        audioAndInteractionList,
        sequenceStartSignal,
      }: {
        audioAndInteractionList: AudioInteractionItem[];
        sequenceStartSignal: number;
      }) =>
        useListenAudioSequence({
          audioAndInteractionList,
          deckRef,
          currentPptPageRef,
          activeElementBidRef,
          pendingAutoNextRef,
          shouldStartSequenceRef,
          sequenceStartSignal,
          contentByBid,
          audioContentByBid,
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: resolveListenAudioSourceBid,
          allowAutoPlayback: true,
          isAudioPlaying: false,
          setIsAudioPlaying,
        }),
      {
        initialProps: {
          audioAndInteractionList: [createAudioItem({ page: 2 })],
          sequenceStartSignal: 1,
        },
      },
    );

    await waitFor(() =>
      expect(result.current.activeSequenceElementBid).toBe(
        buildListenAudioSequenceBid('content-1', 0),
      ),
    );
    expect(slide).not.toHaveBeenCalled();

    deckRef.current = {
      getIndices: () => ({ h: currentPage }),
      slide,
    } as unknown as Reveal.Api;

    rerender({
      audioAndInteractionList: [createAudioItem({ page: 2 })],
      sequenceStartSignal: 1,
    });

    await waitFor(() => expect(slide).toHaveBeenCalledWith(2));
  });

  it('continues late audio positions that arrive on another element in the same generated block', async () => {
    let currentPage = 0;
    const slide = jest.fn((page: number) => {
      currentPage = page;
    });
    const deckRef = {
      current: {
        getIndices: () => ({ h: currentPage }),
        slide,
      } as unknown as Reveal.Api,
    };
    const currentPptPageRef = { current: 0 };
    const activeElementBidRef = { current: null };
    const pendingAutoNextRef = { current: false };
    const shouldStartSequenceRef = { current: true };
    const firstContent = createContentItem({
      element_bid: 'element-1',
      generated_block_bid: 'generated-block-1',
    });
    const secondContent = createContentItem({
      element_bid: 'element-2',
      generated_block_bid: 'generated-block-1',
    });
    const contentByBid = new Map<string, ChatContentItem>([
      ['element-1', firstContent],
      ['element-2', secondContent],
    ]);
    const audioContentByBid = new Map<string, ChatContentItem>([
      ['element-1', firstContent],
      ['element-2', secondContent],
    ]);
    const setIsAudioPlaying = jest.fn();
    const firstAudioBid = buildListenAudioSequenceBid('element-1', 0);
    const secondAudioBid = buildListenAudioSequenceBid('element-2', 1);

    const { rerender, result } = renderHook(
      ({
        audioAndInteractionList,
        sequenceStartSignal,
      }: {
        audioAndInteractionList: AudioInteractionItem[];
        sequenceStartSignal: number;
      }) =>
        useListenAudioSequence({
          audioAndInteractionList,
          deckRef,
          currentPptPageRef,
          activeElementBidRef,
          pendingAutoNextRef,
          shouldStartSequenceRef,
          sequenceStartSignal,
          contentByBid,
          audioContentByBid,
          previewMode: false,
          shouldRenderEmptyPpt: false,
          getNextContentBid: () => null,
          goToBlock: () => false,
          resolveContentBid: resolveListenAudioSourceBid,
          allowAutoPlayback: true,
          isAudioPlaying: false,
          setIsAudioPlaying,
        }),
      {
        initialProps: {
          audioAndInteractionList: [
            createAudioItem({
              element_bid: firstAudioBid,
              generated_block_bid: 'generated-block-1',
              page: 0,
            }),
          ],
          sequenceStartSignal: 1,
        },
      },
    );

    await waitFor(() =>
      expect(result.current.activeSequenceElementBid).toBe(firstAudioBid),
    );

    slide.mockClear();
    rerender({
      audioAndInteractionList: [
        createAudioItem({
          element_bid: firstAudioBid,
          generated_block_bid: 'generated-block-1',
          page: 0,
        }),
        createAudioItem({
          element_bid: secondAudioBid,
          generated_block_bid: 'generated-block-1',
          page: 2,
          audioPosition: 1,
          audioUrl: 'https://example.com/audio-position-1.mp3',
        }),
      ],
      sequenceStartSignal: 1,
    });

    await waitFor(() =>
      expect(result.current.activeSequenceElementBid).toBe(secondAudioBid),
    );
    expect(slide).toHaveBeenCalledWith(2);
  });
});
