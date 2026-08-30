export const EVENT_NAMES = {
  TRIAL_PROGRESS: 'trial_progress',
  POP_PAY: 'pop_pay',
  POP_LOGIN: 'pop_login',
  PAY_SUCCEED: 'pay_succeed',
  NAV_BOTTOM_BEIAN: 'nav_bottom_beian',
  NAV_BOTTOM_SKIN: 'nav_bottom_skin',
  NAV_BOTTOM_SETTING: 'nav_bottom_setting',
  NAV_TOP_LOGO: 'nav_top_logo',
  NAV_TOP_EXPAND: 'nav_top_expand',
  NAV_TOP_COLLAPSE: 'nav_top_collapse',
  NAV_SECTION_SWITCH: 'nav_section_switch',
  RESET_CHAPTER: 'reset_chapter',
  RESET_CHAPTER_CONFIRM: 'reset_chapter_confirm',
  USER_MENU: 'user_menu',
  USER_MENU_BASIC_INFO: 'user_menu_basic_info',
  USER_MENU_PERSONALIZED: 'user_menu_personalized',
  USER_MENU_SET_PASSWORD: 'user_menu_set_password',
  LESSON_FEEDBACK_SUBMIT: 'lesson_feedback_submit',
  LESSON_FEEDBACK_SKIP: 'lesson_feedback_skip',
  // Device authorization: an asynchronous workflow, so the exposure and both
  // terminal outcomes are tracked. One signal alone could not tell an ignored
  // prompt apart from a rejected one.
  DEVICE_AUTH_PROMPT_SHOWN: 'device_auth_prompt_shown',
  DEVICE_AUTH_APPROVED: 'device_auth_approved',
  DEVICE_AUTH_DENIED: 'device_auth_denied',
  // Session management: ending a session is the meaningful outcome here.
  SESSION_LIST_OPENED: 'session_list_opened',
  SESSION_REVOKED: 'session_revoked',
  SESSION_REVOKED_OTHERS: 'session_revoked_others',
};

type UmamiUserInfo = {
  user_id?: string;
  [key: string]: unknown;
};

type UmamiEventData = Record<string, unknown>;
type SanitizedEventData = Record<string, string | number | boolean>;

type IdentifyRequest = {
  generation: number;
  userId: string;
};

type QueuedUmamiCall =
  | {
      kind: 'event';
      eventName: string;
      eventData: SanitizedEventData;
      url?: string;
      referrer?: string;
    }
  | { kind: 'pageview'; url?: string; referrer?: string };

const UMAMI_LIMITS = {
  eventName: 50,
  dataKey: 64,
  dataValue: 240,
  dataJson: 1024,
  url: 500,
  referrer: 500,
  maxDataFields: 30,
  maxRouteSegments: 8,
  maxQueuedCalls: 100,
} as const;

const pageviewState = {
  lastSourcePath: '',
  lastTrackedRoute: '',
  lastReferrer: '',
};

const identifyState = {
  pendingRequest: undefined as IdentifyRequest | undefined,
  prevSnapshot: '',
  ready: false,
  identifying: false,
  generation: 0,
  queuedCalls: [] as QueuedUmamiCall[],
};

const truncateText = (value: string, maxLength: number) => {
  if (value.length <= maxLength) {
    return value;
  }
  return value.slice(0, maxLength);
};

const buildUserSnapshot = (userId: string) =>
  JSON.stringify({ user_id: userId });

const SAFE_ROUTE_SEGMENTS = new Set([
  'admin',
  'agreement',
  'billing',
  'billing-result',
  'c',
  'config',
  'credit-notifications',
  'dashboard',
  'follow-ups',
  'google-callback',
  'history',
  'invite',
  'login',
  'operations',
  'orders',
  'payment',
  'privacy',
  'profile-onboarding',
  'promotions',
  'provider-prices',
  'ratings',
  'referral',
  'referrals',
  'result',
  'shifu',
  'stripe',
  'unsupported-browser',
  'users',
  'voice-clones',
]);

const STATIC_OPERATION_ROUTES = new Set([
  'billing',
  'config',
  'credit-notifications',
  'orders',
  'profile-onboarding',
  'promotions',
  'provider-prices',
  'referrals',
  'users',
  'voice-clones',
]);

