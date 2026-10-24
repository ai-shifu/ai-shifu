import { useCallback } from 'react';
import { EVENT_NAMES, tracking } from '@/lib/tracking';
import { getScriptInfo } from '@/api/lesson';
export { EVENT_NAMES } from '@/lib/tracking';

export const useTracking = () => {
  const trackEvent = useCallback(
    async (
      eventName: string,
      eventData: Record<string, unknown> = {},
    ): Promise<void> => {
      try {
        void tracking(eventName, eventData).catch(() => {});
      } catch {}
    },
    [],
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
        });
      } catch {}
    },
    [trackEvent],
  );

  return { trackEvent, trackTrailProgress, EVENT_NAMES };
};
