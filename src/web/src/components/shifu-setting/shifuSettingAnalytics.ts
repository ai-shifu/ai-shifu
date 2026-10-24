import type { ModelIndex } from '@/types/shifu';

export type ShifuSettingSaveAnalyticsInput = {
  shifuBid: string;
  saveType: 'auto' | 'manual';
  ttsEnabled: boolean;
  defaultListenModeEnabled: boolean;
  useLearnerLanguage: boolean;
  followUpMode: 'text' | 'live_voice';
  price: number;
  mainModelIndex?: ModelIndex | null;
  followUpModelIndex?: ModelIndex | null;
  mainModelFallback?: boolean;
  followUpModelFallback?: boolean;
};

const normalizeIndex = (value: unknown): ModelIndex =>
  typeof value === 'string' && /^[1-9]$/.test(value)
    ? (value as ModelIndex)
    : '1';

export const buildShifuSettingSaveAnalytics = ({
  shifuBid,
  saveType,
  ttsEnabled,
  defaultListenModeEnabled,
  useLearnerLanguage,
  followUpMode,
  price,
  mainModelIndex,
  followUpModelIndex,
  mainModelFallback = false,
  followUpModelFallback = false,
}: ShifuSettingSaveAnalyticsInput) => ({
  shifu_bid: shifuBid,
  save_type: saveType,
  tts_enabled: ttsEnabled,
  default_listen_mode_enabled: ttsEnabled && defaultListenModeEnabled,
  use_learner_language: useLearnerLanguage,
  follow_up_mode: followUpMode,
  main_model_index: normalizeIndex(mainModelIndex),
  follow_up_model_index:
    followUpMode === 'live_voice'
      ? 'not_applicable'
      : normalizeIndex(followUpModelIndex),
  main_model_fallback: mainModelFallback,
  follow_up_model_fallback:
    followUpMode === 'live_voice' ? false : followUpModelFallback,
  price_tier:
    price === 0 ? 'free' : price < 0.5 ? 'micro_paid' : 'standard_paid',
});
