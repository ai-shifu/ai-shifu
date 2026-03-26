import type { ChatContentItem } from './useChatLogicHook';
import {
  canRequestListenModeTtsForItem,
  resolveListenSlideAudioSource,
  resolveListenModeTtsReadyElementBids,
} from './listenModeUtils';

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
  type: 'likeStatus',
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

  it('prefers track-backed audio source when tracks and legacy fields coexist', () => {
    const resolved = resolveListenSlideAudioSource(
      createContentItem({
        element_bid: 'track-priority-block',
        audio_url: 'https://legacy.example.com/audio.mp3',
        audio_segments: [
          {
            segment_index: 0,
            audio_data: 'legacy-segment',
            duration_ms: 1000,
            is_final: true,
            position: 0,
          },
        ],
        audioTracks: [
          {
            position: 0,
            audioUrl: 'https://track.example.com/audio.mp3',
            isAudioStreaming: false,
            audioSegments: [
              {
                segmentIndex: 0,
                audioData: 'track-segment',
                durationMs: 1000,
                isFinal: true,
                position: 0,
              },
            ],
          },
        ],
      }),
    );

    expect(resolved.audioUrl).toBe('https://track.example.com/audio.mp3');
    expect(resolved.audioSegments?.length).toBe(1);
    expect(resolved.audioSegments?.[0]?.audio_data).toBe('track-segment');
  });

  it('falls back to legacy audio source when tracks have no playable payload', () => {
    const resolved = resolveListenSlideAudioSource(
      createContentItem({
        element_bid: 'legacy-fallback-block',
        audio_url: 'https://legacy.example.com/audio.mp3',
        audio_segments: [
          {
            segment_index: 0,
            audio_data: 'legacy-segment',
            duration_ms: 800,
            is_final: true,
            position: 0,
          },
        ],
        audioTracks: [
          {
            position: 0,
            isAudioStreaming: false,
            audioSegments: [],
          },
        ],
      }),
    );

    expect(resolved.audioUrl).toBe('https://legacy.example.com/audio.mp3');
    expect(resolved.audioSegments?.length).toBe(1);
    expect(resolved.audioSegments?.[0]?.audio_data).toBe('legacy-segment');
  });
});
