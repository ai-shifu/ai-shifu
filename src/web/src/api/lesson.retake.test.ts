import { resetChapter } from './lesson';
import request from '@/lib/request';
const mockUser = { userInfo: { user_id: 'learner' } };
const mockSystem = { previewMode: false };
jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: { delete: jest.fn() },
}));
jest.mock('@/store', () => ({
  useUserStore: { getState: () => mockUser },
}));
jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: { getState: () => mockSystem },
}));
jest.mock('@/store/envStore', () => ({
  useEnvStore: { getState: () => ({ courseId: 'course' }) },
}));
it('reuses uncertain requests but creates a new identity after acceptance', async () => {
  jest
    .mocked(request.delete)
    .mockRejectedValueOnce(new Error('network lost'))
    .mockResolvedValue({ code: 0 });
  await expect(resetChapter({ lessonId: 'lesson' })).rejects.toThrow(
    'network lost',
  );
  await resetChapter({ lessonId: 'lesson' });
  await resetChapter({ lessonId: 'lesson' });
  const ids = jest
    .mocked(request.delete)
    .mock.calls.map(
      call =>
        (call[1]?.headers as Record<string, string>)['X-Retake-Request-Id'],
    );
  expect(ids[0]).toBe(ids[1]);
  expect(ids[2]).not.toBe(ids[1]);
  expect(request.delete).toHaveBeenCalledWith(
    '/api/learn/shifu/course/records/lesson?preview_mode=false',
    expect.any(Object),
  );
});
it('uses a new identity after a released attempt', async () => {
  jest
    .mocked(request.delete)
    .mockClear()
    .mockRejectedValueOnce({ code: 4025 })
    .mockResolvedValue({ code: 0 });
  await expect(resetChapter({ lessonId: 'released' })).rejects.toEqual({
    code: 4025,
  });
  await resetChapter({ lessonId: 'released' });
  expect(jest.mocked(request.delete).mock.calls[0][1]?.headers).not.toEqual(
    jest.mocked(request.delete).mock.calls[1][1]?.headers,
  );
});
it('does not share uncertain identities across signed-in learners', async () => {
  jest
    .mocked(request.delete)
    .mockClear()
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValue({ code: 0 });
  await expect(resetChapter({ lessonId: 'shared-browser' })).rejects.toThrow();
  mockUser.userInfo.user_id = 'other';
  await resetChapter({ lessonId: 'shared-browser' });
  expect(jest.mocked(request.delete).mock.calls[0][1]?.headers).not.toEqual(
    jest.mocked(request.delete).mock.calls[1][1]?.headers,
  );
});
