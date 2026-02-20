import { shouldPreferOssUrl } from '@/components/audio/AudioPlayer';

describe('AudioPlayer routing strategy', () => {
  it('prefers segmented playback when segments already exist', () => {
    expect(
      shouldPreferOssUrl({
        audioUrl: 'https://example.com/final.mp3',
        isStreaming: false,
        segmentCount: 3,
      }),
    ).toBe(false);
  });

  it('uses final URL when there are no segments and streaming is complete', () => {
    expect(
      shouldPreferOssUrl({
        audioUrl: 'https://example.com/final.mp3',
        isStreaming: false,
        segmentCount: 0,
      }),
    ).toBe(true);
  });

  it('does not use final URL while streaming is in progress', () => {
    expect(
      shouldPreferOssUrl({
        audioUrl: 'https://example.com/final.mp3',
        isStreaming: true,
        segmentCount: 0,
      }),
    ).toBe(false);
  });
});
