export const MINIMAX_PROVIDER = 'minimax';
export const VOLCENGINE_PROVIDER = 'volcengine';

const CLONED_VOICE_PROVIDERS = new Set([MINIMAX_PROVIDER, VOLCENGINE_PROVIDER]);

export type ClonedVoiceStatus =
  | 'queued'
  | 'processing'
  | 'billing_pending'
  | 'failed'
  | 'ready';

export interface TTSVoiceOptionBase {
  value: string;
  label: string;
  resource_id?: string;
}

export interface RegisteredClonedVoice {
  voice_bid: string;
  voice_id: string;
  display_name: string;
  provider?: string;
  status: ClonedVoiceStatus | string;
}

export interface TTSVoiceOption extends TTSVoiceOptionBase {
  source: 'built_in' | 'cloned' | 'manual';
  status?: string;
  voice_bid?: string;
  disabled?: boolean;
}

const MINIMAX_CUSTOM_VOICE_ID_PATTERN =
  /^[A-Za-z](?=.{7,63}$)[A-Za-z0-9_-]*[A-Za-z0-9]$/;
const VOLCENGINE_CUSTOM_VOICE_ID_PATTERN = /^S_[A-Za-z0-9_-]{4,64}$/;

export function isMiniMaxProvider(providerName: string): boolean {
  return (providerName || '').trim().toLowerCase() === MINIMAX_PROVIDER;
}

export function providerSupportsClonedVoices(providerName: string): boolean {
  return CLONED_VOICE_PROVIDERS.has((providerName || '').trim().toLowerCase());
}

export function isValidMiniMaxCustomVoiceId(voiceId: string): boolean {
  return MINIMAX_CUSTOM_VOICE_ID_PATTERN.test((voiceId || '').trim());
}

export function isValidVolcengineCustomVoiceId(voiceId: string): boolean {
  return VOLCENGINE_CUSTOM_VOICE_ID_PATTERN.test((voiceId || '').trim());
}

export function getCustomVoiceIdValidator(
  providerName: string,
): (voiceId: string) => boolean {
  return (providerName || '').trim().toLowerCase() === VOLCENGINE_PROVIDER
    ? isValidVolcengineCustomVoiceId
    : isValidMiniMaxCustomVoiceId;
}

export function buildClonedVoiceListParams(
  providerName: string,
  shifuId?: string,
): Record<string, string> {
  // Operator-registered rows have no shifu_bid, so filter only by provider.
  void shifuId;
  const provider = (providerName || '').trim().toLowerCase();
  return provider ? { provider } : {};
}

export function shouldPreserveCustomMiniMaxVoice({
  providerName,
  supportsCustomVoiceId,
  voiceId,
  builtInVoices,
}: {
  providerName: string;
  supportsCustomVoiceId?: boolean;
  voiceId: string;
  builtInVoices: TTSVoiceOptionBase[];
}): boolean {
  const normalizedVoiceId = (voiceId || '').trim();
  if (
    !normalizedVoiceId ||
    !isMiniMaxProvider(providerName) ||
    !supportsCustomVoiceId
  ) {
    return false;
  }
  if (builtInVoices.some(voice => voice.value === normalizedVoiceId)) {
    return false;
  }
  return isValidMiniMaxCustomVoiceId(normalizedVoiceId);
}

export function buildMiniMaxVoiceOptions({
  builtInVoices,
  clonedVoices,
  currentVoiceId,
  clonedVoiceLabelFormatter,
  manualLabel,
  statusLabels = {},
  manualVoiceValidator = isValidMiniMaxCustomVoiceId,
}: {
  builtInVoices: TTSVoiceOptionBase[];
  clonedVoices: RegisteredClonedVoice[];
  currentVoiceId: string;
  clonedVoiceLabelFormatter?: (name: string) => string;
  manualLabel: string;
  statusLabels?: Record<string, string>;
  manualVoiceValidator?: (voiceId: string) => boolean;
}): TTSVoiceOption[] {
  const seen = new Set<string>();
  const builtInVoiceIds = new Set(
    (builtInVoices || [])
      .map(voice => (voice.value || '').trim())
      .filter(Boolean),
  );
  const options: TTSVoiceOption[] = [];

  for (const voice of clonedVoices || []) {
    const value = (voice.voice_id || '').trim();
    if (!value || seen.has(value) || builtInVoiceIds.has(value)) {
      continue;
    }
    seen.add(value);
    const status = String(voice.status || '').trim();
    const ready = status === 'ready';
    const statusLabel = statusLabels[status] || status;
    const baseName = voice.display_name || value;
    const displayLabel = clonedVoiceLabelFormatter
      ? clonedVoiceLabelFormatter(baseName)
      : baseName;
    options.push({
      value,
      label: ready ? displayLabel : `${displayLabel} · ${statusLabel}`,
      source: 'cloned',
      status,
      voice_bid: voice.voice_bid,
      disabled: !ready,
    });
  }

  for (const voice of builtInVoices || []) {
    const value = (voice.value || '').trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    options.push({ ...voice, value, source: 'built_in', disabled: false });
  }

  const normalizedCurrent = (currentVoiceId || '').trim();
  if (
    normalizedCurrent &&
    !seen.has(normalizedCurrent) &&
    manualVoiceValidator(normalizedCurrent)
  ) {
    options.push({
      value: normalizedCurrent,
      label: `${manualLabel} (${normalizedCurrent})`,
      source: 'manual',
      disabled: false,
    });
  }

  return options;
}
