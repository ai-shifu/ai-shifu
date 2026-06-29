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

  const [rawProvider = '', rawModel = ''] = String(value || '').split('/');
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
      return {
        value,
        label,
        provider,
        model,
        credit_multiplier_label:
          item.credit_multiplier_label || item.creditMultiplierLabel || '',
      };
    })
    .filter((item): item is TtsModelOption => Boolean(item));
};

export const filterTtsVoicesForModel = (
  provider: string,
  voices: TtsVoiceOption[],
  model: string,
): TtsVoiceOption[] => {
  if (
    String(provider || '')
      .trim()
      .toLowerCase() !== 'volcengine'
  ) {
    return voices;
  }
  const modelKey = String(model || '').trim();
  if (!modelKey) return voices;
  return voices.filter(voice => (voice.resource_id || '').trim() === modelKey);
};
