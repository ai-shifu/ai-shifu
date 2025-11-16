import { useEffect, useRef, useState, useCallback } from 'react';

/**
 * Editor layout configuration constants
 */
const LAYOUT_CONFIG = {
  // Outline tree panel (left sidebar)
  OUTLINE_DEFAULT_SIZE: 20, // 20% of total width
  OUTLINE_MIN_SIZE: 15, // 15% minimum
  OUTLINE_MAX_SIZE: 40, // 40% maximum
  OUTLINE_COLLAPSED_SIZE: 5, // When collapsed, show only 5%

  // LocalStorage key
  STORAGE_KEY: 'shifu-editor-layout-state',
} as const;

/**
 * Layout state stored in localStorage
 */
interface LayoutState {
  outlineWidth: number; // Percentage (0-100)
  savedOutlineWidth?: number; // Save width before collapse for restoration
}

/**
 * Hook to manage editor layout state with localStorage persistence
 *
 * Architecture (based on react-resizable-panels best practices):
 * - Uses PanelGroup.onLayout callback to track layout changes
 * - Uses PanelGroupHandle.setLayout() to programmatically update layout
 * - defaultSize only used for initial render (not reactive)
 * - Persists layout to localStorage
 * - Supports collapse/expand with width restoration
 * - Supports double-click reset to default
 */
export const useEditorLayoutState = () => {
  // Initialize state from localStorage or use defaults
  const [layout, setLayout] = useState<LayoutState>(() => {
    if (typeof window === 'undefined') {
      // SSR fallback
      return {
        outlineWidth: LAYOUT_CONFIG.OUTLINE_DEFAULT_SIZE,
      };
    }

    try {
      const saved = localStorage.getItem(LAYOUT_CONFIG.STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as LayoutState;
        // Validate saved values
        if (
          parsed.outlineWidth >= LAYOUT_CONFIG.OUTLINE_MIN_SIZE &&
          parsed.outlineWidth <= LAYOUT_CONFIG.OUTLINE_MAX_SIZE
        ) {
          return parsed;
        }
      }
    } catch (error) {
      console.warn('Failed to load editor layout from localStorage:', error);
    }

    // Return defaults if no valid saved state
    return {
      outlineWidth: LAYOUT_CONFIG.OUTLINE_DEFAULT_SIZE,
    };
  });

  // Track if this is the first render
  const isFirstRender = useRef(true);

  // Save to localStorage whenever layout changes (skip first render)
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }

    if (typeof window !== 'undefined') {
      try {
        localStorage.setItem(LAYOUT_CONFIG.STORAGE_KEY, JSON.stringify(layout));
      } catch (error) {
        console.warn('Failed to save editor layout to localStorage:', error);
      }
    }
  }, [layout]);

  /**
   * Handle PanelGroup layout change
   * This is called whenever user drags the resize handle
   * Receives full layout array from PanelGroup: [outlineWidth%, editorWidth%]
   */
  const handleLayoutChange = useCallback((newLayout: number[]) => {
    const [outlineWidth] = newLayout;

    // Only save if this is a valid expanded state (not collapsed)
    // This prevents saving the 5% collapsed width to localStorage
    if (
      outlineWidth >= LAYOUT_CONFIG.OUTLINE_MIN_SIZE &&
      outlineWidth <= LAYOUT_CONFIG.OUTLINE_MAX_SIZE
    ) {
      setLayout(prev => ({
        ...prev,
        outlineWidth,
      }));
    }
  }, []);

  /**
   * Get the outline width to use
   * Returns savedOutlineWidth if available (after expand), otherwise current width
   */
  const getOutlineWidth = useCallback(() => {
    return layout.savedOutlineWidth || layout.outlineWidth;
  }, [layout]);

  /**
   * Save current outline width before collapsing
   * Called when user clicks collapse button
   */
  const saveCurrentWidth = useCallback(() => {
    setLayout(prev => ({
      ...prev,
      savedOutlineWidth: prev.outlineWidth,
    }));
  }, []);

  /**
   * Clear saved width after expand (optional, for cleanup)
   */
  const clearSavedWidth = useCallback(() => {
    setLayout(prev => ({
      ...prev,
      savedOutlineWidth: undefined,
    }));
  }, []);

  /**
   * Restore default layout
   * Called on double-click of resize handle
   */
  const restoreDefaultLayout = useCallback(() => {
    setLayout(prev => ({
      outlineWidth: LAYOUT_CONFIG.OUTLINE_DEFAULT_SIZE,
      savedOutlineWidth: prev.savedOutlineWidth, // Preserve saved width for future expand
    }));
  }, []);

  /**
   * Get layout array for react-resizable-panels
   * Format: [outlineWidth%, editorWidth%]
   *
   * @param isCollapsed - Whether outline tree is collapsed
   * @returns Layout array with outline and editor widths
   */
  const getLayoutArray = useCallback(
    (isCollapsed: boolean): number[] => {
      const outlineWidth = isCollapsed
        ? LAYOUT_CONFIG.OUTLINE_COLLAPSED_SIZE
        : getOutlineWidth();
      const editorWidth = 100 - outlineWidth;
      return [outlineWidth, editorWidth];
    },
    [getOutlineWidth],
  );

  return {
    layout,
    handleLayoutChange,
    getOutlineWidth,
    saveCurrentWidth,
    clearSavedWidth,
    restoreDefaultLayout,
    getLayoutArray,
    config: LAYOUT_CONFIG,
  };
};
