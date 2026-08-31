import {
  normalizeAskProviders,
  normalizeTtsProviders,
} from './settings-config-options';

describe('settings-config-options', () => {
  it('normalizes TTS provider names while preserving provider config', () => {
    expect(
      normalizeTtsProviders([
        {
          name: 'MiniMax',
          label: 'MiniMax',
          speed: { min: 0.5, max: 2, step: 0.1, default: 1 },
          pitch: { min: -12, max: 12, step: 1, default: 0 },
          supports_emotion: true,
          supports_voice_cloning: true,
          models: [{ value: 'speech-2.8-turbo', label: 'Speech' }],
          voices: [{ value: 'voice-1', label: 'Voice 1' }],
          emotions: [{ value: 'happy', label: 'Happy' }],
        },
      ]),
    ).toEqual([
      expect.objectContaining({
        name: 'minimax',
        label: 'MiniMax',
        supports_voice_cloning: true,
        models: [{ value: 'speech-2.8-turbo', label: 'Speech' }],
      }),
    ]);
  });

  it('normalizes ask provider ids while preserving schema metadata', () => {
    expect(
      normalizeAskProviders([
        {
          provider: 'OpenAI',
          title: 'OpenAI',
          description: 'Provider description',
          default_config: { model: 'gpt-test' },
          json_schema: {
            properties: {
              model: { type: 'string', title: 'Model' },
            },
            required: ['model'],
          },
        },
      ]),
    ).toEqual([
      {
        provider: 'openai',
        title: 'OpenAI',
        description: 'Provider description',
        default_config: { model: 'gpt-test' },
        json_schema: {
          properties: {
            model: { type: 'string', title: 'Model' },
          },
          required: ['model'],
        },
      },
    ]);
  });

  it('handles missing provider lists', () => {
    expect(normalizeTtsProviders(null)).toEqual([]);
    expect(normalizeAskProviders(undefined)).toEqual([]);
  });
});
