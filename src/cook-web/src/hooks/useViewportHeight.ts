import { useEffect } from 'react';

const APP_HEIGHT_VAR = '--app-height';
const KEYBOARD_OFFSET_VAR = '--keyboard-offset';

export const useViewportHeight = () => {
  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return;
    }

    // Sync CSS variable with real viewport height to avoid iOS keyboard gaps
    const updateViewportHeight = () => {
      const viewport = window.visualViewport;
      const height = viewport ? viewport.height : window.innerHeight;
      const keyboardOffset = viewport
        ? Math.max(
            0,
            window.innerHeight - (viewport.height + viewport.offsetTop),
          )
        : 0;

      document.documentElement.style.setProperty(APP_HEIGHT_VAR, `${height}px`);
      document.documentElement.style.setProperty(
        KEYBOARD_OFFSET_VAR,
        `${keyboardOffset}px`,
      );
    };

    updateViewportHeight();

    const viewport = window.visualViewport;
    viewport?.addEventListener('resize', updateViewportHeight);
    window.addEventListener('resize', updateViewportHeight);

    return () => {
      viewport?.removeEventListener('resize', updateViewportHeight);
      window.removeEventListener('resize', updateViewportHeight);
    };
  }, []);
};
