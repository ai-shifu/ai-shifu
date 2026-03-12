export const EVENT_NAMES = {
  VISIT: 'visit',
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
};

type UmamiUserInfo = {
  user_id?: string;
  name?: string;
  state?: string;
  language?: string;
};

type UmamiEventData = Record<string, unknown>;
type SanitizedEventData = Record<string, string | number | boolean>;

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
  maxArrayItems: 10,
} as const;

const pageviewState = {
  lastTrackedUrl: '',
  lastReferrer: '',
};

const identifyState = {
  pendingUserInfo: undefined as UmamiUserInfo | null | undefined,
  prevSnapshot: '',
  ready: false,
  identifying: false,
  queuedCalls: [] as QueuedUmamiCall[],
};

const buildUserSnapshot = (userInfo: UmamiUserInfo | null) => {
  return JSON.stringify({
    user_id: userInfo?.user_id ?? null,
    name: userInfo?.name ?? null,
    state: userInfo?.state ?? null,
    language: userInfo?.language ?? null,
  });
};

const getCurrentUrl = () => {
  if (typeof window === 'undefined') {
    return '';
  }

  const origin = window.location.origin || '';
  const pathname = window.location.pathname || '';
  const search = window.location.search || '';
  return `${origin}${pathname}${search}`;
};

const truncateText = (value: string, maxLength: number) => {
  if (value.length <= maxLength) {
    return value;
  }
  return value.slice(0, maxLength);
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

const stringifyUnknown = (value: unknown) => {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

const sanitizeDataValue = (value: unknown): string | number | boolean => {
  if (typeof value === 'string') {
    return truncateText(value, UMAMI_LIMITS.dataValue);
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : 0;
  }

  if (typeof value === 'boolean') {
    return value;
  }

  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) {
      return '';
    }
    return truncateText(value.toISOString(), UMAMI_LIMITS.dataValue);
  }

  if (value === null || value === undefined) {
    return '';
  }

  if (Array.isArray(value)) {
    return truncateText(
      stringifyUnknown(value.slice(0, UMAMI_LIMITS.maxArrayItems)),
      UMAMI_LIMITS.dataValue,
    );
  }

  if (typeof value === 'object') {
    return truncateText(stringifyUnknown(value), UMAMI_LIMITS.dataValue);
  }

  return truncateText(String(value), UMAMI_LIMITS.dataValue);
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
    const nextData = { ...safeData, [key]: value };
    if (JSON.stringify(nextData).length > UMAMI_LIMITS.dataJson) {
      break;
    }
    safeData[key] = value;
  }

  return safeData;
};

const sanitizeUrlLike = (url: string | undefined, maxLength: number) => {
  const normalized = normalizeText(url, maxLength);
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
    umami.track();
    return;
  }

  try {
    umami.track((payload: any) => ({
      ...payload,
      url: safeUrl,
      referrer: safeReferrer || payload.referrer,
    }));
  } catch {
    umami.track();
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
      url: safeUrl || payload.url,
      referrer: safeReferrer || payload.referrer,
    }));
  } catch {
    umami.track(eventName, eventData);
  }
}

const ensureCurrentPageviewTracked = () => {
  const currentUrl = getCurrentUrl();
  if (!currentUrl || currentUrl === pageviewState.lastTrackedUrl) {
    return;
  }

  trackPageview(currentUrl);
};

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

const applyIdentify = async (userInfo: UmamiUserInfo | null) => {
  const umami = (window as any).umami;
  if (!umami) {
    return false;
  }

  if (typeof umami.identify !== 'function') {
    identifyState.ready = true;
    drainQueuedEvents(umami);
    return true;
  }

  const uniqueId =
    typeof userInfo?.user_id === 'string' && userInfo.user_id.trim()
      ? userInfo.user_id.trim()
      : undefined;

  if (!uniqueId) {
    return false;
  }

  try {
    const sessionData: {
      nickname?: string;
      user_state?: string;
      language?: string;
    } = {};

    if (userInfo?.name) sessionData.nickname = userInfo.name;
    if (userInfo?.state) sessionData.user_state = userInfo.state;
    if (userInfo?.language) sessionData.language = userInfo.language;

    const hasSessionData = Object.keys(sessionData).length > 0;

    if (hasSessionData) {
      await umami.identify(uniqueId, sessionData);
    } else {
      await umami.identify(uniqueId);
    }
  } catch {
    return false;
  }

  identifyState.ready = true;
  drainQueuedEvents(umami);
  return true;
};

export const flushUmamiIdentify = () => {
  if (typeof window === 'undefined') {
    return;
  }

  if (identifyState.pendingUserInfo === undefined) {
    return;
  }

  if (identifyState.identifying) {
    return;
  }

  identifyState.identifying = true;
  void applyIdentify(identifyState.pendingUserInfo)
    .then(success => {
      if (success) {
        identifyState.pendingUserInfo = undefined;
      }
    })
    .finally(() => {
      identifyState.identifying = false;
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

  if (userInfo && !userInfo.user_id) {
    return;
  }

  const snapshot = buildUserSnapshot(userInfo ?? null);
  if (snapshot === identifyState.prevSnapshot) {
    return;
  }

  identifyState.prevSnapshot = snapshot;
  identifyState.ready = false;
  identifyState.pendingUserInfo = userInfo ?? null;
  flushUmamiIdentify();
};

const ensureIdentifyReady = () => {
  if (typeof window === 'undefined') {
    return;
  }

  if (identifyState.ready) {
    return;
  }

  if (identifyState.pendingUserInfo === undefined) {
    return;
  }

  flushUmamiIdentify();
};

export const tracking = async (
  eventName: unknown,
  eventData: UmamiEventData = {},
) => {
  try {
    ensureCurrentPageviewTracked();
    ensureIdentifyReady();
    const umami = (window as any).umami;
    const urlSnapshot = pageviewState.lastTrackedUrl || getCurrentUrl();
    const referrerSnapshot = pageviewState.lastReferrer || '';
    const safeEventName = sanitizeEventName(eventName);
    const safeEventData = sanitizeEventData(eventData);
    const safeUrl = sanitizeUrlLike(urlSnapshot, UMAMI_LIMITS.url);
    const safeReferrer = sanitizeUrlLike(
      referrerSnapshot,
      UMAMI_LIMITS.referrer,
    );
    if (!umami || !identifyState.ready) {
      identifyState.queuedCalls.push({
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
    const urlSnapshot =
      typeof url === 'string' && url.trim() ? url : getCurrentUrl();

    if (urlSnapshot && urlSnapshot === pageviewState.lastTrackedUrl) {
      return;
    }

    const previousUrl = pageviewState.lastTrackedUrl;

    if (urlSnapshot) {
      pageviewState.lastReferrer = previousUrl;
      pageviewState.lastTrackedUrl = urlSnapshot;
    }

    if (!umami || !identifyState.ready) {
      const pageviewCall: QueuedUmamiCall = {
        kind: 'pageview',
        url: sanitizeUrlLike(urlSnapshot, UMAMI_LIMITS.url),
        referrer: sanitizeUrlLike(previousUrl, UMAMI_LIMITS.referrer),
      };
      identifyState.queuedCalls = identifyState.queuedCalls.filter(
        call => call.kind !== 'pageview',
      );
      identifyState.queuedCalls.unshift(pageviewCall);
      return;
    }
    trackUmamiPageview(umami, { url: urlSnapshot, referrer: previousUrl });
  } catch {
    // swallow tracking errors
  }
};
