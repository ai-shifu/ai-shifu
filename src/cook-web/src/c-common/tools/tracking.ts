export const EVENT_NAMES = {
  VISIT: 'visit',
  TRIAL_PROGRESS: 'trial_progress',
  BLOCK_VIEW: 'learner_block_view',
  LESSON_COMPLETE: 'learner_lesson_complete',
  AI_INTERACTION: 'learner_ai_interaction',
  LANGUAGE_SWITCH: 'learner_language_switch',
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
  RESET_CHAPTER: 'learner_chapter_reset_click',
  RESET_CHAPTER_CONFIRM: 'learner_chapter_reset_confirm',
  USER_MENU: 'user_menu',
  USER_MENU_BASIC_INFO: 'user_menu_basic_info',
  USER_MENU_PERSONALIZED: 'user_menu_personalized',
};

type UmamiUserInfo = {
  user_id?: string;
  name?: string;
  state?: string;
  language?: string;
};

type QueuedUmamiCall =
  | {
      kind: 'event';
      eventName: any;
      eventData: any;
      url?: string;
      referrer?: string;
    }
  | { kind: 'pageview'; url?: string; referrer?: string };

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

function trackUmamiPageview(
  umami: any,
  { url, referrer }: { url?: string; referrer?: string } = {},
) {
  const resolvedUrl =
    typeof url === 'string' && url.trim() ? url : getCurrentUrl();

  if (!resolvedUrl) {
    umami.track();
    return;
  }

  try {
    umami.track((payload: any) => ({
      ...payload,
      url: resolvedUrl,
      referrer: referrer || payload.referrer,
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
  }: { eventName: any; eventData: any; url?: string; referrer?: string },
) {
  const resolvedUrl =
    typeof url === 'string' && url.trim() ? url : getCurrentUrl();

  try {
    umami.track((payload: any) => ({
      ...payload,
      name: eventName,
      data: eventData,
      url: resolvedUrl || payload.url,
      referrer: referrer || payload.referrer,
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
  eventName: string,
  eventData: Record<string, any>,
) => {
  try {
    ensureCurrentPageviewTracked();
    ensureIdentifyReady();
    const umami = (window as any).umami;
    const urlSnapshot = pageviewState.lastTrackedUrl || getCurrentUrl();
    const referrerSnapshot = pageviewState.lastReferrer || '';
    if (!umami || !identifyState.ready) {
      identifyState.queuedCalls.push({
        kind: 'event',
        eventName,
        eventData,
        url: urlSnapshot,
        referrer: referrerSnapshot,
      });
      return;
    }
    trackUmamiEvent(umami, {
      eventName,
      eventData,
      url: urlSnapshot,
      referrer: referrerSnapshot,
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
        url: urlSnapshot,
        referrer: previousUrl,
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
