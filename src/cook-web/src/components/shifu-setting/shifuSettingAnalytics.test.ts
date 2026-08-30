import { buildShifuSettingSaveAnalytics } from './shifuSettingAnalytics';

describe('buildShifuSettingSaveAnalytics', () => {
  it('returns only the reviewed settings adoption fields', () => {
    const payload = buildShifuSettingSaveAnalytics({
      shifuBid: 'course-1',
      saveType: 'manual',
      ttsEnabled: true,
      defaultListenModeEnabled: true,
      useLearnerLanguage: false,
    });

    expect(payload).toEqual({
      shifu_bid: 'course-1',
      save_type: 'manual',
      tts_enabled: true,
      default_listen_mode_enabled: true,
      use_learner_language: false,
    });
    expect(payload).not.toHaveProperty('name');
    expect(payload).not.toHaveProperty('description');
    expect(payload).not.toHaveProperty('system_prompt');
    expect(payload).not.toHaveProperty('ask_provider_config');
    expect(payload).not.toHaveProperty('tts_voice_id');
  });

  it('does not report listen mode enabled while TTS is disabled', () => {
    expect(
      buildShifuSettingSaveAnalytics({
        shifuBid: 'course-1',
        saveType: 'auto',
        ttsEnabled: false,
        defaultListenModeEnabled: true,
        useLearnerLanguage: true,
      }).default_listen_mode_enabled,
    ).toBe(false);
  });
});
