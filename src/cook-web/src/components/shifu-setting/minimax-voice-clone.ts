export const MINIMAX_PROVIDER = 'minimax';

export type MiniMaxVoiceCloneStatus =
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

export interface MiniMaxClonedVoice {
  voice_bid: string;
  voice_id: string;
  display_name: string;
  status: MiniMaxVoiceCloneStatus | string;
  status_msg?: string;
  failure_reason?: string;
  minimax_demo_audio_url?: string;
  estimated_credits?: string;
  charged_credits?: string;
  billing_status?: string;
}

export interface MiniMaxVoiceOption extends TTSVoiceOptionBase {
  source: 'built_in' | 'cloned' | 'manual';
  status?: string;
  voice_bid?: string;
  disabled?: boolean;
}

const MINIMAX_CUSTOM_VOICE_ID_PATTERN =
  /^[A-Za-z](?=.{7,63}$)[A-Za-z0-9_-]*[A-Za-z0-9]$/;

export function isMiniMaxProvider(providerName: string): boolean {
  return (providerName || '').trim().toLowerCase() === MINIMAX_PROVIDER;
}

export function isValidMiniMaxCustomVoiceId(voiceId: string): boolean {
  return MINIMAX_CUSTOM_VOICE_ID_PATTERN.test((voiceId || '').trim());
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
  if (!normalizedVoiceId) {
    return false;
  }
  if (!isMiniMaxProvider(providerName) || !supportsCustomVoiceId) {
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
  manualLabel,
  statusLabels = {},
}: {
  builtInVoices: TTSVoiceOptionBase[];
  clonedVoices: MiniMaxClonedVoice[];
  currentVoiceId: string;
  manualLabel: string;
  statusLabels?: Record<string, string>;
}): MiniMaxVoiceOption[] {
  const seen = new Set<string>();
  const options: MiniMaxVoiceOption[] = [];

  for (const voice of builtInVoices || []) {
    const value = (voice.value || '').trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    options.push({
      ...voice,
      value,
      source: 'built_in',
      disabled: false,
    });
  }

  for (const voice of clonedVoices || []) {
    const value = (voice.voice_id || '').trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    const status = String(voice.status || '').trim();
    const ready = status === 'ready';
    const statusLabel = statusLabels[status] || status;
    options.push({
      value,
      label: ready
        ? voice.display_name || value
        : `${voice.display_name || value} · ${statusLabel}`,
      source: 'cloned',
      status,
      voice_bid: voice.voice_bid,
      disabled: !ready,
    });
  }

  const normalizedCurrent = (currentVoiceId || '').trim();
  if (
    normalizedCurrent &&
    !seen.has(normalizedCurrent) &&
    isValidMiniMaxCustomVoiceId(normalizedCurrent)
  ) {
    seen.add(normalizedCurrent);
    options.push({
      value: normalizedCurrent,
      label: manualLabel,
      source: 'manual',
      disabled: false,
    });
  }

  return options;
}
