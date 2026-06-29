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

export interface MiniMaxCloneCost {
  estimated_credits?: string;
  available_credits?: string;
  can_submit?: boolean;
  billing_enabled?: boolean;
}

export interface MiniMaxVoiceOption extends TTSVoiceOptionBase {
  source: 'built_in' | 'cloned' | 'manual';
  status?: string;
  voice_bid?: string;
  minimax_demo_audio_url?: string;
  disabled?: boolean;
}

export const MINIMAX_SOURCE_MIN_SECONDS = 10;
export const MINIMAX_SOURCE_MAX_SECONDS = 300;

export type MiniMaxCloneSubmitBlockReason =
  | 'clone_in_progress'
  | 'insufficient_credits'
  | 'missing_source_audio'
  | 'recording_in_progress'
  | 'source_recording_too_short'
  | 'submitting'
  | null;

const MINIMAX_CUSTOM_VOICE_ID_PATTERN =
  /^[A-Za-z](?=.{7,63}$)[A-Za-z0-9_-]*[A-Za-z0-9]$/;

export function isMiniMaxProvider(providerName: string): boolean {
  return (providerName || '').trim().toLowerCase() === MINIMAX_PROVIDER;
}

export function isValidMiniMaxCustomVoiceId(voiceId: string): boolean {
  return MINIMAX_CUSTOM_VOICE_ID_PATTERN.test((voiceId || '').trim());
}

export function buildMiniMaxClonedVoiceListParams(
  shifuId?: string,
): Record<string, never> {
  void shifuId;
  return {};
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
      minimax_demo_audio_url: voice.minimax_demo_audio_url || '',
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
      label: `${manualLabel} (${normalizedCurrent})`,
      source: 'manual',
      disabled: false,
    });
  }

  return options;
}

export async function loadMiniMaxVoiceRefreshData({
  fetchVoices,
  fetchCloneCost,
}: {
  fetchVoices: () => Promise<
    { voices?: MiniMaxClonedVoice[] } | MiniMaxClonedVoice[]
  >;
  fetchCloneCost: () => Promise<MiniMaxCloneCost | null | undefined>;
}): Promise<{
  voices: MiniMaxClonedVoice[] | null;
  cloneCost: MiniMaxCloneCost | null;
  errors: unknown[];
}> {
  const [voicesResult, costResult] = await Promise.allSettled([
    fetchVoices(),
    fetchCloneCost(),
  ]);
  const errors: unknown[] = [];
  let voices: MiniMaxClonedVoice[] | null = null;
  let cloneCost: MiniMaxCloneCost | null = null;

  if (voicesResult.status === 'fulfilled') {
    const payload = voicesResult.value;
    voices = Array.isArray(payload) ? payload : payload?.voices || [];
  } else {
    errors.push(voicesResult.reason);
  }

  if (costResult.status === 'fulfilled') {
    cloneCost = costResult.value || null;
  } else {
    errors.push(costResult.reason);
  }

  return { voices, cloneCost, errors };
}

export async function executeMiniMaxVoiceAction({
  action,
  onSuccess,
  onError,
}: {
  action: () => Promise<unknown>;
  onSuccess?: () => void | Promise<void>;
  onError: (error: unknown) => void;
}): Promise<boolean> {
  try {
    await action();
    await onSuccess?.();
    return true;
  } catch (error) {
    onError(error);
    return false;
  }
}

export function getMiniMaxRecordingElapsedSeconds(
  startedAtMs: number,
  nowMs: number = Date.now(),
): number {
  return Math.max(0, Math.floor((nowMs - startedAtMs) / 1000));
}

export function getMiniMaxCloneSubmitBlockReason({
  sourceFileSelected,
  sourceElapsed,
  recordingKind,
  submitting,
  cloneInProgress,
  canSubmitByCredits,
}: {
  sourceFileSelected: boolean;
  sourceElapsed: number;
  recordingKind: 'source' | null;
  submitting: boolean;
  cloneInProgress: boolean;
  canSubmitByCredits: boolean;
}): MiniMaxCloneSubmitBlockReason {
  if (cloneInProgress) {
    return 'clone_in_progress';
  }
  if (submitting) {
    return 'submitting';
  }
  if (!canSubmitByCredits) {
    return 'insufficient_credits';
  }
  if (recordingKind) {
    if (sourceElapsed < MINIMAX_SOURCE_MIN_SECONDS) {
      return 'source_recording_too_short';
    }
    return 'recording_in_progress';
  }
  if (!sourceFileSelected) {
    return 'missing_source_audio';
  }
  if (sourceElapsed < MINIMAX_SOURCE_MIN_SECONDS) {
    return 'source_recording_too_short';
  }
  return null;
}
