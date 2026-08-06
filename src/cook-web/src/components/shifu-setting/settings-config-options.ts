import type { AskProviderJsonSchema } from './ask-provider-schema';

export interface AskProviderConfigItem {
  provider: string;
  title: string;
  description?: string;
  default_config?: Record<string, unknown>;
  json_schema?: AskProviderJsonSchema;
}

export interface AskConfigMetadata {
  feature_enabled?: boolean;
  default?: {
    provider?: string;
    mode?: string;
    config?: Record<string, unknown>;
  };
  modes?: Array<{ value: string; title: string }>;
  providers?: AskProviderConfigItem[];
}

export interface TTSProviderConfig {
  name: string;
  label: string;
  speed: { min: number; max: number; step: number; default: number };
  pitch: { min: number; max: number; step: number; default: number };
  supports_emotion: boolean;
  supports_custom_voice_id?: boolean;
  supports_voice_cloning?: boolean;
  models: { value: string; label: string }[];
  voices: { value: string; label: string; resource_id?: string }[];
  emotions: { value: string; label: string }[];
}

export const normalizeTtsProviders = (
  providers?: TTSProviderConfig[] | null,
): TTSProviderConfig[] =>
  (providers ?? []).map(provider => ({
    ...provider,
    name: (provider.name || '').toLowerCase(),
  }));

export const normalizeAskProviders = (
  providers?: AskProviderConfigItem[] | null,
): AskProviderConfigItem[] =>
  (providers ?? []).map(provider => ({
    ...provider,
    provider: (provider.provider || '').toLowerCase(),
  }));
