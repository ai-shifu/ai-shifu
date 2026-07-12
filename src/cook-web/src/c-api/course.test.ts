import request from '@/lib/request';
import { getCourseInfo } from './course';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
  },
}));

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
});
