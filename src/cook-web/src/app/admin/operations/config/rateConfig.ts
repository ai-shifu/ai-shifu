export const RATE_TABS = ['llm', 'tts'] as const;

export type RateTab = (typeof RATE_TABS)[number];

export type RateRow = {
  rate_bid?: string;
  matched_rate_provider?: string | null;
  matched_rate_model?: string | null;
  usage_type: 'llm' | 'tts' | string;
  usage_type_code: number;
  provider: string;
  model: string;
  rate_model?: string;
  display_name: string;
  usage_scene: string;
  usage_scene_code: number;
  billing_metric: string;
  billing_metric_code: number;
  unit_size: number;
  credits_per_unit: number;
  unit_cost: number;
  multiplier: number | null;
  rounding_mode: number;
  status_code: number;
  updated_at?: string | null;
  source: string;
};

export type RateBaseline = {
  default_llm_model?: string;
  unit_cost?: number;
  per_1000_output_tokens?: number;
  is_configured?: boolean;
  tts_chars_per_llm_token?: number;
};

export type RateConfigResponse = {
  baseline?: RateBaseline;
  llm_rates?: RateRow[];
  tts_rates?: RateRow[];
};

export type RateIdentity = {
  usageType: RateTab;
  provider: string;
  model: string;
  rateModel: string;
};

export type CreateRatePayload = {
  create_only: true;
  usage_type: RateTab;
  provider: string;
  model: string;
  rate_model: string;
  billing_metric: 'llm_output_tokens' | 'tts_output_chars';
  unit_size: 1;
  credits_per_unit: number;
  status: 'active';
};

const CONTROL_CHARACTER_PATTERN = /[\u0000-\u001f\u007f]/;

export const getRateRowKey = (row: RateRow) =>
  JSON.stringify([
    row.usage_type,
    row.provider,
    row.rate_model ?? row.model,
    row.billing_metric,
  ]);

export const getRateDisplayName = (row: RateRow, defaultTierLabel: string) => {
  const provider = row.provider.trim();
  const displayName = row.display_name.trim();
  const rateModel = (row.rate_model ?? row.model).trim();
  const usesProviderDefaultFallback =
    row.usage_type === 'tts' &&
    !rateModel &&
    (!displayName ||
      displayName === provider ||
      displayName === `${provider}/default`);

  if (usesProviderDefaultFallback) {
    return `${provider || displayName || '-'}/${defaultTierLabel}`;
  }
  return displayName || row.model.trim() || provider || '-';
};

export const normalizeMultiplierInput = (value: string) => {
  const normalized = value.replace(/[。．｡,，]/g, '.');
  const cleaned = normalized.replace(/[^\d.]/g, '');
  const [integerPart = '', ...decimalParts] = cleaned.split('.');
  const decimalPart = decimalParts.join('').slice(0, 2);
  if (cleaned.includes('.')) {
    return `${integerPart || '0'}.${decimalPart}`;
  }
  return integerPart;
};

export const isValidMultiplier = (value: string) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0;
};

export const canonicalizeRateIdentity = (
  usageType: RateTab,
  rawProvider: string,
  rawModel: string,
): RateIdentity => {
  const provider = rawProvider.trim();
  const modelInput = rawModel.trim();

  if (usageType === 'tts') {
    return {
      usageType,
      provider,
      model: modelInput,
      rateModel: modelInput,
    };
  }

  const providerPrefix = provider ? `${provider}/` : '';
  const rateModel =
    providerPrefix && modelInput.startsWith(providerPrefix)
      ? modelInput.slice(providerPrefix.length).trim()
      : modelInput;

  return {
    usageType,
    provider,
    model: provider && rateModel ? `${provider}/${rateModel}` : modelInput,
    rateModel,
  };
};

export const isValidProvider = (provider: string) => {
  const normalized = provider.trim();
  return (
    normalized.length > 0 &&
    normalized.length <= 32 &&
    !normalized.includes('*') &&
    !CONTROL_CHARACTER_PATTERN.test(normalized)
  );
};

export const isValidRateModel = (usageType: RateTab, rateModel: string) => {
  const normalized = rateModel.trim();
  if (!normalized) {
    return usageType === 'tts';
  }
  return (
    normalized.length <= 100 &&
    !normalized.includes('*') &&
    !CONTROL_CHARACTER_PATTERN.test(normalized)
  );
};

export const rateRowMatchesExactIdentity = (
  row: RateRow,
  identity: RateIdentity,
) => {
  const hasMatchedProvider = row.matched_rate_provider !== undefined;
  const hasMatchedModel = row.matched_rate_model !== undefined;
  if (hasMatchedProvider || hasMatchedModel) {
    return (
      hasMatchedProvider &&
      hasMatchedModel &&
      row.matched_rate_provider === identity.provider &&
      row.matched_rate_model === identity.rateModel
    );
  }

  if (row.source !== 'exact') {
    return false;
  }
  const rowIdentity = canonicalizeRateIdentity(
    identity.usageType,
    row.provider,
    row.rate_model ?? row.model,
  );
  return (
    rowIdentity.provider === identity.provider &&
    rowIdentity.rateModel === identity.rateModel
  );
};

export const hasExactRateIdentity = (rows: RateRow[], identity: RateIdentity) =>
  rows.some(row => rateRowMatchesExactIdentity(row, identity));

export const isRateRowCreateSuggestion = (row: RateRow, usageType: RateTab) => {
  const targetIdentity = canonicalizeRateIdentity(
    usageType,
    row.provider,
    row.rate_model ?? row.model,
  );
  return !rateRowMatchesExactIdentity(row, targetIdentity);
};

export const deriveCreditsPerUnit = ({
  usageType,
  multiplier,
  baseline,
}: {
  usageType: RateTab;
  multiplier: string;
  baseline?: RateBaseline;
}): number | null => {
  const multiplierValue = Number(multiplier);
  const baselineUnitCost = Number(baseline?.unit_cost || 0);
  if (
    !baseline?.is_configured ||
    !Number.isFinite(multiplierValue) ||
    multiplierValue <= 0 ||
    !Number.isFinite(baselineUnitCost) ||
    baselineUnitCost <= 0
  ) {
    return null;
  }

  let creditsPerUnit = baselineUnitCost * multiplierValue;
  if (usageType === 'tts') {
    const factor = Number(baseline.tts_chars_per_llm_token || 0);
    if (!Number.isFinite(factor) || factor <= 0) {
      return null;
    }
    creditsPerUnit /= factor;
  }

  const rounded = Number(creditsPerUnit.toFixed(10));
  return rounded > 0 ? rounded : null;
};

export const buildCreateRatePayload = ({
  identity,
  creditsPerUnit,
}: {
  identity: RateIdentity;
  creditsPerUnit: number;
}): CreateRatePayload => ({
  create_only: true,
  usage_type: identity.usageType,
  provider: identity.provider,
  model: identity.model,
  rate_model: identity.rateModel,
  billing_metric:
    identity.usageType === 'llm' ? 'llm_output_tokens' : 'tts_output_chars',
  unit_size: 1,
  credits_per_unit: creditsPerUnit,
  status: 'active',
});

export const getSuggestedRateModel = (row: RateRow) => {
  const rateModel = (row.rate_model ?? '').trim();
  if (rateModel) {
    return rateModel;
  }
  const model = row.model.trim();
  const providerPrefix = row.provider ? `${row.provider}/` : '';
  return providerPrefix && model.startsWith(providerPrefix)
    ? model.slice(providerPrefix.length)
    : model;
};