const isKnownDynamicRouteSegment = (
  segments: string[],
  segmentIndex: number,
) => {
  const firstSegment = segments[0]?.toLowerCase();
  if (firstSegment === 'invite' || firstSegment === 'shifu') {
    return segmentIndex === 1;
  }

  if (firstSegment !== 'admin') {
    return false;
  }

  const secondSegment = segments[1]?.toLowerCase();
  if (secondSegment === 'dashboard') {
    return segmentIndex === 2;
  }

  if (secondSegment !== 'operations') {
    return false;
  }

  const thirdSegment = segments[2]?.toLowerCase();
  if (!thirdSegment) {
    return false;
  }
  if (segmentIndex === 2) {
    return !STATIC_OPERATION_ROUTES.has(thirdSegment);
  }

  return thirdSegment === 'users' && segmentIndex === 3;
};

const getUrlPathname = (url?: string) => {
  const fallbackUrl =
    typeof window === 'undefined' ? '' : window.location.href || '';
  const candidate =
    typeof url === 'string' && url.trim() ? url.trim() : fallbackUrl;
  if (!candidate) {
    return '';
  }

  try {
    return new URL(candidate, 'https://tracking.invalid').pathname || '/';
  } catch {
    const withoutFragment = candidate.split('#', 1)[0] ?? '';
    const withoutQuery = withoutFragment.split('?', 1)[0] ?? '';
    return withoutQuery.startsWith('/') ? withoutQuery : '/';
  }
};

const normalizeSourcePath = (url?: string) => {
  const pathname = getUrlPathname(url).replace(/\/{2,}/g, '/');
  return truncateText(pathname || '/', UMAMI_LIMITS.url);
};

/**
 * Converts a browser URL into a bounded analytics route. Only reviewed static
 * route segments survive; dynamic and unknown values become `:dynamic`.
 * Course catch-all values are collapsed completely. Host, credentials, query,
 * fragment, and browser/external referrer data never enter the result.
 */
export const normalizeTrackingRoute = (url?: string): string => {
  const pathname = normalizeSourcePath(url);
  const rawSegments = pathname.split('/').filter(Boolean);
  if (rawSegments.length === 0) {
    return '/';
  }

  if (rawSegments[0]?.toLowerCase() === 'c') {
    return rawSegments.length === 1 ? '/c' : '/c/:dynamic';
  }

  const hasOverflow = rawSegments.length > UMAMI_LIMITS.maxRouteSegments;
  const segmentLimit = hasOverflow
    ? UMAMI_LIMITS.maxRouteSegments - 1
    : UMAMI_LIMITS.maxRouteSegments;
  const normalizedSegments = rawSegments
    .slice(0, segmentLimit)
    .map((segment, index) => {
      if (isKnownDynamicRouteSegment(rawSegments, index)) {
        return ':dynamic';
      }
      const normalized = segment.toLowerCase();
      return SAFE_ROUTE_SEGMENTS.has(normalized) ? normalized : ':dynamic';
    });
  if (hasOverflow) {
    normalizedSegments.push(':more');
  }

  return truncateText(`/${normalizedSegments.join('/')}`, UMAMI_LIMITS.url);
};

const getCurrentUrl = () => {
  return normalizeTrackingRoute();
};

const normalizeText = (value: unknown, maxLength: number) => {
  if (value === null || value === undefined) {
    return '';
  }

  const text = String(value).trim();
  if (!text) {
    return '';
  }

  return truncateText(text, maxLength);
};

const sanitizeDataValue = (
  value: unknown,
): string | number | boolean | undefined => {
  if (typeof value === 'string') {
    return truncateText(value, UMAMI_LIMITS.dataValue);
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined;
  }

  if (typeof value === 'boolean') {
    return value;
  }

  return undefined;
};

const sanitizeEventData = (
  eventData: UmamiEventData | undefined,
): SanitizedEventData => {
  if (!eventData || typeof eventData !== 'object' || Array.isArray(eventData)) {
    return {};
  }

  const safeData: SanitizedEventData = {};
  const entries = Object.entries(eventData).slice(
    0,
    UMAMI_LIMITS.maxDataFields,
  );

  for (const [rawKey, rawValue] of entries) {
    const key = normalizeText(rawKey, UMAMI_LIMITS.dataKey);
    if (!key) {
      continue;
    }
    const value = sanitizeDataValue(rawValue);
    if (value === undefined) {
      continue;
    }
    const nextData = { ...safeData, [key]: value };
    if (JSON.stringify(nextData).length > UMAMI_LIMITS.dataJson) {
      continue;
    }
    safeData[key] = value;
  }

  return safeData;
};

