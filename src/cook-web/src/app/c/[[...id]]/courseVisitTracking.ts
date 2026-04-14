const COURSE_VISIT_EVENT_PREFIX = 'course_visit_';

const normalizeCourseVisitId = (value: string) =>
  String(value || '')
    .trim()
    .replace(/[^a-zA-Z0-9_-]/g, '_');

export const buildCourseVisitEventName = (shifuBid: string) => {
  const normalized = normalizeCourseVisitId(shifuBid);
  if (!normalized) {
    return COURSE_VISIT_EVENT_PREFIX.slice(0, -1);
  }

  const suffixLimit = Math.max(1, 50 - COURSE_VISIT_EVENT_PREFIX.length);
  return `${COURSE_VISIT_EVENT_PREFIX}${normalized.slice(0, suffixLimit)}`;
};

export const buildCourseVisitSessionKey = (shifuBid: string) =>
  `course_visit:${normalizeCourseVisitId(shifuBid)}`;

type SessionStorageLike = Pick<Storage, 'getItem' | 'setItem'>;

type TrackCourseVisitParams = {
  initialized: boolean;
  isLoggedIn: boolean;
  previewMode: boolean;
  shifuBid: string;
  entryType: 'catalog' | 'deep_link';
  storage?: SessionStorageLike | null;
  trackEvent: (
    eventName: string,
    eventData?: Record<string, unknown>,
  ) => Promise<void> | void;
};

export const trackCourseVisitIfNeeded = async ({
  initialized,
  isLoggedIn,
  previewMode,
  shifuBid,
  entryType,
  storage,
  trackEvent,
}: TrackCourseVisitParams): Promise<boolean> => {
  const normalizedShifuBid = normalizeCourseVisitId(shifuBid);
  if (!initialized || !isLoggedIn || previewMode || !normalizedShifuBid) {
    return false;
  }

  const sessionKey = buildCourseVisitSessionKey(normalizedShifuBid);
  let shouldTrack = true;

  if (storage) {
    try {
      shouldTrack = !storage.getItem(sessionKey);
    } catch {
      shouldTrack = true;
    }
  }

  if (!shouldTrack) {
    return false;
  }

  try {
    await trackEvent(buildCourseVisitEventName(normalizedShifuBid), {
      shifu_bid: normalizedShifuBid,
      entry_type: entryType,
      preview_mode: false,
    });
  } catch {
    return false;
  }

  if (storage) {
    try {
      storage.setItem(sessionKey, '1');
    } catch {
      // Ignore storage write failures after a successful emit.
    }
  }

  return true;
};
