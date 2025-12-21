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
};

type UmamiUserInfo = {
  user_id?: string;
  name?: string;
  state?: string;
  language?: string;
};

const identifyState = {
  pendingUserInfo: undefined as UmamiUserInfo | null | undefined,
  prevSnapshot: '',
  ready: false,
  pageviewReady: false,
  queuedEvents: [] as Array<{ eventName: string; eventData: any }>,
  queuedPageviews: 0,
};

const buildUserSnapshot = (userInfo: UmamiUserInfo | null) => {
  return JSON.stringify({
    user_id: userInfo?.user_id ?? null,
    name: userInfo?.name ?? null,
    state: userInfo?.state ?? null,
    language: userInfo?.language ?? null,
  });
};

const drainQueuedEvents = (umami: any) => {
  if (identifyState.queuedEvents.length === 0) {
    return;
  }

  const queued = identifyState.queuedEvents.slice();
  identifyState.queuedEvents = [];
  queued.forEach(({ eventName, eventData }) => {
    try {
      umami.track(eventName, eventData);
    } catch {
      // swallow tracking errors
    }
  });
};

const applyIdentify = (userInfo: UmamiUserInfo | null) => {
  const umami = (window as any).umami;
  if (!umami) {
    return false;
  }

  try {
    if (!userInfo?.user_id) {
      umami.identify(null);
    } else {
      const sessionData: {
        nickname?: string;
        user_state?: string;
        language?: string;
      } = {};

      if (userInfo.name) sessionData.nickname = userInfo.name;
      if (userInfo.state) sessionData.user_state = userInfo.state;
      if (userInfo.language) sessionData.language = userInfo.language;

      if (Object.keys(sessionData).length > 0) {
        umami.identify(userInfo.user_id, sessionData);
      } else {
        umami.identify(userInfo.user_id);
      }
    }
  } catch {
    return false;
  }

  identifyState.ready = true;
  drainQueuedEvents(umami);
  return true;
};

const sendPageview = (umami: any) => {
  try {
    umami.track();
  } catch {
    return false;
  }

  identifyState.pageviewReady = true;
  flushUmamiIdentify();
  return true;
};

export const flushUmamiPageviews = () => {
  if (typeof window === 'undefined') {
    return;
  }

  const umami = (window as any).umami;
  if (!umami) {
    return;
  }

  if (identifyState.queuedPageviews <= 0) {
    return;
  }

  const count = identifyState.queuedPageviews;
  identifyState.queuedPageviews = 0;
  for (let i = 0; i < count; i += 1) {
    try {
      umami.track();
    } catch {
      // swallow tracking errors
    }
  }

  identifyState.pageviewReady = true;
  flushUmamiIdentify();
};

export const flushUmamiIdentify = () => {
  if (typeof window === 'undefined') {
    return;
  }

  if (!identifyState.pageviewReady) {
    return;
  }

  if (identifyState.pendingUserInfo === undefined) {
    return;
  }

  if (applyIdentify(identifyState.pendingUserInfo)) {
    identifyState.pendingUserInfo = undefined;
  }
};

export const identifyUmamiUser = (userInfo?: UmamiUserInfo | null) => {
  if (typeof window === 'undefined') {
    return;
  }

  if (userInfo === undefined) {
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

export const tracking = async (eventName, eventData) => {
  try {
    const umami = (window as any).umami;
    if (!umami) {
      identifyState.queuedEvents.push({ eventName, eventData });
      return;
    }
    if (!identifyState.ready) {
      flushUmamiIdentify();
      if (!identifyState.ready) {
        identifyState.queuedEvents.push({ eventName, eventData });
        return;
      }
    }
    umami.track(eventName, eventData);
  } catch {
    // swallow tracking errors
  }
};

export const trackPageview = () => {
  try {
    const umami = (window as any).umami;
    if (!umami) {
      identifyState.queuedPageviews += 1;
      return;
    }
    if (!sendPageview(umami)) {
      identifyState.queuedPageviews += 1;
    }
  } catch {
    // swallow tracking errors
  }
};
