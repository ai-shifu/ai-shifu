import {
  ASK_PROVIDER_LLM,
  ASK_PROVIDER_MODE_PROVIDER_ONLY,
  buildAskProviderSubmitConfig,
  getAskProviderDefaultConfig,
  getAskProviderMeta,
  normalizeAskProviderId,
  normalizeStoredAskProviderConfig,
  resolveAskProvider,
  resolveAskProviderSelection,
} from './ask-provider-config';
import type { AskConfigMetadata } from './settings-config-options';

const metadata: AskConfigMetadata = {
  default: { provider: 'openai', mode: 'provider_only', config: {} },
  providers: [
    {
      provider: 'openai',
      title: 'OpenAI',
      default_config: { model: 'gpt-test' },
    },
    {
      provider: 'qwen',
      title: 'Qwen',
      default_config: { model: 'qwen-test', temperature: 0.4 },
    },
  ],
};

describe('ask provider config helpers', () => {
  it('normalizes provider ids with trim and lowercase', () => {
    expect(normalizeAskProviderId(' QWEN ')).toBe('qwen');
  });

  it('uses the first provider when selected provider is missing or unknown', () => {
    expect(resolveAskProvider(metadata, '')).toBe('openai');
    expect(resolveAskProvider(metadata, 'missing')).toBe('openai');
  });

  it('keeps selected providers that exist in metadata', () => {
    expect(resolveAskProvider(metadata, 'QWEN')).toBe('qwen');
    expect(getAskProviderMeta(metadata, 'qwen')?.title).toBe('Qwen');
  });

  it('falls back to llm when provider metadata is unavailable', () => {
    expect(resolveAskProvider(null, '')).toBe(ASK_PROVIDER_LLM);
    expect(resolveAskProvider(null, 'custom')).toBe('custom');
  });

  it('returns a copy of provider default config', () => {
    const config = getAskProviderDefaultConfig(metadata, 'qwen');
    config.model = 'changed';

    expect(getAskProviderDefaultConfig(metadata, 'qwen')).toEqual({
      model: 'qwen-test',
      temperature: 0.4,
    });
  });

  it('normalizes stored config while preserving provider inner config', () => {
    expect(
      normalizeStoredAskProviderConfig({
        provider: ' QWEN ',
        mode: 'custom_mode',
        config: { model: 'qwen-test' },
      }),
    ).toEqual({
      provider: 'qwen',
      mode: 'custom_mode',
      config: { model: 'qwen-test' },
    });
  });

  it('falls back stored malformed config to existing defaults', () => {
    expect(normalizeStoredAskProviderConfig(null)).toEqual({
      provider: ASK_PROVIDER_LLM,
      mode: ASK_PROVIDER_MODE_PROVIDER_ONLY,
      config: {},
    });
  });

  it('returns fallback selection with default config for unknown providers', () => {
    expect(resolveAskProviderSelection(metadata, 'missing')).toEqual({
      provider: 'openai',
      config: { model: 'gpt-test' },
      changed: true,
    });
  });

  it('builds submit config with the fixed existing provider-only mode', () => {
    expect(
      buildAskProviderSubmitConfig({
        metadata,
        provider: 'qwen',
        config: { model: 'qwen-test' },
      }),
    ).toEqual({
      provider: 'qwen',
      mode: ASK_PROVIDER_MODE_PROVIDER_ONLY,
      config: { model: 'qwen-test' },
    });
  });
});
