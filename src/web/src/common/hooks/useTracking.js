import { useCallback } from 'react';
import { tracking } from 'common/tools/tracking.js';
import { useUserStore } from 'stores/useUserStore.js';
import { useUiLayoutStore } from 'stores/useUiLayoutStore.js';
export { EVENT_NAMES } from 'common/tools/tracking.js';

const USER_STATE_DICT = {
  '未注册': 'guest',
  '已注册': 'user',
  '已付费': 'member',
}
export const useTracking = () => {
  const { isMobile } = useUiLayoutStore((state) => state);
  const { userInfo } = useUserStore((state) => state);

  const getEventBasicData = useCallback(() => {
    return {
      user_type: userInfo.state ? USER_STATE_DICT[userInfo.state] : 'guest',
      user_id: userInfo?.user_id || 0,
      device: isMobile ? 'H5' : 'Web',
    }
  }, [isMobile, userInfo?.state, userInfo?.user_id])

  const trackEvent = useCallback(async (eventName, eventData) => {
    try {
      const basicData = getEventBasicData();
      const data = {
        ...eventData,
        ...basicData
      }
      tracking(eventName, data);
    } catch { }
  }, [getEventBasicData])

  return { trackEvent }
}
