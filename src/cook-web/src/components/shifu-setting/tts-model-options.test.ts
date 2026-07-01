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

  test('filters volcengine voices by selected resource model', () => {
    const voices = [
      { value: 'voice-1', label: 'Voice 1', resource_id: 'seed-tts-1.0' },
      { value: 'voice-2', label: 'Voice 2', resource_id: 'seed-tts-2.0' },
    ];

    expect(
      filterTtsVoicesForModel('volcengine', voices, 'seed-tts-2.0'),
    ).toEqual([voices[1]]);
    expect(filterTtsVoicesForModel('minimax', voices, 'speech-01')).toEqual(
      voices,
    );
  });
});
