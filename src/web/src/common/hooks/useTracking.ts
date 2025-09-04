import { useCallback, useEffect } from 'react';
import { EVENT_NAMES, tracking } from 'common/tools/tracking';
import { useUserStore } from 'stores/useUserStore';
import { useUiLayoutStore } from 'stores/useUiLayoutStore';
import { FRAME_LAYOUT_MOBILE } from 'constants/uiConstants';
import { getScriptInfo } from 'Api/lesson';
export { EVENT_NAMES } from 'common/tools/tracking';

const USER_STATE_DICT = {
  '未注册': 'guest',
  '已注册': 'user',
  '已付费': 'member',
};
export const useTracking = () => {
  const { frameLayout } = useUiLayoutStore((state) => state);
  const { userInfo } = useUserStore((state) => state);

  const identifyUser = useCallback(() => {
    try {
      const umami = window.umami;
      if (!umami) {
        return;
      }

      if (userInfo?.user_id) {
        // Identify user with their unique ID
        umami.identify(userInfo.user_id);
      } else {
        // Clear identification when no user
        umami.identify(null);
      }
    } catch (error) { }
  }, [userInfo?.user_id]);

  // Call identify when user info changes
  useEffect(() => {
    identifyUser();
  }, [identifyUser]);

  const getEventBasicData = useCallback(() => {
    return {
      user_type: userInfo?.state ? USER_STATE_DICT[userInfo.state] : 'guest',
      user_id: userInfo?.user_id || 0,
      device: frameLayout === FRAME_LAYOUT_MOBILE ? 'H5' : 'Web',
    };
  }, [frameLayout, userInfo?.state, userInfo?.user_id]);

  const trackEvent = useCallback(async (eventName, eventData) => {
    try {
      const basicData = getEventBasicData();
      const data = {
        ...eventData,
        ...basicData
      };
      tracking(eventName, data);
    } catch { }
  }, [getEventBasicData]);


  const trackTrailProgress = useCallback(async (scriptId) => {
    try {
      const { data: scriptInfo } = await getScriptInfo(scriptId);

      // 是否体验课
      if (!scriptInfo?.is_trial_lesson) {
        return;
      }

      trackEvent(EVENT_NAMES.TRIAL_PROGRESS, {
        progress_no: scriptInfo.script_index,
        progress_desc: scriptInfo.script_name,
      });
    } catch { }
  }, [trackEvent]);

  return { trackEvent, trackTrailProgress, EVENT_NAMES };
};
