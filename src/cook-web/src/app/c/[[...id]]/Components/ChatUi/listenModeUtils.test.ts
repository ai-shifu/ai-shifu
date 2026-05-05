import {
  canRequestListenModeTtsForItem,
  resolveListenSlideSubtitleCues,
  resolveListenModeTtsReadyElementBids,
} from './listenModeUtils';

type ChatContentItem = NonNullable<
  Parameters<typeof canRequestListenModeTtsForItem>[0]
>;

const ChatContentItemType = {
  LIKE_STATUS: 'likeStatus',
} as const;

const createContentItem = (
  overrides: Partial<ChatContentItem> = {},
): ChatContentItem => ({
  element_bid: 'content-1',
  type: 'content',
  content: '',
  ...overrides,
});

const createLikeStatusItem = (
  parentElementBid: string,
  overrides: Partial<ChatContentItem> = {},
): ChatContentItem => ({
  element_bid: '',
  parent_element_bid: parentElementBid,
  type: ChatContentItemType.LIKE_STATUS as ChatContentItem['type'],
  ...overrides,
});

describe('listenModeUtils', () => {
  it('marks speakable content as requestable for listen-mode tts', () => {
    expect(
      canRequestListenModeTtsForItem(
        createContentItem({
          is_speakable: true,
        }),
      ),
    ).toBe(true);
  });

  it('does not mark visual-only content as requestable without audio', () => {
    expect(
      canRequestListenModeTtsForItem(
        createContentItem({
          is_speakable: false,
          audioTracks: [],
          audio_segments: [],
        }),
      ),
    ).toBe(false);
  });

  it('keeps audio-backed content requestable for compatibility', () => {
    expect(
      canRequestListenModeTtsForItem(
        createContentItem({
          is_speakable: false,
          audioUrl: 'https://example.com/audio.mp3',
        }),
      ),
    ).toBe(true);
  });

  it('only returns ready bids for speakable content blocks', () => {
    const ready = resolveListenModeTtsReadyElementBids([
      createContentItem({
        element_bid: 'speakable-block',
        is_speakable: true,
      }),
      createLikeStatusItem('speakable-block'),
      createContentItem({
        element_bid: 'visual-only-block',
        is_speakable: false,
        audioTracks: [],
        audio_segments: [],
      }),
      createLikeStatusItem('visual-only-block'),
    ]);

    expect(ready.has('speakable-block')).toBe(true);
    expect(ready.has('visual-only-block')).toBe(false);
  });

  it('maps payload subtitle cues into normalized slide metadata', () => {
    const subtitleCues = resolveListenSlideSubtitleCues(
      createContentItem({
        payload: {
          audio: {
            subtitle_cues: [
              {
                text: '第二句',
                start_ms: 1200,
                end_ms: 1800,
                segment_index: 1,
                position: 0,
              },
              {
                text: '第一句',
                start_ms: 0,
                end_ms: 1200,
                position: 0,
              },
              {
                text: '',
                start_ms: 1800,
                end_ms: 2400,
              },
            ],
          },
        },
      }),
    );

    expect(subtitleCues).toEqual([
      {
        text: '第一句',
        start_ms: 0,
        end_ms: 1200,
        segment_index: 0,
        position: 0,
      },
      {
        text: '第二句',
        start_ms: 1200,
        end_ms: 1800,
        segment_index: 1,
        position: 0,
      },
    ]);
  });

  it('strips disallowed trailing punctuation from subtitle cues', () => {
    const subtitleCues = resolveListenSlideSubtitleCues(
      createContentItem({
        payload: {
          audio: {
            subtitle_cues: [
              {
                text: '句号结尾。',
                start_ms: 0,
                end_ms: 1000,
              },
              {
                text: '冒号结尾：',
                start_ms: 1000,
                end_ms: 2000,
              },
              {
                text: '问号保留？”',
                start_ms: 2000,
                end_ms: 3000,
              },
              {
                text: '省略号保留……',
                start_ms: 3000,
                end_ms: 4000,
              },
              {
                text: '双引号保留”',
                start_ms: 4000,
                end_ms: 5000,
              },
              {
                text: '句号后跟双引号。”',
                start_ms: 5000,
                end_ms: 6000,
              },
              {
                text: '右括号后跟句号）。',
                start_ms: 6000,
                end_ms: 7000,
              },
              {
                text: '问号双引号后再跟句号？”。',
                start_ms: 7000,
                end_ms: 8000,
              },
              {
                text: '双引号后跟逗号”，',
                start_ms: 8000,
                end_ms: 9000,
              },
            ],
          },
        },
      }),
    );

    expect(subtitleCues).toEqual([
      {
        text: '句号结尾',
        start_ms: 0,
        end_ms: 1000,
        segment_index: 0,
      },
      {
        text: '冒号结尾',
        start_ms: 1000,
        end_ms: 2000,
        segment_index: 0,
      },
      {
        text: '问号保留？”',
        start_ms: 2000,
        end_ms: 3000,
        segment_index: 0,
      },
      {
        text: '省略号保留……',
        start_ms: 3000,
        end_ms: 4000,
        segment_index: 0,
      },
      {
        text: '双引号保留”',
        start_ms: 4000,
        end_ms: 5000,
        segment_index: 0,
      },
      {
        text: '句号后跟双引号”',
        start_ms: 5000,
        end_ms: 6000,
        segment_index: 0,
      },
      {
        text: '右括号后跟句号）',
        start_ms: 6000,
        end_ms: 7000,
        segment_index: 0,
      },
      {
        text: '问号双引号后再跟句号？”',
        start_ms: 7000,
        end_ms: 8000,
        segment_index: 0,
      },
      {
        text: '双引号后跟逗号”',
        start_ms: 8000,
        end_ms: 9000,
        segment_index: 0,
      },
    ]);
  });
});
