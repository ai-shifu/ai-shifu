export type ShifuSettingSaveAnalyticsInput = {
  shifuBid: string;
  saveType: 'auto' | 'manual';
  ttsEnabled: boolean;
  defaultListenModeEnabled: boolean;
  useLearnerLanguage: boolean;
  followUpMode: 'text' | 'live_voice';
  price: number;
};

export const buildShifuSettingSaveAnalytics = ({
  shifuBid,
  saveType,
  ttsEnabled,
  defaultListenModeEnabled,
  useLearnerLanguage,
  followUpMode,
  price,
}: ShifuSettingSaveAnalyticsInput) => ({
  shifu_bid: shifuBid,
  save_type: saveType,
  tts_enabled: ttsEnabled,
  default_listen_mode_enabled: ttsEnabled && defaultListenModeEnabled,
  use_learner_language: useLearnerLanguage,
  follow_up_mode: followUpMode,
  price_tier:
    price === 0 ? 'free' : price < 0.5 ? 'micro_paid' : 'standard_paid',
});
