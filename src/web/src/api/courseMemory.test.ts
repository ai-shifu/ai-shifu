import request from '@/lib/request';
import { listCourseMemory } from './courseMemory';

jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

test.each([undefined, '9223372036854775806'])(
  'serializes the course scope and optional cursor into the request URL (%s)',
  async before => {
    await listCourseMemory('course-id', before);
    const [path, config] = (request.get as jest.Mock).mock.lastCall;
    const url = new URL(path, 'https://example.test');
    expect(url.pathname).toBe('/api/user/course-memory');
    expect(url.searchParams.get('course_id')).toBe('course-id');
    expect(url.searchParams.get('before')).toBe(before ?? null);
    expect(config).toEqual({ skipErrorToast: true });
  },
);