const sanitizeUrlLike = (url: string | undefined, maxLength: number) => {
  if (typeof url !== 'string' || !url.trim()) {
    return undefined;
  }
  const normalized = truncateText(normalizeTrackingRoute(url), maxLength);
  return normalized || undefined;
};

const sanitizeEventName = (eventName: unknown): string => {
  return normalizeText(eventName, UMAMI_LIMITS.eventName) || 'unknown_event';
};

function trackUmamiPageview(
  umami: any,
  { url, referrer }: { url?: string; referrer?: string } = {},
) {
  const resolvedUrl =
    typeof url === 'string' && url.trim() ? url : getCurrentUrl();
  const safeUrl = sanitizeUrlLike(resolvedUrl, UMAMI_LIMITS.url);
  const safeReferrer = sanitizeUrlLike(referrer, UMAMI_LIMITS.referrer);

  if (!safeUrl) {
    return;
  }

  try {
    umami.track((payload: any) => ({
      ...payload,
      url: safeUrl,
      referrer: safeReferrer,
      title: undefined,
    }));
  } catch {
    // Do not fall back to auto-context tracking because it can restore the
    // browser's raw URL, referrer, and document title.
  }
}

function trackUmamiEvent(
  umami: any,
  {
    eventName,
    eventData,
    url,
    referrer,
  }: {
    eventName: string;
    eventData: SanitizedEventData;
    url?: string;
    referrer?: string;
  },
) {
  const resolvedUrl =
    typeof url === 'string' && url.trim() ? url : getCurrentUrl();
  const safeUrl = sanitizeUrlLike(resolvedUrl, UMAMI_LIMITS.url);
  const safeReferrer = sanitizeUrlLike(referrer, UMAMI_LIMITS.referrer);

  try {
    umami.track((payload: any) => ({
      ...payload,
      name: eventName,
      data: eventData,
      url: safeUrl,
      referrer: safeReferrer,
      title: undefined,
    }));
  } catch {
    // The legacy overload rehydrates unsafe browser context, so delivery is
    // intentionally skipped when the privacy-safe callback path is unavailable.
  }
}

const drainQueuedEvents = (umami: any) => {
  if (identifyState.queuedCalls.length === 0) {
    return;
  }

  const queued = identifyState.queuedCalls.slice();
  identifyState.queuedCalls = [];
  queued.forEach(item => {
    try {
      if (item.kind === 'pageview') {
        trackUmamiPageview(umami, { url: item.url, referrer: item.referrer });
      } else {
        trackUmamiEvent(umami, {
          eventName: item.eventName,
          eventData: item.eventData,
          url: item.url,
          referrer: item.referrer,
        });
      }
    } catch {
      // swallow tracking errors
    }
  });
};

const enforceQueueLimit = () => {
  while (identifyState.queuedCalls.length > UMAMI_LIMITS.maxQueuedCalls) {
    const oldestEventIndex = identifyState.queuedCalls.findIndex(
      call => call.kind === 'event',
    );
    identifyState.queuedCalls.splice(
      oldestEventIndex >= 0 ? oldestEventIndex : 0,
      1,
    );
  }
};

const enqueueEvent = (event: Extract<QueuedUmamiCall, { kind: 'event' }>) => {
  identifyState.queuedCalls.push(event);
  enforceQueueLimit();
};

const enqueuePageview = (
  pageview: Extract<QueuedUmamiCall, { kind: 'pageview' }>,
) => {
  identifyState.queuedCalls = identifyState.queuedCalls.filter(
    call => call.kind !== 'pageview',
  );
  identifyState.queuedCalls.unshift(pageview);
  enforceQueueLimit();
};

const applyIdentify = async (request: IdentifyRequest) => {
  const umami = (window as any).umami;
  if (!umami) {
    return false;
  }

  if (typeof umami.identify !== 'function') {
    return false;
  }

  try {
    await umami.identify(request.userId);
  } catch {
    return false;
  }

  return true;
};

export const flushUmamiIdentify = () => {
  if (typeof window === 'undefined') {
    return;
  }

  if (identifyState.pendingRequest === undefined) {
    const umami = (window as any).umami;
    if (identifyState.ready && umami) {
      drainQueuedEvents(umami);
    }
    return;
  }

  if (identifyState.identifying) {
    return;
  }

  const request = identifyState.pendingRequest;
  identifyState.identifying = true;
  void applyIdentify(request)
    .then(success => {
      const isNewestRequest =
        identifyState.pendingRequest?.generation === request.generation;
      if (!success || !isNewestRequest) {
        return;
      }

      identifyState.pendingRequest = undefined;
      identifyState.ready = true;
      const umami = (window as any).umami;
      if (umami) {
        drainQueuedEvents(umami);
      }
    })
    .finally(() => {
      identifyState.identifying = false;
      if (
        identifyState.pendingRequest &&
        identifyState.pendingRequest.generation !== request.generation
      ) {
        flushUmamiIdentify();
      }
    });
};

