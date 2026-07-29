import {
  buildTtsModelOptionValue,
  filterTtsVoicesForModel,
  normalizeTtsModelOptions,
  parseTtsModelOptionValue,
} from './tts-model-options';

describe('tts-model-options', () => {
  test('builds and parses provider/model values', () => {
    const options = normalizeTtsModelOptions([
      {
        value: 'minimax/speech-01-turbo',
        label: 'MiniMax Turbo',
        provider: 'MiniMax',
        model: 'speech-01-turbo',
        credit_multiplier_label: '2x',
      },
      {
        value: 'baidu/default',
        label: 'Baidu',
        provider: 'baidu',
        model: '',
      },
    ]);

    expect(buildTtsModelOptionValue('minimax', 'speech-01-turbo')).toBe(
      'minimax/speech-01-turbo',
    );
    expect(buildTtsModelOptionValue('baidu', '')).toBe('baidu/default');
    expect(parseTtsModelOptionValue('baidu/default', options)).toEqual({
      provider: 'baidu',
      model: '',
    });
    expect(options[0].creditMultiplierLabel).toBe('2x');
  });

  test('parses fallback values by splitting on the first slash only', () => {
    // A stale selection missing from options must round-trip without losing
    // slashes in the model portion (matches backend split('/', 1)).
    expect(parseTtsModelOptionValue('volcengine/seed/tts/2.0', [])).toEqual({
      provider: 'volcengine',
      model: 'seed/tts/2.0',
    });
    expect(parseTtsModelOptionValue('minimax/default', [])).toEqual({
      provider: 'minimax',
      model: '',
    });
    expect(parseTtsModelOptionValue('minimax', [])).toEqual({
      provider: 'minimax',
      model: '',
    });
  });

  test('filters resource-annotated voices by selected model', () => {
    const annotatedVoices = [
      { value: 'voice-1', label: 'Voice 1', resource_id: 'seed-tts-1.0' },
      { value: 'voice-2', label: 'Voice 2', resource_id: 'seed-tts-2.0' },
    ];
    const tencentVoices = [
      { value: '101001', label: '智瑜', resource_id: 'premium' },
      { value: '501001', label: '智兰', resource_id: 'large-model' },
    ];
    const plainVoices = [
      { value: 'voice-a', label: 'Voice A' },
      { value: 'voice-b', label: 'Voice B' },
    ];

    expect(filterTtsVoicesForModel(annotatedVoices, 'seed-tts-2.0')).toEqual([
      annotatedVoices[1],
    ]);
    expect(filterTtsVoicesForModel(tencentVoices, 'premium')).toEqual([
      tencentVoices[0],
    ]);
    // Voices without resource annotations are returned unchanged.
    expect(filterTtsVoicesForModel(plainVoices, 'speech-01')).toEqual(
      plainVoices,
    );
    // An empty model keeps the full list.
    expect(filterTtsVoicesForModel(annotatedVoices, '')).toEqual(
      annotatedVoices,
    );
  });
});
