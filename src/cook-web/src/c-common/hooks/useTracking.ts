import { useCallback, useEffect } from 'react';
import { EVENT_NAMES, tracking } from '@/c-common/tools/tracking';
import { useUserStore } from '@/store';
import { useUiLayoutStore } from '@/c-store/useUiLayoutStore';
import { FRAME_LAYOUT_MOBILE } from '@/c-constants/uiConstants';
import { getScriptInfo } from '@/c-api/lesson';
export { EVENT_NAMES } from '@/c-common/tools/tracking';

const USER_STATE_DICT = {
  未注册: 'guest',
  已注册: 'user',
  已付费: 'member',
};

// Module-level singleton state for global deduplication
const identifyState = {
  timeout: undefined as ReturnType<typeof setTimeout> | undefined,
  prevUserInfo: undefined as string | undefined,
};

export const useTracking = () => {
  const { frameLayout } = useUiLayoutStore(state => state);
  const { userInfo } = useUserStore(state => state);

  // Identify user when user info changes with global debouncing and change detection
  useEffect(() => {
    // Clear previous global timeout if exists
    if (identifyState.timeout) {
      clearTimeout(identifyState.timeout);
    }

    // Set global debounced timeout
    identifyState.timeout = setTimeout(() => {
      try {
        const umami = window.umami;
        if (!umami) {
          return;
        }

        // Create a unique identifier for current state
        const currentState = JSON.stringify({
          user_id: userInfo?.user_id,
          name: userInfo?.name,
          state: userInfo?.state,
          language: userInfo?.language,
        });

        // Only call identify if state actually changed
        if (currentState !== identifyState.prevUserInfo) {
          // Build session data with only safe fields
          const sessionData: {
            nickname?: string;
            user_state?: string;
            language?: string;
          } = {};
          if (userInfo?.name) sessionData.nickname = userInfo.name;
          if (userInfo?.state) sessionData.user_state = userInfo.state;
          if (userInfo?.language) sessionData.language = userInfo.language;

          // Identify user with their unique ID and session data
          if (userInfo?.user_id) {
            if (Object.keys(sessionData).length > 0) {
              umami.identify(userInfo.user_id, sessionData);
            } else {
              umami.identify(userInfo.user_id);
            }
          } else {
            // Clear identification if no user
            umami.identify(null);
          }

          // Update global previous state reference
          identifyState.prevUserInfo = currentState;
        }
      } catch {
        // Silently fail - tracking errors should not affect user experience
        // Uncomment for debugging: console.error('Umami identify error:', error);
      }
    }, 100); // 100ms debounce delay

    // Cleanup function
    return () => {
      // Note: We don't clear the global timeout on unmount as other components may still be using it
      // The timeout will naturally complete or be cleared by the next update
    };
  }, [userInfo?.user_id, userInfo?.name, userInfo?.state, userInfo?.language]);

  const getEventBasicData = useCallback(() => {
    return {
      user_type: userInfo?.state ? USER_STATE_DICT[userInfo.state] : 'guest',
      user_id: userInfo?.user_id || 0,
      device: frameLayout === FRAME_LAYOUT_MOBILE ? 'H5' : 'Web',
    };
  }, [frameLayout, userInfo?.state, userInfo?.user_id]);

  const trackEvent = useCallback(
    async (eventName, eventData) => {
      try {
        const basicData = getEventBasicData();
        const data = {
          ...eventData,
          ...basicData,
        };
        tracking(eventName, data);
      } catch {}
    },
    [getEventBasicData],
  );

  const trackTrailProgress = useCallback(
    async (courseId: string, scriptId: string) => {
      try {
        const { data: scriptInfo } = await getScriptInfo(courseId, scriptId);

        // Check whether this script is part of a trial lesson
        if (!scriptInfo?.is_trial_lesson) {
          return;
        }

        trackEvent(EVENT_NAMES.TRIAL_PROGRESS, {
          progress_no: scriptInfo.position,
          progress_desc: scriptInfo.outline_name,
        });
      } catch {}
    },
    [trackEvent],
  );

  return { trackEvent, trackTrailProgress, EVENT_NAMES };
};