export const identifyUmamiUser = (userInfo?: UmamiUserInfo | null) => {
  if (typeof window === 'undefined') {
    return;
  }

  if (userInfo === undefined) {
    return;
  }

  if (userInfo === null) {
    return;
  }

  const userId =
    typeof userInfo.user_id === 'string' ? userInfo.user_id.trim() : '';
  if (!userId) {
    return;
  }

  const snapshot = buildUserSnapshot(userId);
  if (snapshot === identifyState.prevSnapshot) {
    return;
  }

  const isReplacementIdentity = identifyState.prevSnapshot !== '';

  // Business events accepted while another identity was pending must never be
  // replayed under the replacement identity. Preserve only a pending current
  // pageview, and remove the previous identity's navigation context from it.
  // A pageview that already drained is not re-created here.
  const currentPageview = identifyState.queuedCalls.find(
    call => call.kind === 'pageview',
  );
  identifyState.queuedCalls = currentPageview
    ? [
        isReplacementIdentity
          ? { ...currentPageview, referrer: undefined }
          : currentPageview,
      ]
    : [];
  if (isReplacementIdentity) {
    pageviewState.lastReferrer = '';
  }
  identifyState.prevSnapshot = snapshot;
  identifyState.ready = false;
  identifyState.generation += 1;
  identifyState.pendingRequest = {
    generation: identifyState.generation,
    userId,
  };
  flushUmamiIdentify();
};

const ensureIdentifyReady = () => {
  if (typeof window === 'undefined') {
    return;
  }

  if (identifyState.ready) {
    return;
  }

  if (identifyState.pendingRequest === undefined) {
    return;
  }

  flushUmamiIdentify();
};

export const tracking = async (
  eventName: unknown,
  eventData: UmamiEventData = {},
) => {
  try {
    ensureIdentifyReady();
    const umami = (window as any).umami;
    const urlSnapshot = pageviewState.lastTrackedRoute || getCurrentUrl();
    const referrerSnapshot = pageviewState.lastReferrer || '';
    const safeEventName = sanitizeEventName(eventName);
    const safeEventData = sanitizeEventData(eventData);
    const safeUrl = sanitizeUrlLike(urlSnapshot, UMAMI_LIMITS.url);
    const safeReferrer = sanitizeUrlLike(
      referrerSnapshot,
      UMAMI_LIMITS.referrer,
    );
    if (!umami || !identifyState.ready) {
      enqueueEvent({
        kind: 'event',
        eventName: safeEventName,
        eventData: safeEventData,
        url: safeUrl,
        referrer: safeReferrer,
      });
      return;
    }
    trackUmamiEvent(umami, {
      eventName: safeEventName,
      eventData: safeEventData,
      url: safeUrl,
      referrer: safeReferrer,
    });
  } catch {
    // swallow tracking errors
  }
};

export const trackPageview = (url?: string) => {
  try {
    ensureIdentifyReady();
    const umami = (window as any).umami;
    const sourcePath = normalizeSourcePath(url);
    const routeSnapshot = normalizeTrackingRoute(url);

    if (sourcePath && sourcePath === pageviewState.lastSourcePath) {
      return;
    }

    const previousRoute = pageviewState.lastTrackedRoute;

    if (sourcePath) {
      pageviewState.lastSourcePath = sourcePath;
      pageviewState.lastReferrer = previousRoute;
      pageviewState.lastTrackedRoute = routeSnapshot;
    }

    if (!umami || !identifyState.ready) {
      const pageviewCall: QueuedUmamiCall = {
        kind: 'pageview',
        url: sanitizeUrlLike(routeSnapshot, UMAMI_LIMITS.url),
        referrer: sanitizeUrlLike(previousRoute, UMAMI_LIMITS.referrer),
      };
      enqueuePageview(pageviewCall);
      return;
    }
    trackUmamiPageview(umami, {
      url: routeSnapshot,
      referrer: previousRoute,
    });
  } catch {
    // swallow tracking errors
  }
};
