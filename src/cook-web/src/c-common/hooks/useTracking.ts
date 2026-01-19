import { useCallback } from 'react';
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

export const useTracking = () => {
  const { frameLayout } = useUiLayoutStore(state => state);
  const { userInfo } = useUserStore(state => state);

  const getEventBasicData = useCallback(() => {
    return {
      user_type: userInfo?.state ? USER_STATE_DICT[userInfo.state] : 'guest',
      user_id: userInfo?.user_id || 0,
      device: frameLayout === FRAME_LAYOUT_MOBILE ? 'H5' : 'Web',
    };
  }, [frameLayout, userInfo?.state, userInfo?.user_id]);

  const trackEvent = useCallback(
    async (eventName: string, eventData?: Record<string, any>) => {
      try {
        const basicData = getEventBasicData();
        const data = {
          ...eventData,
          ...basicData,
          timeStamp: new Date().toLocaleString(),
        };
        // console.log('trackEvent', eventName, data);
        tracking(eventName, data);
      } catch (error) {
        console.error('Failed to track event:', eventName, error);
      }
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
      } catch (error) {
        console.error('Failed to track trial progress:', error);
      }
    },
    [trackEvent],
  );

  const trackBlockView = useCallback(
    async (courseId: string, blockId: string) => {
      try {
        const { data: scriptInfo } = await getScriptInfo(courseId, blockId);

        trackEvent(EVENT_NAMES.BLOCK_VIEW, {
          shifu_bid: courseId,
          block_bid: blockId,
          position: scriptInfo?.position ?? 0,
          outline_name: scriptInfo?.outline_name ?? '',
          is_trial: scriptInfo?.is_trial_lesson ?? false,
        });
      } catch (error) {
        console.error('Failed to track block view:', error);
      }
    },
    [trackEvent],
  );

  const trackLessonComplete = useCallback(
    (shifu_bid: string, outline_bid: string) => {
      trackEvent(EVENT_NAMES.LESSON_COMPLETE, {
        shifu_bid,
        outline_bid,
      });
    },
    [trackEvent],
  );

  const trackAiInteraction = useCallback(
    (data: {
      shifu_bid: string;
      outline_bid: string;
      interaction_type: 'user_message' | 'ai_response' | 'button_click';
      message_length?: number;
    }) => {
      trackEvent(EVENT_NAMES.AI_INTERACTION, data);
    },
    [trackEvent],
  );

  return {
    trackEvent,
    trackTrailProgress,
    trackBlockView,
    trackLessonComplete,
    trackAiInteraction,
    EVENT_NAMES,
  };
};
