import request from '@/lib/request';
import { getCourseInfo, recordCourseVisit } from './course';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

jest.mock('@/c-constants/uiConstants', () => ({
  inWechat: jest.fn(() => false),
}));

jest.mock('@/c-common/tools/tracking', () => ({
  tracking: jest.fn(),
}));

jest.mock('@/i18n', () => ({
  __esModule: true,
  default: {
    language: 'en-US',
    resolvedLanguage: 'en-US',
    t: (key: string) => key,
  },
}));

const mockGet = request.get as jest.Mock;
const mockPost = request.post as jest.Mock;

describe('getCourseInfo owner context', () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  test.each([
    [true, true],
    [false, false],
    [undefined, false],
  ] as const)('maps API is_owner=%s to %s', async (isOwner, expected) => {
    mockGet.mockResolvedValue({
      bid: 'course-1',
      title: 'Course',
      description: 'Description',
      keywords: ['test'],
      price: '0',
      avatar: '',
      tts_enabled: true,
      is_owner: isOwner,
    });

    const result = await getCourseInfo('course-1', true);

    expect(result.course_is_owner).toBe(expected);
  });
});

describe('recordCourseVisit', () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockPost.mockResolvedValue({ recorded: true });
  });

  test('posts an empty best-effort request through the shared transport', async () => {
    await recordCourseVisit(' course/1 ');

    expect(mockPost).toHaveBeenCalledWith(
      '/api/learn/shifu/course%2F1/visit',
      {},
      {
        keepalive: true,
        skipAuthRecovery: true,
        skipErrorToast: true,
      },
    );
  });
});
