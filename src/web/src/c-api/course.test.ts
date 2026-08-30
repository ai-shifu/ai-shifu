import request from '@/lib/request';
import { getCourseInfo } from './course';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
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
