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

type TrackCourseVisitParams = {
  initialized: boolean;
  isLoggedIn: boolean;
  previewMode: boolean;
  shifuBid: string;
  entryType: 'catalog' | 'deep_link';
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
  trackEvent,
}: TrackCourseVisitParams): Promise<boolean> => {
  const normalizedShifuBid = normalizeCourseVisitId(shifuBid);
  if (!initialized || previewMode || !normalizedShifuBid) {
    return false;
  }

  try {
    await trackEvent(buildCourseVisitEventName(normalizedShifuBid), {
      shifu_bid: normalizedShifuBid,
      entry_type: entryType,
      auth_state: isLoggedIn ? 'logged_in' : 'guest',
      preview_mode: false,
    });
    return true;
  } catch {
    return false;
  }
};
