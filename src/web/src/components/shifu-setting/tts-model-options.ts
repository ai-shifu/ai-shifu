import type { ModelOption } from '@/types/shifu';

export const TTS_DEFAULT_MODEL_TOKEN = 'default';

export interface TtsModelOption extends ModelOption {
  provider: string;
  model: string;
}

export interface TtsVoiceOption {
  value: string;
  label: string;
  resource_id?: string;
}

export const buildTtsModelOptionValue = (
  provider: string,
  model: string,
): string => {
  const normalizedProvider = String(provider || '')
    .trim()
    .toLowerCase();
  if (!normalizedProvider) return '';
  const modelKey = String(model || '').trim() || TTS_DEFAULT_MODEL_TOKEN;
  return `${normalizedProvider}/${modelKey}`;
};

export const parseTtsModelOptionValue = (
  value: string,
  options: TtsModelOption[],
): { provider: string; model: string } => {
  const selected = options.find(option => option.value === value);
  if (selected) {
    return {
      provider: selected.provider,
      model: selected.model,
    };
  }

  // Split on the first slash only so model ids containing slashes survive,
  // matching the backend `split('/', 1)` normalization.
  const normalizedValue = String(value || '').trim();
  const separatorIndex = normalizedValue.indexOf('/');
  const rawProvider =
    separatorIndex >= 0
      ? normalizedValue.slice(0, separatorIndex)
      : normalizedValue;
  const rawModel =
    separatorIndex >= 0 ? normalizedValue.slice(separatorIndex + 1) : '';
  const provider = rawProvider.trim().toLowerCase();
  const model = rawModel.trim();
  return {
    provider,
    model: model === TTS_DEFAULT_MODEL_TOKEN ? '' : model,
  };
};

export const normalizeTtsModelOptions = (list: any): TtsModelOption[] => {
  if (!Array.isArray(list)) return [];
  return list
    .map((item): TtsModelOption | null => {
      if (!item || typeof item !== 'object') return null;
      const provider = String(item.provider || '')
        .trim()
        .toLowerCase();
      const model = String(item.model || '').trim();
      const value =
        String(item.value || '').trim() ||
        buildTtsModelOptionValue(provider, model);
      const label = String(item.label || value).trim() || value;
      if (!provider || !value) return null;
      const rawMultiplier = item.credit_multiplier ?? item.creditMultiplier;
      const parsedMultiplier = Number(rawMultiplier);
      const creditMultiplier =
        Number.isFinite(parsedMultiplier) && parsedMultiplier > 0
          ? Math.ceil(parsedMultiplier)
          : null;
      const creditMultiplierLabel = String(
        item.credit_multiplier_label || item.creditMultiplierLabel || '',
      ).trim();
      return {
        value,
        label,
        provider,
        model,
        creditMultiplier,
        creditMultiplierLabel,
        isDefault: Boolean(item.is_default ?? item.isDefault),
      };
    })
    .filter((item): item is TtsModelOption => Boolean(item));
};

export const getDefaultTtsModelOption = (
  options: TtsModelOption[],
): TtsModelOption | undefined =>
  options.find(option => option.isDefault) || options[0];

export const filterTtsVoicesForModel = (
  voices: TtsVoiceOption[],
  model: string,
): TtsVoiceOption[] => {
  const modelKey = String(model || '').trim();
  if (!modelKey) return voices;
  // Providers whose voices declare a resource_id (volcengine resources,
  // tencent TextToVoice tiers) get model-scoped voice lists; providers
  // without the annotation keep their full list.
  const hasResourceAnnotations = voices.some(voice =>
    (voice.resource_id || '').trim(),
  );
  if (!hasResourceAnnotations) return voices;
  return voices.filter(voice => (voice.resource_id || '').trim() === modelKey);
};
