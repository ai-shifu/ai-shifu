import type { ModelTier } from '@/types/shifu';

export type ShifuSettingSaveAnalyticsInput = {
  shifuBid: string;
  saveType: 'auto' | 'manual';
  ttsEnabled: boolean;
  defaultListenModeEnabled: boolean;
  useLearnerLanguage: boolean;
  followUpMode: 'text' | 'live_voice';
  price: number;
  mainModelTier?: ModelTier | null;
  followUpModelTier?: ModelTier | null;
};

const normalizeTier = (value: unknown) =>
  value === 'fast' || value === 'balanced' || value === 'ultimate'
    ? value
    : 'legacy';

export const buildShifuSettingSaveAnalytics = ({
  shifuBid,
  saveType,
  ttsEnabled,
  defaultListenModeEnabled,
  useLearnerLanguage,
  followUpMode,
  price,
  mainModelTier,
  followUpModelTier,
}: ShifuSettingSaveAnalyticsInput) => ({
  shifu_bid: shifuBid,
  save_type: saveType,
  tts_enabled: ttsEnabled,
  default_listen_mode_enabled: ttsEnabled && defaultListenModeEnabled,
  use_learner_language: useLearnerLanguage,
  follow_up_mode: followUpMode,
  main_model_tier: normalizeTier(mainModelTier),
  follow_up_model_tier:
    followUpMode === 'live_voice'
      ? 'not_applicable'
      : normalizeTier(followUpModelTier),
  price_tier:
    price === 0 ? 'free' : price < 0.5 ? 'micro_paid' : 'standard_paid',
});
