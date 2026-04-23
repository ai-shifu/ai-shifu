import {
  type AudioItem,
  buildAudioTracksFromSegmentData,
  getAudioSegmentDataListFromTracks,
  mergeAudioSegmentDataList,
  upsertAudioComplete,
  upsertAudioSegment,
} from './audio-utils';

const progressiveSubtitleCues = [
  {
    text: '第一句',
    start_ms: 0,
    end_ms: 1200,
    segment_index: 0,
    position: 0,
  },
];

const finalSubtitleCues = [
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
    end_ms: 2400,
    segment_index: 1,
    position: 0,
  },
];

describe('audio-utils subtitle cues', () => {
  it('preserves subtitle cues when duplicate audio segments are merged', () => {
    const mergedSegments = mergeAudioSegmentDataList('content-1', [
      {
        segment_index: 0,
        audio_data: 'ZmFrZS0w',
        duration_ms: 1200,
        is_final: false,
        position: 0,
      },
      {
        segment_index: 0,
        audio_data: 'ZmFrZS0w',
        duration_ms: 1200,
        is_final: false,
        position: 0,
        subtitle_cues: progressiveSubtitleCues,
      },
    ]);

    expect(mergedSegments).toHaveLength(1);
    expect(mergedSegments[0].subtitle_cues).toEqual(progressiveSubtitleCues);
  });

  it('mirrors latest streamed subtitle cues onto rebuilt audio tracks', () => {
    const tracks = buildAudioTracksFromSegmentData([
      {
        segment_index: 0,
        audio_data: 'ZmFrZS0w',
        duration_ms: 1200,
        is_final: false,
        position: 0,
        subtitle_cues: progressiveSubtitleCues,
      },
      {
        segment_index: 1,
        audio_data: 'ZmFrZS0x',
        duration_ms: 1200,
        is_final: false,
        position: 0,
        subtitle_cues: finalSubtitleCues,
      },
    ]);

    expect(tracks).toHaveLength(1);
    expect(tracks[0].subtitleCues).toEqual(finalSubtitleCues);
    expect(tracks[0].audioSegments?.[1].subtitleCues).toEqual(
      finalSubtitleCues,
    );
  });

  it('stores final subtitle cues on complete events without dropping segments', () => {
    const initialItems: AudioItem[] = [
      {
        element_bid: 'content-1',
        audioTracks: [],
      },
    ];

    const itemsWithSegment = upsertAudioSegment(initialItems, 'content-1', {
      segment_index: 0,
      audio_data: 'ZmFrZS0w',
      duration_ms: 1200,
      is_final: false,
      position: 0,
      subtitle_cues: progressiveSubtitleCues,
    });

    const itemsWithComplete = upsertAudioComplete(
      itemsWithSegment,
      'content-1',
      {
        audio_url: 'https://example.com/audio.mp3',
        audio_bid: 'audio-1',
        duration_ms: 2400,
        position: 0,
        subtitle_cues: finalSubtitleCues,
      },
    );

    const track = itemsWithComplete[0].audioTracks?.[0];
    expect(track?.audioSegments).toHaveLength(1);
    expect(track?.audioSegments?.[0].audioData).toBe('ZmFrZS0w');
    expect(track?.subtitleCues).toEqual(finalSubtitleCues);

    const flattenedSegments = getAudioSegmentDataListFromTracks(
      itemsWithComplete[0].audioTracks ?? [],
    );
    const rebuiltTracks = buildAudioTracksFromSegmentData(flattenedSegments);

    expect(flattenedSegments[0].subtitle_cues).toEqual(finalSubtitleCues);
    expect(rebuiltTracks[0].subtitleCues).toEqual(finalSubtitleCues);
  });
});
