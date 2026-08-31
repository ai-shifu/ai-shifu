import type { MobileViewMode } from 'markdown-flow-ui/slide';

export const DEFAULT_LISTEN_MOBILE_VIEW_MODE: MobileViewMode = 'nonFullscreen';

export const LISTEN_MODE_VH_FALLBACK_CLASSNAME = 'listen-mode-vh-fallback';

export type ListenMobileViewModeChangeHandler = (
  viewMode: MobileViewMode,
) => void;
