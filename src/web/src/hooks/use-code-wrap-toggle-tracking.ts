import { useEffect } from 'react';
import { useTracking } from './use-tracking';

export type CodeWrapToggleSurface =
  | 'course_read'
  | 'course_listen'
  | 'course_classroom';

// Marks a region whose code blocks are outside the measured population, such
// as Profile onboarding shown over a lesson.
const CODE_WRAP_TRACKING_EXCLUDED_ATTRIBUTE =
  'data-code-wrap-tracking-excluded';

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
    // The library reports a toggle without saying which button was pressed.
    // The press reaches this capture listener first, so remember its target.
    let pressTarget: EventTarget | null = null;
    const rememberPressTarget = (event: MouseEvent) => {
      pressTarget = event.target;
    };
    document.addEventListener('click', rememberPressTarget, true);
    // Loaded on demand so the renderer stays out of the page's initial bundle.
    void import('markdown-flow-ui/renderer')
      .then(({ subscribeCodeWrapToggle }) => {
        if (!active) return;
        unsubscribe = subscribeCodeWrapToggle(wrapEnabled => {
          try {
            const target = pressTarget;
            pressTarget = null;
            if (
              target instanceof Element &&
              target.closest(`[${CODE_WRAP_TRACKING_EXCLUDED_ATTRIBUTE}]`)
            ) {
              return;
            }
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
      document.removeEventListener('click', rememberPressTarget, true);
      unsubscribe?.();
    };
  }, [surface, trackEvent]);
}
