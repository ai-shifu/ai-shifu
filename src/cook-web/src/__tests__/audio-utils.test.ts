import {
  mergeAudioCompleteIntoTracks,
  mergeAudioSegmentsIntoTracks,
} from '../c-utils/audio-utils';

describe('audio-utils embedded segment compatibility', () => {
  it('merges incremental element audio segments into one track', () => {
    const afterFirstSegment = mergeAudioSegmentsIntoTracks(
      'element-1',
      [],
      [
        {
          segment_index: 0,
          audio_data: 'segment-0',
          duration_ms: 120,
          is_final: false,
          position: 0,
        },
      ],
    );

    const afterSecondSegment = mergeAudioSegmentsIntoTracks(
      'element-1',
      afterFirstSegment,
      [
        {
          segment_index: 1,
          audio_data: 'segment-1',
          duration_ms: 160,
          is_final: false,
          position: 0,
        },
      ],
    );

    expect(afterSecondSegment).toHaveLength(1);
    expect(afterSecondSegment[0].position).toBe(0);
    expect(
      afterSecondSegment[0].audioSegments?.map(item => item.segmentIndex),
    ).toEqual([0, 1]);
    expect(afterSecondSegment[0].isAudioStreaming).toBe(true);
  });

  it('deduplicates repeated element audio segments and keeps complete audio url', () => {
    const withDuplicateSegments = mergeAudioSegmentsIntoTracks(
      'element-2',
      [],
      [
        {
          segment_index: 0,
          audio_data: 'segment-0',
          duration_ms: 180,
          is_final: false,
          position: 0,
        },
        {
          segment_index: 0,
          audio_data: 'segment-0',
          duration_ms: 180,
          is_final: false,
          position: 0,
        },
      ],
    );

    const completedTracks = mergeAudioCompleteIntoTracks(
      withDuplicateSegments,
      {
        audio_url: 'https://example.com/audio.mp3',
        duration_ms: 180,
        position: 0,
      },
    );

    expect(completedTracks).toHaveLength(1);
    expect(completedTracks[0].audioSegments).toHaveLength(1);
    expect(completedTracks[0].audioUrl).toBe('https://example.com/audio.mp3');
    expect(completedTracks[0].isAudioStreaming).toBe(false);
  });
});
