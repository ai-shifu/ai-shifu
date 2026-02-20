import {
  hasAnyAudioPayload,
  resolveListenAudioTrack,
} from '@/c-utils/listen-mode/audio-track-resolver';

describe('listen-mode audio-track-resolver', () => {
  it('prefers per-position streaming track over persisted and legacy fields', () => {
    const resolved = resolveListenAudioTrack(
      {
        audioUrl: 'legacy-url',
        audios: [
          {
            position: 1,
            audio_url: 'persisted-url',
            duration_ms: 1000,
          },
        ],
        audioTracksByPosition: {
          1: {
            audioUrl: 'stream-url',
            audioSegments: [{ audioData: 'seg-1' }],
            isAudioStreaming: true,
            audioDurationMs: 2000,
          },
        },
      },
      1,
    );

    expect(resolved.audioUrl).toBe('stream-url');
    expect(resolved.audioSegments).toEqual([{ audioData: 'seg-1' }]);
    expect(resolved.isAudioStreaming).toBe(true);
    expect(resolved.audioDurationMs).toBe(2000);
  });

  it('falls back to persisted track by position when streaming map is absent', () => {
    const resolved = resolveListenAudioTrack(
      {
        audios: [
          {
            position: 2,
            audio_url: 'persisted-url-2',
            duration_ms: 3200,
          },
        ],
      },
      2,
    );

    expect(resolved.audioUrl).toBe('persisted-url-2');
    expect(resolved.audioDurationMs).toBe(3200);
    expect(resolved.isAudioStreaming).toBe(false);
  });

  it('uses legacy audio only for position 0', () => {
    const zeroTrack = resolveListenAudioTrack(
      {
        audioUrl: 'legacy-url',
        audioSegments: [{ audioData: 'legacy-seg' }],
        isAudioStreaming: true,
      },
      0,
    );
    const nonZeroTrack = resolveListenAudioTrack(
      {
        audioUrl: 'legacy-url',
        audioSegments: [{ audioData: 'legacy-seg' }],
        isAudioStreaming: true,
      },
      1,
    );

    expect(zeroTrack.audioUrl).toBe('legacy-url');
    expect(zeroTrack.audioSegments).toEqual([{ audioData: 'legacy-seg' }]);
    expect(zeroTrack.isAudioStreaming).toBe(true);

    expect(nonZeroTrack.audioUrl).toBeUndefined();
    expect(nonZeroTrack.audioSegments).toBeUndefined();
    expect(nonZeroTrack.isAudioStreaming).toBe(false);
  });

  it('detects audio payload from av contract speakable segments', () => {
    expect(
      hasAnyAudioPayload({
        avContract: {
          speakable_segments: [{ position: 0 }],
        },
      }),
    ).toBe(true);

    expect(
      hasAnyAudioPayload({
        avContract: {
          speakable_segments: [],
        },
      }),
    ).toBe(false);
  });
});
