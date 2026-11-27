import { useEffect } from 'react';
import { useTracking } from './use-tracking';

export type CodeWrapToggleSurface =
  | 'course_read'
  | 'course_listen'
  | 'course_classroom';

// Reports a learner switching code block line wrapping. Pass null on surfaces
// outside the measured population, such as course previews.
export function useCodeWrapToggleTracking(
  surface: CodeWrapToggleSurface | null,
) {
  const { trackEvent } = useTracking();
  useEffect(() => {
    if (!surface) return;
    let active = true;
    let unsubscribe: (() => void) | undefined;
    // Loaded on demand so the renderer stays out of the page's initial bundle.
    void import('markdown-flow-ui/renderer')
      .then(({ subscribeCodeWrapToggle }) => {
        if (!active) return;
        unsubscribe = subscribeCodeWrapToggle(wrapEnabled => {
          try {
            void Promise.resolve(
              trackEvent('learner_code_block_wrap_toggled', {
                surface,
                wrap_enabled: wrapEnabled,
              }),
            ).catch(() => {});
          } catch {}
        });
      })
      .catch(() => {});
    return () => {
      active = false;
      unsubscribe?.();
    };
  }, [surface, trackEvent]);
}
