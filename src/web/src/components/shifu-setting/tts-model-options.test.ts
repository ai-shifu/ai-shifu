import {
  buildTtsModelOptionValue,
  filterTtsVoicesForModel,
  getDefaultTtsModelOption,
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

  test('normalizes the backend is_default marker', () => {
    const options = normalizeTtsModelOptions([
      {
        value: 'tencent_texttovoice/premium',
        label: 'Basic Voice',
        provider: 'tencent_texttovoice',
        model: 'premium',
        is_default: false,
      },
      {
        value: 'tencent_texttovoice/large-model',
        label: 'Standard Voice',
        provider: 'tencent_texttovoice',
        model: 'large-model',
        is_default: true,
      },
    ]);

    expect(options.map(option => option.isDefault)).toEqual([false, true]);
  });

  test('selects the default option with first-option fallback', () => {
    const options = normalizeTtsModelOptions([
      {
        value: 'tencent_texttovoice/premium',
        label: 'Basic Voice',
        provider: 'tencent_texttovoice',
        model: 'premium',
      },
      {
        value: 'tencent_texttovoice/large-model',
        label: 'Standard Voice',
        provider: 'tencent_texttovoice',
        model: 'large-model',
        is_default: true,
      },
    ]);

    // The declared default wins even when it is not the first option, so the
    // dropdown order stays untouched.
    expect(getDefaultTtsModelOption(options)?.value).toBe(
      'tencent_texttovoice/large-model',
    );

    // Without a declared default (older backend payloads), fall back to the
    // first option to preserve the legacy behavior.
    const legacyOptions = normalizeTtsModelOptions([
      {
        value: 'tencent_texttovoice/premium',
        label: 'Basic Voice',
        provider: 'tencent_texttovoice',
        model: 'premium',
      },
      {
        value: 'minimax/speech-2.8-turbo',
        label: 'Premium Voice',
        provider: 'minimax',
        model: 'speech-2.8-turbo',
      },
    ]);
    expect(getDefaultTtsModelOption(legacyOptions)?.value).toBe(
      'tencent_texttovoice/premium',
    );

    expect(getDefaultTtsModelOption([])).toBeUndefined();
  });
});
