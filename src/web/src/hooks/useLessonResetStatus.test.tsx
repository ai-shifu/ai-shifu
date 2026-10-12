import { act, renderHook, waitFor } from '@testing-library/react';
import { useLessonResetStatus } from './useLessonResetStatus';
import { getLessonResetStatus } from '@/api/lesson';

const mockEnv = { courseId: 'course' };
const mockSystem = { previewMode: false };
let mockToken = 'authenticated-token';
const mockUser: {
  userInfo: { user_id: string } | null;
  isInitialized: boolean;
  getToken: () => string;
} = {
  userInfo: { user_id: 'learner' },
  isInitialized: true,
  getToken: () => mockToken,
};
const mockCourse = { resettingLessonId: '' };
jest.mock('@/api/lesson', () => ({ getLessonResetStatus: jest.fn() }));
jest.mock('@/store/envStore', () => ({
  useEnvStore: (selector: any) => selector(mockEnv),
}));
jest.mock('@/store/useSystemStore', () => ({
  useSystemStore: (selector: any) => selector(mockSystem),
}));
jest.mock('@/store/useUserStore', () => ({
  useUserStore: (selector: any) => selector(mockUser),
}));
jest.mock('@/store/useCourseStore', () => ({
  useCourseStore: (selector: any) => selector(mockCourse),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockUser.isInitialized = true;
  mockUser.userInfo = { user_id: 'learner' };
  mockToken = 'authenticated-token';
  mockCourse.resettingLessonId = '';
  (getLessonResetStatus as jest.Mock)
    .mockReset()
    .mockResolvedValue({ can_reset: true });
});

it('waits for learner initialization and only queries an active reset surface', async () => {
  mockUser.isInitialized = false;
  const { result, rerender } = renderHook(
    ({ active }) => useLessonResetStatus('lesson', active),
    { initialProps: { active: false } },
  );
  expect(getLessonResetStatus).not.toHaveBeenCalled();
  rerender({ active: true });
  expect(result.current.phase).toBe('idle');
  expect(getLessonResetStatus).not.toHaveBeenCalled();
  mockUser.isInitialized = true;
  rerender({ active: true });
  await waitFor(() => expect(result.current.phase).toBe('ready'));
});

it('ignores a stale availability response after changing learner or lesson', async () => {
  let resolve!: (value: { can_reset: boolean }) => void;
  (getLessonResetStatus as jest.Mock).mockReturnValueOnce(
    new Promise(done => {
      resolve = done;
    }),
  );
  const { result, rerender } = renderHook(
    ({ lesson }) => useLessonResetStatus(lesson, true),
    { initialProps: { lesson: 'old' } },
  );
  mockUser.userInfo = { user_id: 'other' };
  rerender({ lesson: 'new' });
  await waitFor(() => expect(result.current.phase).toBe('ready'));
  await act(async () => resolve({ can_reset: false }));
  expect(result.current.phase).toBe('ready');
});

it('enables a first-visit guest with a valid token but no loaded profile', async () => {
  mockUser.userInfo = null;
  mockToken = 'guest-token';
  const { result } = renderHook(() => useLessonResetStatus('lesson', true));
  await waitFor(() => expect(result.current.phase).toBe('ready'));
  expect(getLessonResetStatus).toHaveBeenCalledTimes(1);
});

it('does not query when guest initialization failed to obtain an identity', () => {
  mockUser.userInfo = null;
  mockToken = '';
  const { result } = renderHook(() => useLessonResetStatus('lesson', true));
  expect(result.current.phase).toBe('idle');
  expect(getLessonResetStatus).not.toHaveBeenCalled();
});

it('ignores an old guest response after changing guest identity', async () => {
  mockUser.userInfo = null;
  mockToken = 'first-guest-token';
  let resolve!: (value: { can_reset: boolean }) => void;
  (getLessonResetStatus as jest.Mock).mockReturnValueOnce(
    new Promise(done => {
      resolve = done;
    }),
  );
  const { result, rerender } = renderHook(() =>
    useLessonResetStatus('lesson', true),
  );
  mockToken = 'second-guest-token';
  rerender();
  await waitFor(() => expect(result.current.phase).toBe('ready'));
  await act(async () => resolve({ can_reset: false }));
  expect(result.current.phase).toBe('ready');
});

it('refreshes after reset completes and surfaces the terminal server rejection', async () => {
  const { result, rerender } = renderHook(() =>
    useLessonResetStatus('lesson', true),
  );
  await waitFor(() => expect(result.current.phase).toBe('ready'));
  mockCourse.resettingLessonId = 'lesson';
  rerender();
  (getLessonResetStatus as jest.Mock).mockResolvedValue({ can_reset: false });
  mockCourse.resettingLessonId = '';
  rerender();
  await waitFor(() => expect(result.current.phase).toBe('exhausted'));
  act(() => result.current.setFailure({ code: 4022 }));
  expect(result.current.phase).toBe('unavailable');
});

it('makes a failed availability read unavailable, without enabling reset', async () => {
  (getLessonResetStatus as jest.Mock).mockRejectedValue(new Error('offline'));
  const { result } = renderHook(() => useLessonResetStatus('lesson', true));
  await waitFor(() => expect(result.current.phase).toBe('unavailable'));
});

it.each(['focus', 'online'])(
  'recovers an active unavailable surface on %s without remounting',
  async event => {
    (getLessonResetStatus as jest.Mock).mockRejectedValueOnce(
      new Error('offline'),
    );
    const { result, unmount } = renderHook(() =>
      useLessonResetStatus('lesson', true),
    );
    await waitFor(() => expect(result.current.phase).toBe('unavailable'));
    await act(async () => window.dispatchEvent(new Event(event)));
    await waitFor(() => expect(result.current.phase).toBe('ready'));
    expect(getLessonResetStatus).toHaveBeenCalledTimes(2);
    unmount();
    await act(async () => window.dispatchEvent(new Event(event)));
    expect(getLessonResetStatus).toHaveBeenCalledTimes(2);
  },
);

it('does not refresh a closed reset surface or an exhausted allowance on focus', async () => {
  (getLessonResetStatus as jest.Mock).mockResolvedValue({ can_reset: false });
  const { result, rerender } = renderHook(
    ({ active }) => useLessonResetStatus('lesson', active),
    { initialProps: { active: true } },
  );
  await waitFor(() => expect(result.current.phase).toBe('exhausted'));
  await act(async () => window.dispatchEvent(new Event('focus')));
  expect(getLessonResetStatus).toHaveBeenCalledTimes(1);
  rerender({ active: false });
  await act(async () => window.dispatchEvent(new Event('online')));
  expect(getLessonResetStatus).toHaveBeenCalledTimes(1);
});

it('rechecks unavailable status only when the page becomes visible', async () => {
  (getLessonResetStatus as jest.Mock).mockRejectedValueOnce(
    new Error('offline'),
  );
  const { result } = renderHook(() => useLessonResetStatus('lesson', true));
  await waitFor(() => expect(result.current.phase).toBe('unavailable'));
  const visibility = jest
    .spyOn(document, 'visibilityState', 'get')
    .mockReturnValue('hidden');
  try {
    await act(async () =>
      document.dispatchEvent(new Event('visibilitychange')),
    );
    expect(getLessonResetStatus).toHaveBeenCalledTimes(1);
    visibility.mockReturnValue('visible');
    await act(async () =>
      document.dispatchEvent(new Event('visibilitychange')),
    );
    await waitFor(() => expect(result.current.phase).toBe('ready'));
    expect(getLessonResetStatus).toHaveBeenCalledTimes(2);
  } finally {
    visibility.mockRestore();
  }
});
