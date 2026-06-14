import type { LearningMode } from './learningModeOptions';
import { getDocumentFullscreenElement } from '@/c-utils/browserFullscreen';

const MODE_QUERY_PARAM = 'mode';
const LEGACY_LISTEN_QUERY_PARAM = 'listen';
type BrowserFullscreenElement = HTMLElement & {
  webkitRequestFullscreen?: HTMLElement['requestFullscreen'];
};

export const parseLearningModeQueryParam = (
  value?: string,
): LearningMode | null => {
  const normalizedValue = String(value || '')
    .trim()
    .toLowerCase();

  if (
    normalizedValue === 'read' ||
    normalizedValue === 'listen' ||
    normalizedValue === 'classroom'
  ) {
    return normalizedValue;
  }

  return null;
};

const replaceCurrentUrl = (url: URL) => {
  if (typeof window === 'undefined') {
    return;
  }

  window.history.replaceState(
    window.history.state,
    '',
    `${url.pathname}${url.search}${url.hash}`,
  );
};

export const enableClassroomModeInUrl = () => {
  if (typeof window === 'undefined') {
    return;
  }

  const url = new URL(window.location.href);
  url.searchParams.set(MODE_QUERY_PARAM, 'classroom');
  url.searchParams.delete('preview');
  url.searchParams.delete(LEGACY_LISTEN_QUERY_PARAM);
  replaceCurrentUrl(url);
};

export const requestClassroomBrowserFullscreen = async (
  targetElement?: HTMLElement,
) => {
  if (typeof document === 'undefined') {
    return false;
  }

  if (getDocumentFullscreenElement()) {
    return true;
  }

  const fullscreenElement = (targetElement ??
    document.documentElement) as BrowserFullscreenElement;
  const requestFullscreen =
    fullscreenElement.requestFullscreen ??
    fullscreenElement.webkitRequestFullscreen;

  if (!requestFullscreen) {
    return false;
  }

  try {
    await requestFullscreen.call(fullscreenElement);
    return true;
  } catch {
    return false;
  }
};

export const clearClassroomModeFromUrl = () => {
  if (typeof window === 'undefined') {
    return;
  }

  const url = new URL(window.location.href);
  if (url.searchParams.get(MODE_QUERY_PARAM) !== 'classroom') {
    return;
  }

  url.searchParams.delete(MODE_QUERY_PARAM);
  replaceCurrentUrl(url);
};
