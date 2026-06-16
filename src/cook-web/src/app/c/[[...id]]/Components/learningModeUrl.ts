import type { LearningMode } from './learningModeOptions';
import { getDocumentFullscreenElement } from '@/c-utils/browserFullscreen';

const MODE_QUERY_PARAM = 'mode';
const LEGACY_LISTEN_QUERY_PARAM = 'listen';
type BrowserFullscreenElement = HTMLElement & {
  webkitRequestFullscreen?: HTMLElement['requestFullscreen'];
};

export const parseBooleanQueryParam = (value?: string) => {
  if (typeof value !== 'string') {
    return null;
  }

  const normalizedValue = value.trim().toLowerCase();
  if (normalizedValue === 'true' || normalizedValue === '1') {
    return true;
  }
  if (normalizedValue === 'false' || normalizedValue === '0') {
    return false;
  }

  return null;
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

export const setLearningModeInUrl = (mode: LearningMode) => {
  if (typeof window === 'undefined') {
    return;
  }

  const url = new URL(window.location.href);
  url.searchParams.set(MODE_QUERY_PARAM, mode);
  url.searchParams.delete(LEGACY_LISTEN_QUERY_PARAM);
  replaceCurrentUrl(url);
};

export const normalizeLegacyListenModeInUrl = ({
  listenModeParam,
  urlModeParam,
}: {
  listenModeParam: boolean | null;
  urlModeParam: LearningMode | null;
}) => {
  if (urlModeParam || listenModeParam === null) {
    return;
  }

  setLearningModeInUrl(listenModeParam ? 'listen' : 'read');
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
