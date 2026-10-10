import request from '@/lib/request';
import { useSystemStore } from '@/store/useSystemStore';
import { resetChapter, getLessonResetStatus } from './lesson';

let mockRequestNumber = 0;
let mockUserId = 'learner';
let mockToken = 'authenticated-token';
jest.mock('@/lib/request', () => ({
  __esModule: true,
  default: { delete: jest.fn(), get: jest.fn() },
}));
jest.mock('@/lib/request-trace', () => ({
  TRACE_REQUEST_ID_HEADER: 'X-Request-ID',
  createRequestId: () => `request-${++mockRequestNumber}`,
}));
jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: { getState: jest.fn() },
}));
jest.mock('@/store/useUserStore', () => ({
  useUserStore: {
    getState: () => ({
      userInfo: mockUserId ? { user_id: mockUserId } : null,
      getToken: () => mockToken,
    }),
  },
}));
jest.mock('@/store/envStore', () => ({
  useEnvStore: { getState: jest.fn(() => ({ courseId: 'course' })) },
}));

describe('lesson reset transport', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUserId = 'learner';
    mockToken = 'authenticated-token';
    (useSystemStore.getState as jest.Mock).mockReturnValue({
      previewMode: false,
    });
    (request.delete as jest.Mock).mockResolvedValue(true);
  });

  it.each([true, false])(
    'sends explicit preview scope %s',
    async previewMode => {
      (useSystemStore.getState as jest.Mock).mockReturnValue({ previewMode });
      await resetChapter({ lessonId: 'lesson' });
      expect(request.delete).toHaveBeenLastCalledWith(
        `/api/learn/shifu/course/records/lesson?preview_mode=${previewMode}`,
        {
          headers: { 'X-Request-ID': expect.any(String) },
          skipErrorToast: true,
        },
      );
    },
  );

  it('preserves retry identity after a lost response, then starts a new operation', async () => {
    (request.delete as jest.Mock).mockRejectedValueOnce(
      new Error('response lost'),
    );
    await expect(resetChapter({ lessonId: 'retry' })).rejects.toThrow();
    await resetChapter({ lessonId: 'retry' });
    await resetChapter({ lessonId: 'retry' });
    const ids = (request.delete as jest.Mock).mock.calls.map(
      ([, config]) => config.headers['X-Request-ID'],
    );
    expect(ids[0]).toBe(ids[1]);
    expect(ids[2]).not.toBe(ids[1]);
  });

  it('never reuses another account or lesson pending identity', async () => {
    (request.delete as jest.Mock).mockRejectedValueOnce(
      new Error('response lost'),
    );
    await expect(resetChapter({ lessonId: 'scoped' })).rejects.toThrow();
    mockUserId = 'other';
    await resetChapter({ lessonId: 'scoped' });
    mockUserId = 'learner';
    await resetChapter({ lessonId: 'other-lesson' });
    const ids = (request.delete as jest.Mock).mock.calls.map(
      ([, config]) => config.headers['X-Request-ID'],
    );
    expect(new Set(ids).size).toBe(3);
    await resetChapter({ lessonId: 'scoped' });
    expect(
      (request.delete as jest.Mock).mock.calls[3][1].headers['X-Request-ID'],
    ).toBe(ids[0]);
  });

  it('reads availability with no balance contract and no duplicate toast', async () => {
    (request.get as jest.Mock).mockResolvedValue({ can_reset: false });
    expect(await getLessonResetStatus('lesson')).toEqual({ can_reset: false });
    expect(request.get).toHaveBeenCalledWith(
      '/api/learn/shifu/course/records/lesson/reset-status?preview_mode=false',
      { skipErrorToast: true },
    );
  });

  it('keeps guest retries stable without sharing them with a different guest', async () => {
    mockUserId = '';
    mockToken = 'first-guest-token';
    (request.delete as jest.Mock).mockRejectedValueOnce(
      new Error('response lost'),
    );
    await expect(resetChapter({ lessonId: 'guest-retry' })).rejects.toThrow();
    mockToken = 'second-guest-token';
    await resetChapter({ lessonId: 'guest-retry' });
    mockToken = 'first-guest-token';
    await resetChapter({ lessonId: 'guest-retry' });
    const ids = (request.delete as jest.Mock).mock.calls.map(
      ([, config]) => config.headers['X-Request-ID'],
    );
    expect(ids[1]).not.toBe(ids[0]);
    expect(ids[2]).toBe(ids[0]);
  });
});
