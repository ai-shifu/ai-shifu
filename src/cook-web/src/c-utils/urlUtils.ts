export const parseUrlParams = () => {
  return getQueryParams(window.location.href);
};

const LESSON_ID_QUERY_KEY = 'lessonid';
const FALLBACK_URL_ORIGIN = 'https://placeholder.local';

type QueryParamReader = {
  get: (key: string) => string | null;
};

export const getTrimmedQueryParam = (
  params: QueryParamReader | null | undefined,
  key: string,
) => {
  const value = params?.get(key);
  return value ? value.trim() : '';
};

export const getLessonIdFromQuery = (
  params: QueryParamReader | null | undefined,
) => {
  return getTrimmedQueryParam(params, LESSON_ID_QUERY_KEY);
};

const createUrl = (url: string) => {
  return new URL(url, FALLBACK_URL_ORIGIN);
};

const toRelativeUrl = (urlObj: URL) => {
  return `${urlObj.pathname}${urlObj.search}${urlObj.hash}`;
};

export const buildUrlWithQueryParam = (
  url: string,
  key: string,
  value: string | null | undefined,
) => {
  const urlObj = createUrl(url);
  const trimmedValue = value?.trim() || '';

  if (trimmedValue) {
    urlObj.searchParams.set(key, trimmedValue);
  } else {
    urlObj.searchParams.delete(key);
  }

  return toRelativeUrl(urlObj);
};

export const buildUrlWithLessonId = (
  url: string,
  lessonId: string | null | undefined,
) => {
  return buildUrlWithQueryParam(url, LESSON_ID_QUERY_KEY, lessonId);
};

export const replaceCurrentUrlWithLessonId = (
  lessonId: string | null | undefined,
) => {
  if (typeof window === 'undefined') {
    return;
  }

  const nextUrl = buildUrlWithLessonId(window.location.href, lessonId);
  const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;

  if (currentUrl === nextUrl) {
    return;
  }

  // Keep the current page state shareable without creating extra history entries.
  window.history.replaceState(window.history.state, '', nextUrl);
};

export function getQueryParams(url) {
  const params = {};
  const queryString = url.split('?')[1];
  if (queryString) {
    queryString.split('&').forEach(param => {
      const [key, value] = param.split('=');
      params[key] = decodeURIComponent(value);
    });
  }
  return params;
}

// remove some query params from url
export const removeParamFromUrl = (url, paramsToRemove) => {
  const urlObj = new URL(url);
  const searchParams = urlObj.searchParams;

  for (const paramToRemove of paramsToRemove) {
    searchParams.delete(paramToRemove);
  }

  return urlObj.toString();
};

export const buildLoginRedirectPath = (url: string) => {
  const urlObj = new URL(url);
  urlObj.searchParams.delete('code');
  urlObj.searchParams.delete('state');
  return urlObj.pathname + urlObj.search;
};

/**
 * Detects the branded host domain from the current page URL.
 * Returns 'ai-shifu.cn', 'ai-shifu.com', or null for unknown hosts.
 * Covers bare domains, subdomains, and localhost (mapped to ai-shifu.cn).
 */
export const getHostDomain = (): 'ai-shifu.cn' | 'ai-shifu.com' | null => {
  if (typeof window === 'undefined') return null;
  const hostname = window.location.hostname;
  if (
    hostname === 'ai-shifu.cn' ||
    hostname.endsWith('.ai-shifu.cn') ||
    hostname === 'localhost'
  ) {
    return 'ai-shifu.cn';
  }
  if (hostname === 'ai-shifu.com' || hostname.endsWith('.ai-shifu.com')) {
    return 'ai-shifu.com';
  }
  return null;
};

/**
 * Returns the absolute URL to the payment agreement page for the current domain,
 * or null when the domain cannot be detected (graceful degradation: hide the checkbox).
 */
export const getPaymentAgreementUrl = (): string | null => {
  const domain = getHostDomain();
  return domain ? `https://${domain}/payment-agreement.html` : null;
};

const COURSE_CREATOR_URLS: Record<'ai-shifu.cn' | 'ai-shifu.com', string> = {
  'ai-shifu.cn':
    'https://app.ai-shifu.cn/c/ed0e57ded79d4b7b88d1be348c151509?lessonid=77ff6ea94e4245d19172a29c0a279848',
  'ai-shifu.com': 'https://ai-shifu.com/educators.html#course-creator-skill',
};

export const getCourseCreatorUrl = (): string | null => {
  const domain = getHostDomain();
  return domain ? COURSE_CREATOR_URLS[domain] : null;
};
