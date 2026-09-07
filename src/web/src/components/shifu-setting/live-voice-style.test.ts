import {
  getLiveVoiceStyleI18nKey,
  LIVE_VOICE_STYLE_I18N_KEYS,
} from './live-voice-style';

const OFFICIAL_GEMINI_LIVE_STYLES = [
  'Bright',
  'Upbeat',
  'Informative',
  'Firm',
  'Excitable',
  'Youthful',
  'Breezy',
  'Easy-going',
  'Breathy',
  'Clear',
  'Smooth',
  'Gravelly',
  'Soft',
  'Even',
  'Mature',
  'Forward',
  'Friendly',
  'Casual',
  'Gentle',
  'Lively',
  'Knowledgeable',
  'Warm',
] as const;

describe('Gemini Live voice style localization', () => {
  it('maps every official low-cardinality style to a stable i18n key', () => {
    expect(Object.keys(LIVE_VOICE_STYLE_I18N_KEYS)).toEqual(
      OFFICIAL_GEMINI_LIVE_STYLES,
    );

    for (const style of OFFICIAL_GEMINI_LIVE_STYLES) {
      expect(getLiveVoiceStyleI18nKey(style)).toMatch(
        /^module\.shifuSetting\.liveVoiceStyles\.[A-Za-z]+$/,
      );
    }
  });

  it('does not expose an unexpected backend style as visible copy', () => {
    expect(
      getLiveVoiceStyleI18nKey('Provider supplied free-form text'),
    ).toBeNull();
  });
});
