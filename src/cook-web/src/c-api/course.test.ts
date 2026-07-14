import request, { ErrorWithCode } from '@/lib/request';
import { CourseInfoFetchError, getCourseInfo } from './course';

jest.mock('@/lib/request', () => {
  class MockErrorWithCode extends Error {
    code: number;
    status?: number;

    constructor(message: string, code: number) {
      super(message);
      this.code = code;
    }
  }

  return {
    __esModule: true,
    ErrorWithCode: MockErrorWithCode,
    default: {
      get: jest.fn(),
    },
  };
});

jest.mock('@/c-common/tools/tracking', () => ({
  tracking: jest.fn(),
}));

jest.mock('@/c-constants/uiConstants', () => ({
  inWechat: () => false,
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    language: 'en-US',
    resolvedLanguage: 'en-US',
    t: (key: string) => key,
  },
}));

describe('getCourseInfo', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('normalizes the route identifier response to canonical course identity', async () => {
    (request.get as jest.Mock).mockResolvedValue({
      bid: 'canonical-bid',
      slug: 'practical-ai-teaching-methods',
      canonical_path: '/c/practical-ai-teaching-methods',
      title: 'Practical AI Teaching Methods',
      description: 'Course description',
      keywords: ['ai', 'teaching'],
      price: 0,
      avatar: '/avatar.png',
      tts_enabled: true,
    });

    await expect(
      getCourseInfo('practical-ai-teaching-methods', false),
    ).resolves.toEqual({
      course_id: 'canonical-bid',
      course_slug: 'practical-ai-teaching-methods',
      course_canonical_url: '/c/practical-ai-teaching-methods',
      course_name: 'Practical AI Teaching Methods',
      course_desc: 'Course description',
      course_keywords: 'ai,teaching',
      course_price: 0,
      course_teacher_avatar: '/avatar.png',
      course_avatar: '/avatar.png',
      course_tts_enabled: true,
    });

    expect(request.get).toHaveBeenCalledWith(
      '/api/learn/shifu/practical-ai-teaching-methods?preview_mode=false',
      { skipErrorToast: undefined },
    );
  });

  test('classifies the backend shifu-not-found business code without losing the error message', async () => {
    const error = new ErrorWithCode('Localized course missing message', 4008);
    error.status = 200;
    (request.get as jest.Mock).mockRejectedValue(error);

    await expect(
      getCourseInfo('missing-course', false, { trackErrors: false }),
    ).rejects.toMatchObject({
      name: 'CourseInfoFetchError',
      message: 'Localized course missing message',
      code: 4008,
      status: 200,
      isCourseNotFound: true,
    });
  });

  test('preserves native Error messages when applying the not-found fallback', async () => {
    (request.get as jest.Mock).mockRejectedValue(new Error('Course not found'));

    try {
      await getCourseInfo('missing-course', false, { trackErrors: false });
      throw new Error('Expected getCourseInfo to reject');
    } catch (error) {
      expect(error).toBeInstanceOf(CourseInfoFetchError);
      expect(error).toMatchObject({
        message: 'Course not found',
        isCourseNotFound: true,
      });
    }
  });

  test('keeps transient server errors retryable', async () => {
    const error = new ErrorWithCode('Service unavailable', 500);
    error.status = 500;
    (request.get as jest.Mock).mockRejectedValue(error);

    await expect(
      getCourseInfo('temporarily-unavailable-course', false, {
        trackErrors: false,
      }),
    ).rejects.toMatchObject({
      message: 'Service unavailable',
      code: 500,
      status: 500,
      isCourseNotFound: false,
    });
  });
});
