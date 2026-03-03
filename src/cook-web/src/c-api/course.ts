import request from '@/lib/request';
import { inWechat } from '@/c-constants/uiConstants';
import { tracking } from '@/c-common/tools/tracking';
import i18n from '@/i18n';

const COURSE_NOT_FOUND_MESSAGE_FALLBACKS = ['course not found'];
let cachedNotFoundMessages: { language: string; messages: string[] } | null =
  null;

const isHttpStatusCode = (value: unknown): value is number => {
  const code = Number(value);
  return Number.isInteger(code) && code >= 400 && code <= 599;
};

const getCourseNotFoundMessages = (): string[] => {
  const language = i18n.resolvedLanguage || i18n.language || '';
  if (cachedNotFoundMessages && cachedNotFoundMessages.language === language) {
    return cachedNotFoundMessages.messages;
  }

  const translatedCandidates = [
    i18n.t('server.shifu.shifuNotFound'),
    i18n.t('server.shifu.courseNotFound'),
  ];
  const merged = [
    ...COURSE_NOT_FOUND_MESSAGE_FALLBACKS,
    ...translatedCandidates,
  ]
    .map(item =>
      String(item || '')
        .trim()
        .toLowerCase(),
    )
    .filter(Boolean);
  const messages = Array.from(new Set(merged));
  cachedNotFoundMessages = { language, messages };
  return messages;
};

const isCourseNotFoundError = (error: any): boolean => {
  const code = Number(error?.code);
  const status = Number(error?.status);
  if (code === 4001 || code === 404 || status === 404) {
    return true;
  }
  const message = String(error?.message || '').toLowerCase();
  return getCourseNotFoundMessages().some(keyword => message.includes(keyword));
};

export class CourseInfoFetchError extends Error {
  code?: number;
  status?: number;
  isCourseNotFound: boolean;

  constructor(error: any) {
    super(error?.message || 'Failed to fetch course info');
    this.name = 'CourseInfoFetchError';
    this.code = Number.isFinite(Number(error?.code))
      ? Number(error?.code)
      : undefined;
    this.status = Number.isFinite(Number(error?.status))
      ? Number(error?.status)
      : isHttpStatusCode(error?.code)
        ? Number(error?.code)
        : undefined;
    this.isCourseNotFound = isCourseNotFoundError({
      ...error,
      code: this.code,
      status: this.status,
    });
  }
}

export const getCourseInfo = async (courseId: string, previewMode: boolean) => {
  try {
    const encodedCourseId = encodeURIComponent(courseId);
    const res = await request.get(
      `/api/learn/shifu/${encodedCourseId}?preview_mode=${previewMode}`,
      // `/api/course/get-course-info?course_id=${courseId}&preview_mode=${previewMode}`,
    );

    // Do processing at the model layer to adapt the new interface to the old interface format
    // Reduce the impact on the view layer
    return {
      course_desc: res.description,
      course_id: res.bid,
      course_keywords: res.keywords,
      course_name: res.title,
      course_price: res.price,
      course_teacher_avatar: res.avatar,
      course_avatar: res.avatar,
      course_tts_enabled: !!res?.tts_enabled,
    };
  } catch (rawError: any) {
    const error = new CourseInfoFetchError(rawError);
    const networkType =
      typeof navigator !== 'undefined' && (navigator as any).connection
        ? (navigator as any).connection.effectiveType || ''
        : '';
    tracking('learner_course_info_fetch_error', {
      shifu_bid: courseId,
      preview_mode: previewMode,
      error_code: error.code ?? '',
      http_status: error.status ?? '',
      error_type: error.isCourseNotFound
        ? 'course_not_found'
        : error.status
          ? 'http_error'
          : 'unknown_error',
      path: typeof window !== 'undefined' ? window.location.pathname : '',
      ua: typeof navigator !== 'undefined' ? navigator.userAgent : '',
      is_wechat: typeof navigator !== 'undefined' ? Boolean(inWechat()) : false,
      network_type: networkType,
      is_course_not_found: error.isCourseNotFound,
    });
    throw error;
  }
};
