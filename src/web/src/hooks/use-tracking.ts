import { useCallback } from 'react';
import { EVENT_NAMES, tracking } from '@/lib/tracking';
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

  return { trackEvent, EVENT_NAMES };
};
