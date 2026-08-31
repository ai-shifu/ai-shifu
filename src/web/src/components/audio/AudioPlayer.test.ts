import { shouldFallbackToCompleteUrlForWaitingStream } from './AudioPlayer';

describe('shouldFallbackToCompleteUrlForWaitingStream', () => {
  it('does not use the complete URL after stream segments have been consumed', () => {
    expect(
      shouldFallbackToCompleteUrlForWaitingStream({
        audioUrl: 'https://example.com/final.mp3',
        streamingSegmentCount: 1,
        currentSegmentIndex: 1,
        playedSeconds: 1,
      }),
    ).toBe(false);
  });

  it('uses the complete URL when a stream finishes without segments', () => {
    expect(
      shouldFallbackToCompleteUrlForWaitingStream({
        audioUrl: 'https://example.com/cached.mp3',
        streamingSegmentCount: 0,
        currentSegmentIndex: 0,
        playedSeconds: 0,
      }),
    ).toBe(true);
  });

  it('does not use the complete URL when none is available', () => {
    expect(
      shouldFallbackToCompleteUrlForWaitingStream({
        audioUrl: undefined,
        streamingSegmentCount: 0,
        currentSegmentIndex: 0,
        playedSeconds: 0,
      }),
    ).toBe(false);
  });
});
