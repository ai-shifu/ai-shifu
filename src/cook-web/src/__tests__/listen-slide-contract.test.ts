import {
  buildListenUnitId,
  normalizeListenRecordAudios,
  toListenInboundAudioEvent,
} from '@/c-utils/listen-orchestrator';

describe('listen slide contract adapters', () => {
  it('parses slide_id from inbound audio SSE payload', () => {
    const inbound = toListenInboundAudioEvent(
      {
        type: 'audio_complete',
        generated_block_bid: 'block-1',
        content: {
          position: 2,
          slide_id: 'slide-2',
          audio_url: 'https://example.com/a.mp3',
          audio_bid: 'audio-2',
          duration_ms: 1234,
        },
      },
      'fallback-bid',
    );

    expect(inbound).not.toBeNull();
    expect(inbound?.generatedBlockBid).toBe('block-1');
    expect(inbound?.position).toBe(2);
    expect(inbound?.slideId).toBe('slide-2');
  });

  it('hydrates audioSlideIdByPosition from records audios', () => {
    const normalized = normalizeListenRecordAudios({
      audios: [
        {
          position: 1,
          slide_id: 'slide-1',
          audio_url: 'https://example.com/1.mp3',
          audio_bid: 'audio-1',
          duration_ms: 100,
        },
        {
          position: 0,
          slide_id: 'slide-0',
          audio_url: 'https://example.com/0.mp3',
          audio_bid: 'audio-0',
          duration_ms: 90,
        },
      ],
    });

    expect(normalized.audios?.map(audio => audio.position)).toEqual([0, 1]);
    expect(normalized.audioSlideIdByPosition).toEqual({
      0: 'slide-0',
      1: 'slide-1',
    });
  });

  it('keeps legacy position fallback when slide_id is missing', () => {
    const inbound = toListenInboundAudioEvent(
      {
        type: 'audio_segment',
        generated_block_bid: 'block-legacy',
        content: {
          position: 3,
          segment_index: 0,
          audio_data: 'ZmFrZQ==',
          duration_ms: 80,
          is_final: false,
        },
      },
      '',
    );

    expect(inbound).not.toBeNull();
    expect(inbound?.generatedBlockBid).toBe('block-legacy');
    expect(inbound?.position).toBe(3);
    expect(inbound?.slideId).toBeUndefined();
  });

  it('uses stable bid:position format for content positions', () => {
    const first = buildListenUnitId({
      type: 'content',
      generatedBlockBid: 'block-1',
      position: 0,
      fallbackIndex: 0,
    });
    const second = buildListenUnitId({
      type: 'content',
      generatedBlockBid: 'block-1',
      position: 1,
      fallbackIndex: 1,
    });

    // Keep unit IDs stable across list rebuilds even when slide metadata
    // arrives asynchronously via avContract.
    expect(first).toBe('content:block-1:0');
    expect(second).toBe('content:block-1:1');
    expect(first).not.toBe(second);
  });
});
