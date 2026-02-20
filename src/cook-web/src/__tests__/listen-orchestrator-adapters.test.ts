import {
  LISTEN_AUDIO_EVENT_TYPES,
  buildListenUnitId,
  normalizeListenRecordAudios,
  normalizeListenAudioPosition,
  toListenInboundAudioEvent,
} from '@/c-utils/listen-orchestrator';

describe('listen-orchestrator adapters', () => {
  it('normalizes invalid positions to 0', () => {
    expect(normalizeListenAudioPosition(undefined)).toBe(0);
    expect(normalizeListenAudioPosition('abc')).toBe(0);
    expect(normalizeListenAudioPosition(-1)).toBe(0);
    expect(normalizeListenAudioPosition(2.7)).toBe(2);
  });

  it('builds stable content unit id with resolved bid and position', () => {
    const unitId = buildListenUnitId({
      type: 'content',
      generatedBlockBid: 'raw-bid',
      position: 3,
      fallbackIndex: 9,
      resolveContentBid: () => 'resolved-bid',
    });
    expect(unitId).toBe('content:resolved-bid:3');
  });

  it('builds interaction unit id with fallback index', () => {
    const unitId = buildListenUnitId({
      type: 'interaction',
      generatedBlockBid: '',
      fallbackIndex: 5,
    });
    expect(unitId).toBe('interaction:5');
  });

  it('parses inbound audio_segment event', () => {
    const event = toListenInboundAudioEvent({
      type: LISTEN_AUDIO_EVENT_TYPES.AUDIO_SEGMENT,
      generated_block_bid: 'block-1',
      content: {
        position: 2,
        segment_index: 0,
        audio_data: 'base64',
      },
    });

    expect(event).toEqual({
      type: LISTEN_AUDIO_EVENT_TYPES.AUDIO_SEGMENT,
      generatedBlockBid: 'block-1',
      position: 2,
      payload: {
        position: 2,
        segment_index: 0,
        audio_data: 'base64',
      },
    });
  });

  it('uses fallback generatedBlockBid when event omits it', () => {
    const event = toListenInboundAudioEvent(
      {
        type: LISTEN_AUDIO_EVENT_TYPES.AUDIO_COMPLETE,
        content: {
          position: 1,
          audio_url: 'https://example.com/a.mp3',
          audio_bid: 'audio-1',
          duration_ms: 1234,
        },
      },
      'fallback-bid',
    );

    expect(event?.generatedBlockBid).toBe('fallback-bid');
    expect(event?.position).toBe(1);
    expect(event?.type).toBe(LISTEN_AUDIO_EVENT_TYPES.AUDIO_COMPLETE);
  });

  it('returns null for non-audio events or missing block id', () => {
    expect(toListenInboundAudioEvent({ type: 'content' })).toBeNull();
    expect(
      toListenInboundAudioEvent({
        type: LISTEN_AUDIO_EVENT_TYPES.AUDIO_COMPLETE,
        content: { position: 0 },
      }),
    ).toBeNull();
  });

  it('normalizes record audios and builds tracks by position', () => {
    const normalized = normalizeListenRecordAudios({
      audios: [
        {
          position: 1,
          audio_url: 'https://example.com/a1.mp3',
          audio_bid: 'a1',
          duration_ms: 1001,
        },
        {
          position: 0,
          audio_url: 'https://example.com/a0.mp3',
          audio_bid: 'a0',
          duration_ms: 1000,
        },
      ],
    });

    expect(normalized.audios).toEqual([
      {
        position: 0,
        audio_url: 'https://example.com/a0.mp3',
        audio_bid: 'a0',
        duration_ms: 1000,
      },
      {
        position: 1,
        audio_url: 'https://example.com/a1.mp3',
        audio_bid: 'a1',
        duration_ms: 1001,
      },
    ]);
    expect(normalized.audioTracksByPosition?.[0]).toEqual({
      audioUrl: 'https://example.com/a0.mp3',
      audioDurationMs: 1000,
      audioBid: 'a0',
      isAudioStreaming: false,
    });
    expect(normalized.audioTracksByPosition?.[1]).toEqual({
      audioUrl: 'https://example.com/a1.mp3',
      audioDurationMs: 1001,
      audioBid: 'a1',
      isAudioStreaming: false,
    });
  });

  it('projects legacy audio_url to position 0 when audios missing', () => {
    const normalized = normalizeListenRecordAudios({
      audioUrl: 'https://example.com/legacy.mp3',
      audios: [],
    });

    expect(normalized.audios).toEqual([
      {
        position: 0,
        audio_url: 'https://example.com/legacy.mp3',
      },
    ]);
    expect(normalized.audioTracksByPosition?.[0]).toEqual({
      audioUrl: 'https://example.com/legacy.mp3',
      audioDurationMs: undefined,
      audioBid: undefined,
      isAudioStreaming: false,
    });
  });
});
