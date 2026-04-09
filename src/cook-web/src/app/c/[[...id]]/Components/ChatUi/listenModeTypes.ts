export type ListenMobileViewMode = 'nonFullscreen' | 'fullscreen';

export type ListenMobileViewModeChangeHandler = (
  viewMode: ListenMobileViewMode,
) => void;
