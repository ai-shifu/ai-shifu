export type ShifuSettingSaveAnalyticsInput = {
  shifuBid: string;
  saveType: 'auto' | 'manual';
  ttsEnabled: boolean;
  defaultListenModeEnabled: boolean;
  useLearnerLanguage: boolean;
  followUpMode: 'text' | 'live_voice';
};

export const buildShifuSettingSaveAnalytics = ({
  shifuBid,
  saveType,
  ttsEnabled,
  defaultListenModeEnabled,
  useLearnerLanguage,
  followUpMode,
}: ShifuSettingSaveAnalyticsInput) => ({
  shifu_bid: shifuBid,
  save_type: saveType,
  tts_enabled: ttsEnabled,
  default_listen_mode_enabled: ttsEnabled && defaultListenModeEnabled,
  use_learner_language: useLearnerLanguage,
  follow_up_mode: followUpMode,
});
