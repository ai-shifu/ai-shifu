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
  queuedCalls: [] as Array<{ args: any[] }>,
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
  if (identifyState.queuedCalls.length === 0) {
    return;
  }

  const queued = identifyState.queuedCalls.slice();
  identifyState.queuedCalls = [];
  queued.forEach(({ args }) => {
    try {
      umami.track(...args);
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

export const flushUmamiIdentify = () => {
  if (typeof window === 'undefined') {
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

export const tracking = async (eventName, eventData) => {
  try {
    ensureIdentifyReady();
    const umami = (window as any).umami;
    if (!umami || !identifyState.ready) {
      identifyState.queuedCalls.push({ args: [eventName, eventData] });
      return;
    }
    umami.track(eventName, eventData);
  } catch {
    // swallow tracking errors
  }
};

export const trackPageview = () => {
  try {
    ensureIdentifyReady();
    const umami = (window as any).umami;
    if (!umami || !identifyState.ready) {
      identifyState.queuedCalls.push({ args: [] });
      return;
    }
    umami.track();
  } catch {
    // swallow tracking errors
  }
};
