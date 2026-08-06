import type {
  AskConfigMetadata,
  AskProviderConfigItem,
} from './settings-config-options';

export const ASK_PROVIDER_LLM = 'llm';
export const ASK_PROVIDER_MODE_PROVIDER_ONLY = 'provider_only';

export type StoredAskProviderConfig = {
  provider?: string;
  mode?: string;
  config?: Record<string, unknown>;
};

export type AskProviderSubmitConfig = {
  provider: string;
  mode: string;
  config: Record<string, unknown>;
};

export const normalizeAskProviderId = (provider?: string | null) =>
  String(provider || '')
    .trim()
    .toLowerCase();

const clonePlainConfig = (config: unknown): Record<string, unknown> =>
  config && typeof config === 'object' && !Array.isArray(config)
    ? { ...(config as Record<string, unknown>) }
    : {};

export const resolveAskProvider = (
  metadata?: AskConfigMetadata | null,
  provider?: string | null,
  fallbackProvider = ASK_PROVIDER_LLM,
): string => {
  const normalizedProvider = normalizeAskProviderId(provider);
  const providers = metadata?.providers || [];

  if (!normalizedProvider) {
    return providers[0]?.provider || fallbackProvider;
  }

  if (providers.length) {
    const exists = providers.some(item => item.provider === normalizedProvider);
    return exists
      ? normalizedProvider
      : providers[0]?.provider || normalizedProvider;
  }

  return normalizedProvider;
};

export const getAskProviderMeta = (
  metadata?: AskConfigMetadata | null,
  provider?: string | null,
): AskProviderConfigItem | undefined => {
  const resolvedProvider = resolveAskProvider(metadata, provider);
  return (
    metadata?.providers?.find(item => item.provider === resolvedProvider) ||
    metadata?.providers?.[0]
  );
};

export const getAskProviderDefaultConfig = (
  metadata?: AskConfigMetadata | null,
  provider?: string | null,
): Record<string, unknown> => {
  const resolvedProvider = normalizeAskProviderId(provider);
  const providerMeta = metadata?.providers?.find(
    item => item.provider === resolvedProvider,
  );
  return clonePlainConfig(providerMeta?.default_config);
};

export const normalizeStoredAskProviderConfig = (
  rawConfig: unknown,
): Required<StoredAskProviderConfig> => {
  const configObject = clonePlainConfig(rawConfig);
  return {
    provider: normalizeAskProviderId(
      typeof configObject.provider === 'string'
        ? configObject.provider
        : ASK_PROVIDER_LLM,
    ),
    mode:
      typeof configObject.mode === 'string' && configObject.mode.trim()
        ? configObject.mode.trim()
        : ASK_PROVIDER_MODE_PROVIDER_ONLY,
    config: clonePlainConfig(configObject.config),
  };
};

export const resolveAskProviderSelection = (
  metadata?: AskConfigMetadata | null,
  provider?: string | null,
): { provider: string; config: Record<string, unknown>; changed: boolean } => {
  const normalizedProvider = normalizeAskProviderId(provider);
  const providers = metadata?.providers || [];

  if (!providers.length) {
    return {
      provider: normalizedProvider || ASK_PROVIDER_LLM,
      config: {},
      changed: false,
    };
  }

  const matched = providers.some(item => item.provider === normalizedProvider);
  const nextProvider = matched ? normalizedProvider : providers[0].provider;

  return {
    provider: nextProvider,
    config: getAskProviderDefaultConfig(metadata, nextProvider),
    changed: !matched,
  };
};

export const buildAskProviderSubmitConfig = ({
  metadata,
  provider,
  config,
}: {
  metadata?: AskConfigMetadata | null;
  provider?: string | null;
  config: Record<string, unknown>;
}): AskProviderSubmitConfig => ({
  provider:
    resolveAskProvider(metadata, provider) ||
    metadata?.default?.provider ||
    ASK_PROVIDER_LLM,
  mode: ASK_PROVIDER_MODE_PROVIDER_ONLY,
  config,
});
