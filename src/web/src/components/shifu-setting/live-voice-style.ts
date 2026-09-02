import type { I18nKey } from '@/types/i18n-keys';

export const LIVE_VOICE_STYLE_I18N_KEYS = {
  Bright: 'module.shifuSetting.liveVoiceStyles.bright',
  Upbeat: 'module.shifuSetting.liveVoiceStyles.upbeat',
  Informative: 'module.shifuSetting.liveVoiceStyles.informative',
  Firm: 'module.shifuSetting.liveVoiceStyles.firm',
  Excitable: 'module.shifuSetting.liveVoiceStyles.excitable',
  Youthful: 'module.shifuSetting.liveVoiceStyles.youthful',
  Breezy: 'module.shifuSetting.liveVoiceStyles.breezy',
  'Easy-going': 'module.shifuSetting.liveVoiceStyles.easyGoing',
  Breathy: 'module.shifuSetting.liveVoiceStyles.breathy',
  Clear: 'module.shifuSetting.liveVoiceStyles.clear',
  Smooth: 'module.shifuSetting.liveVoiceStyles.smooth',
  Gravelly: 'module.shifuSetting.liveVoiceStyles.gravelly',
  Soft: 'module.shifuSetting.liveVoiceStyles.soft',
  Even: 'module.shifuSetting.liveVoiceStyles.even',
  Mature: 'module.shifuSetting.liveVoiceStyles.mature',
  Forward: 'module.shifuSetting.liveVoiceStyles.forward',
  Friendly: 'module.shifuSetting.liveVoiceStyles.friendly',
  Casual: 'module.shifuSetting.liveVoiceStyles.casual',
  Gentle: 'module.shifuSetting.liveVoiceStyles.gentle',
  Lively: 'module.shifuSetting.liveVoiceStyles.lively',
  Knowledgeable: 'module.shifuSetting.liveVoiceStyles.knowledgeable',
  Warm: 'module.shifuSetting.liveVoiceStyles.warm',
} as const satisfies Record<string, I18nKey>;

export function getLiveVoiceStyleI18nKey(style: string): I18nKey | null {
  return (
    LIVE_VOICE_STYLE_I18N_KEYS[
      style as keyof typeof LIVE_VOICE_STYLE_I18N_KEYS
    ] ?? null
  );
}
