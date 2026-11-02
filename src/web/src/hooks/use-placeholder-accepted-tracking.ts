import { useCallback } from 'react';
import { useTracking } from './use-tracking';

type PlaceholderSurface =
  | 'course_read'
  | 'course_listen'
  | 'profile_onboarding';

export function usePlaceholderAcceptedTracking(
  surface: PlaceholderSurface,
  enabled: boolean,
) {
  const { trackEvent } = useTracking();
  return useCallback(() => {
    if (!enabled) return;
    try {
      void Promise.resolve(
        trackEvent('learner_interaction_placeholder_accepted', { surface }),
      ).catch(() => {});
    } catch {}
  }, [enabled, surface, trackEvent]);
}
