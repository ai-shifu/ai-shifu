import { useEffect } from 'react';

const APP_HEIGHT_VAR = '--app-height';

export const useViewportHeight = () => {
  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      return;
    }

    // Sync CSS variable with real viewport height to avoid iOS keyboard gaps
    const updateViewportHeight = () => {
      const viewport = window.visualViewport;
      const height = viewport ? viewport.height : window.innerHeight;
      document.documentElement.style.setProperty(APP_HEIGHT_VAR, `${height}px`);
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
