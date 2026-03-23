import {
  normalizeAudioItemList,
  resolveAudioItemKey,
} from '../c-utils/audio-playlist';

describe('audio-playlist element identity', () => {
  it('keeps listen tracks distinct when they share one generated block', () => {
    const items = normalizeAudioItemList([
      {
        element_bid: 'element-1::listen-audio-pos::0',
        generated_block_bid: 'generated-1',
      },
      {
        element_bid: 'element-1::listen-audio-pos::1',
        generated_block_bid: 'generated-1',
      },
    ]);

    expect(items).toHaveLength(2);
    expect(items.map(item => resolveAudioItemKey(item))).toEqual([
      'element-1::listen-audio-pos::0',
      'element-1::listen-audio-pos::1',
    ]);
  });

  it('falls back to generated block bid when no element bid is present', () => {
    const items = normalizeAudioItemList([
      {
        generated_block_bid: 'generated-1',
      },
      {
        generated_block_bid: 'generated-1',
      },
    ]);

    expect(items).toHaveLength(1);
    expect(resolveAudioItemKey(items[0])).toBe('generated-1');
  });
});
