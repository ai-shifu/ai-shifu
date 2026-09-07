import { buildShifuSettingSaveAnalytics } from './shifuSettingAnalytics';

describe('buildShifuSettingSaveAnalytics', () => {
  it('returns only the reviewed settings adoption fields', () => {
    const payload = buildShifuSettingSaveAnalytics({
      shifuBid: 'course-1',
      saveType: 'manual',
      ttsEnabled: true,
      defaultListenModeEnabled: true,
      useLearnerLanguage: false,
      followUpMode: 'live_voice',
    });

    expect(payload).toEqual({
      shifu_bid: 'course-1',
      save_type: 'manual',
      tts_enabled: true,
      default_listen_mode_enabled: true,
      use_learner_language: false,
      follow_up_mode: 'live_voice',
    });
    expect(payload).not.toHaveProperty('name');
    expect(payload).not.toHaveProperty('description');
    expect(payload).not.toHaveProperty('system_prompt');
    expect(payload).not.toHaveProperty('ask_model');
    expect(payload).not.toHaveProperty('ask_provider_config');
    expect(payload).not.toHaveProperty('live_voice');
    expect(payload).not.toHaveProperty('tts_voice_id');
    expect(payload).not.toHaveProperty('api_key');
    expect(payload).not.toHaveProperty('token');
    expect(payload).not.toHaveProperty('url');
    expect(Object.keys(payload).sort()).toEqual(
      [
        'default_listen_mode_enabled',
        'follow_up_mode',
        'save_type',
        'shifu_bid',
        'tts_enabled',
        'use_learner_language',
      ].sort(),
    );
  });

  it('reports the exact text-mode payload and normalizes disabled listen mode', () => {
    expect(
      buildShifuSettingSaveAnalytics({
        shifuBid: 'course-1',
        saveType: 'auto',
        ttsEnabled: false,
        defaultListenModeEnabled: true,
        useLearnerLanguage: true,
        followUpMode: 'text',
      }),
    ).toEqual({
      shifu_bid: 'course-1',
      save_type: 'auto',
      tts_enabled: false,
      default_listen_mode_enabled: false,
      use_learner_language: true,
      follow_up_mode: 'text',
    });
  });
});
